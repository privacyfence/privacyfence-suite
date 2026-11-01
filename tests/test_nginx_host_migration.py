"""deploy/nginx-host-migration: the stack, the nginx template, migrate.sh's render and the Grist report."""

import importlib.util
import os
import re
import shutil
import sqlite3
import subprocess
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]
DIR = ROOT / "deploy" / "nginx-host-migration"
GATEWAY = "172.30.87.1"
PORTS = {"privacyfence": 8765, "peek": 7700, "grist": 8484, "grist-provisioner": 8485}


def compose() -> dict:
    return yaml.safe_load((DIR / "compose.yaml").read_text())


def env_example() -> dict[str, str]:
    values = {}
    for line in (DIR / ".env.example").read_text().splitlines():
        if line and not line.startswith("#") and "=" in line:
            key, _, value = line.partition("=")
            values[key] = value
    return values


def test_init_is_the_common_one():
    assert (DIR / "init.sh").read_bytes() == (ROOT / "common" / "init.sh").read_bytes()


def test_every_required_variable_is_in_env_example():
    used = set(re.findall(r"(?<!\$)\$\{([A-Z_]+)(?::\?|:-|\})", (DIR / "compose.yaml").read_text()))
    missing = used - set(env_example())
    assert not missing


def test_images_are_pinned():
    for key, value in env_example().items():
        if key.endswith("_IMAGE_TAG"):
            assert value and value != "latest", key


def test_apps_publish_their_old_port_on_loopback_only():
    services = compose()["services"]
    for name, port in PORTS.items():
        assert services[name]["ports"] == [f"127.0.0.1:{port}:{port}"], name
    assert "ports" not in services["init"]


def test_proxy_trust_and_public_names_go_through_the_gateway():
    services = compose()["services"]
    assert services["privacyfence"]["environment"]["PRIVACYFENCE_TRUSTED_PROXIES"] == GATEWAY
    assert services["privacyfence"]["environment"]["PRIVACYFENCE_BIND_HOST"] == "0.0.0.0"
    assert services["peek"]["environment"]["PEEK_TRUSTED_PROXY_CIDRS"] == GATEWAY + "/32"
    for name in ("privacyfence", "peek", "grist"):
        hosts = services[name]["extra_hosts"]
        for var in ("PF_HOSTNAME", "PEEK_HOSTNAME", "GRIST_HOSTNAME"):
            assert any(h.startswith("${" + var + ":?") and h.endswith(":" + GATEWAY) for h in hosts), (name, var)
    network = compose()["networks"]["pf"]
    assert network["driver_opts"]["com.docker.network.bridge.name"] == "pf-suite"
    assert network["ipam"]["config"][0]["gateway"] == GATEWAY


def test_privacyfence_settings_come_from_privacyfence_env():
    pf = compose()["services"]["privacyfence"]
    assert pf["env_file"] == [{"path": "privacyfence.env", "required": True}]
    env = pf["environment"]
    assert not any(k.startswith("PRIVACYFENCE_IDP") for k in env)
    assert env["PRIVACYFENCE_OIDC_CLIENTS"] == "peek,grist"


def test_hardened_services():
    services = compose()["services"]
    for name in ("privacyfence", "peek", "grist-provisioner"):
        svc = services[name]
        assert svc["read_only"] is True and svc["cap_drop"] == ["ALL"], name
        assert "no-new-privileges:true" in svc["security_opt"], name


def test_nginx_template_targets_and_guard():
    text = (DIR / "nginx" / "privacyfence-suite.conf.template").read_text()
    targets = set(re.findall(r"proxy_pass\s+([^;\s]+);", text))
    assert targets == {f"http://127.0.0.1:{p}" for p in PORTS.values()}
    pf_address = compose()["services"]["privacyfence"]["networks"]["pf"]["ipv4_address"]
    guard = text.split("location /api/provisioning/", 1)[1]
    assert f"$remote_addr != {pf_address}" in guard.split("}", 1)[0]
    assert "auth_basic" not in text.replace("no basic auth", "")
    assert not re.search(r"^\s*proxy_set_header\s+X-Forwarded-User", text, re.MULTILINE)
    assert not re.search(r"ssl_protocols[^;]*TLSv1(\.1)?[ ;]", text)


@pytest.mark.skipif(os.geteuid() != 0 or not shutil.which("bash"), reason="migrate.sh runs as root")
def test_migrate_renders_nginx(tmp_path):
    work = tmp_path / "m"
    shutil.copytree(DIR, work)
    env = (work / ".env.example").read_text()
    env = env.replace("PF_HOSTNAME=\n", "PF_HOSTNAME=pf.example.com\n")
    env = env.replace("PEEK_HOSTNAME=\n", "PEEK_HOSTNAME=peek.example.net\n")
    env = env.replace("GRIST_HOSTNAME=\n", "GRIST_HOSTNAME=grist.example.net\n")
    (work / ".env").write_text(env)
    out = subprocess.run(
        ["bash", str(work / "migrate.sh"), "nginx"],
        capture_output=True,
        text=True,
        check=True,
        env={**os.environ, "GRIST_CERT": "/etc/ssl/grist/chain.pem"},
    ).stdout
    assert "@" not in re.sub(r"#.*", "", out)
    assert "server_name pf.example.com;" in out
    assert "ssl_certificate     /etc/ssl/certs/peek.example.net/fullchain.pem;" in out
    assert "ssl_certificate     /etc/ssl/grist/chain.pem;" in out


def test_migrate_script_lints():
    if not shutil.which("shellcheck"):
        pytest.skip("shellcheck not installed")
    subprocess.run(["shellcheck", str(DIR / "migrate.sh")], check=True)


# The Grist report


def load_report():
    spec = importlib.util.spec_from_file_location("preflight_grist", DIR / "preflight_grist.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.report


def make_home_db(path: Path) -> str:
    db = sqlite3.connect(path)
    db.executescript(
        """
        create table logins (id integer primary key, user_id integer, email text, display_email text);
        create table orgs (id integer primary key, name text, domain text, owner_id integer);
        create table workspaces (id integer primary key, org_id integer, removed_at datetime);
        create table docs (id text primary key, workspace_id integer, removed_at datetime);
        create table groups (id integer primary key, name text);
        create table group_users (group_id integer, user_id integer);
        create table acl_rules (id integer primary key, permissions integer, type integer,
                                workspace_id integer, org_id integer, doc_id text, group_id integer);
        insert into logins values (1, 1, 'admin@acme.test', 'admin@acme.test'),
                                  (2, 2, 'bob@acme.test', 'bob@acme.test'),
                                  (3, 3, 'eve@other.test', 'eve@other.test');
        insert into orgs values (10, 'Team', 'team', null), (11, 'Personal', 'docs-2', 2);
        insert into workspaces values (100, 10, null), (101, 11, null), (102, 10, '2026-01-01');
        insert into docs values ('a', 100, null), ('b', 100, null), ('c', 101, null),
                                ('d', 100, '2026-01-01'), ('e', 102, null);
        insert into groups values (5, 'owners'), (6, 'editors');
        insert into group_users values (5, 1), (6, 2);
        insert into acl_rules values (1, 63, 1, null, 10, null, 5), (2, 15, 1, null, 10, null, 6);
        """
    )
    db.commit()
    db.close()
    return str(path)


def test_report_lists_sites_and_flags_problems(tmp_path):
    report = load_report()
    lines = report(make_home_db(tmp_path / "home.sqlite3"), "team", "Admin@acme.test", "acme.test", "bob bob@acme.test")
    text = "\n".join(lines)
    assert "team  'Team'  team site  docs=2" in text
    assert "docs-2  'Personal'  personal site of bob@acme.test  docs=1" in text
    assert "WARN  1 document(s) in the personal site of bob@acme.test" in text
    assert "ok    Admin@acme.test owns team site 'team'" in text
    assert "eve@other.test" in text and "not in ALLOWED_DOMAIN" in text
    assert "htpasswd user 'bob' is not an email address" in text
    assert not any(line.startswith("  FAIL") for line in lines)


def test_report_fails_when_admin_does_not_own_the_site(tmp_path):
    report = load_report()
    lines = report(make_home_db(tmp_path / "home.sqlite3"), "team", "bob@acme.test", "acme.test", "")
    assert any(line.startswith("  FAIL  GRIST_ADMIN_EMAIL=bob@acme.test does not own") for line in lines)


def test_report_warns_about_a_missing_team_site(tmp_path):
    report = load_report()
    lines = report(make_home_db(tmp_path / "home.sqlite3"), "sales", "admin@acme.test", "acme.test", "")
    assert any(line.startswith("  WARN  no team site 'sales'") for line in lines)


def test_report_opens_the_database_read_only(tmp_path):
    report = load_report()
    path = make_home_db(tmp_path / "home.sqlite3")
    before = Path(path).read_bytes()
    report(path, "team", "admin@acme.test", "acme.test", "")
    assert Path(path).read_bytes() == before
