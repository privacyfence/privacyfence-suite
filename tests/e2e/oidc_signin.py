"""Scripted sign-ins for the localhost stack (standard library only).

    oidc_signin.py pf     sign in to PrivacyFence with the single-user setup code
    oidc_signin.py apps   sign in to Grist and Peek through PrivacyFence's OIDC provider

Both use the cookie jar at $RUNNER_TEMP/cookies.txt (or the system temp dir). On any failed
assertion it prints a one-line reason and exits 1. It never prints a cookie, code or secret.
"""

import json
import os
import re
import subprocess
import sys
import tempfile
import urllib.error
import urllib.parse
import urllib.request
from html.parser import HTMLParser
from http.cookiejar import LoadError, MozillaCookieJar
from pathlib import Path

PF = "http://localhost:8765"
PEEK = "http://localhost:7700"
GRIST = "http://localhost:8484"
EMAIL = "admin@privacyfence.localhost"
COMPOSE_DIR = Path(__file__).resolve().parent.parent.parent / "configs" / "localhost"
JAR_PATH = Path(os.environ.get("RUNNER_TEMP") or tempfile.gettempdir()) / "cookies.txt"
TIMEOUT = 30


class Fail(Exception):
    pass


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None


class _Form(HTMLParser):
    """Collects the name and value of every <input>."""

    def __init__(self):
        super().__init__()
        self.fields: dict[str, str] = {}

    def handle_starttag(self, tag, attrs):
        if tag == "input":
            a = dict(attrs)
            if a.get("name"):
                self.fields[a["name"]] = a.get("value") or ""


def _load_jar() -> MozillaCookieJar:
    jar = MozillaCookieJar(str(JAR_PATH))
    if JAR_PATH.exists():
        try:
            jar.load(ignore_discard=True, ignore_expires=True)
        except LoadError as exc:
            raise Fail(f"cannot read the cookie jar: {exc}") from None
    return jar


def _opener(jar, follow: bool):
    handlers = [urllib.request.HTTPCookieProcessor(jar)]
    if not follow:
        handlers.append(_NoRedirect())
    return urllib.request.build_opener(*handlers)


def _open(opener, url, data=None):
    """Return (response, error_response); HTTPError objects are responses too."""
    req = urllib.request.Request(url, data=data)
    try:
        return opener.open(req, timeout=TIMEOUT)
    except urllib.error.HTTPError as err:
        return err
    except urllib.error.URLError as exc:
        raise Fail(f"{url} is not reachable: {exc.reason}") from None


def _check_cookies_accepted(resp, jar) -> None:
    names = {c.name for c in jar}
    for header in resp.headers.get_all("Set-Cookie") or []:
        name = header.split("=", 1)[0].strip()
        if name not in names:
            attrs = [a.split("=", 1)[0].strip().lower() for a in header.split(";")[1:]]
            raise Fail(f"cookie refused: {name} (attributes: {', '.join(attrs) or 'none'})")


def sign_in_pf() -> None:
    logs = subprocess.run(
        ["docker", "compose", "logs", "--no-color", "privacyfence"],
        cwd=COMPOSE_DIR, capture_output=True, text=True, timeout=60, check=False,
    ).stdout
    codes = re.findall(r"Setup code: ([0-9A-F]{4}-[0-9A-F]{4})", logs)
    if not codes:
        raise Fail("no setup code in the privacyfence log")
    code = codes[-1]

    jar = MozillaCookieJar(str(JAR_PATH))
    page = _open(_opener(jar, True), f"{PF}/login")
    if page.status != 200:
        raise Fail(f"GET /login answered {page.status}")
    _check_cookies_accepted(page, jar)
    form = _Form()
    form.feed(page.read().decode("utf-8", "replace"))
    for field in ("binding", "next"):
        if field not in form.fields:
            raise Fail(f"the login form has no {field} field")
    if "pf_setup_binding" not in {c.name for c in jar}:
        raise Fail("no pf_setup_binding cookie after GET /login")

    body = urllib.parse.urlencode(
        {"code": code, "binding": form.fields["binding"], "next": form.fields["next"]}
    ).encode()
    resp = _open(_opener(jar, False), f"{PF}/login/setup", data=body)
    if resp.status != 303:
        raise Fail(f"POST /login/setup answered {resp.status}, expected 303")
    _check_cookies_accepted(resp, jar)
    location = resp.headers.get("Location", "")
    if not urllib.parse.urlparse(location).path.startswith("/security"):
        raise Fail("POST /login/setup did not redirect to /security")
    if "pf_org_session" not in {c.name for c in jar}:
        raise Fail("no pf_org_session cookie after the setup code")
    jar.save(ignore_discard=True, ignore_expires=True)
    print("pf: signed in")


def sign_in_apps() -> None:
    jar = _load_jar()
    if "pf_org_session" not in {c.name for c in jar}:
        raise Fail("no PrivacyFence session in the cookie jar; run the pf step first")
    opener = _opener(jar, True)

    resp = _open(opener, f"{GRIST}/login?next=/")
    if resp.status != 200:
        raise Fail(f"grist sign-in ended with status {resp.status} at {urllib.parse.urlparse(resp.url).path}")
    profile = _open(opener, f"{GRIST}/api/profile/user")
    if profile.status != 200:
        raise Fail(f"grist /api/profile/user answered {profile.status}")
    try:
        email = json.loads(profile.read()).get("email")
    except ValueError:
        raise Fail("grist /api/profile/user did not return JSON") from None
    if email != EMAIL:
        raise Fail(f"grist profile email is {email!r}, expected {EMAIL!r}")
    print("grist: signed in")

    resp = _open(opener, f"{PEEK}/oauth/oidc/start")
    path = urllib.parse.urlparse(resp.url).path
    if resp.status != 200:
        raise Fail(f"peek sign-in ended with status {resp.status} at {path}")
    if path == "/login":
        raise Fail("peek sign-in ended at /login")
    dash = _open(opener, f"{PEEK}/dashboard")
    if dash.status != 200:
        raise Fail(f"peek /dashboard answered {dash.status}")
    print("peek: signed in")


def main(argv: list[str]) -> int:
    commands = {"pf": sign_in_pf, "apps": sign_in_apps}
    if len(argv) != 2 or argv[1] not in commands:
        print("usage: oidc_signin.py pf|apps", file=sys.stderr)
        return 2
    try:
        commands[argv[1]]()
    except Fail as exc:
        print(f"FAIL: {exc}")
        return 1
    except (subprocess.SubprocessError, OSError) as exc:
        print(f"FAIL: {type(exc).__name__}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
