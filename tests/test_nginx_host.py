"""configs/nginx-host: the stack, the nginx template and nginx/render.sh."""

import os
import re
import shutil
import subprocess
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "configs" / "nginx-host"
GATEWAY = "172.30.87.1"
PORTS = {"privacyfence": 8765, "peek": 7700, "grist": 8484, "grist-provisioner": 8485}


def compose() -> dict:
    return yaml.safe_load((CONFIG / "compose.yaml").read_text())


def env_example() -> dict[str, str]:
    values = {}
    for line in (CONFIG / ".env.example").read_text().splitlines():
        if line and not line.startswith("#") and "=" in line:
            key, _, value = line.partition("=")
            values[key] = value
    return values


def test_init_is_the_common_one():
    assert (CONFIG / "init.sh").read_bytes() == (ROOT / "common" / "init.sh").read_bytes()


def test_every_required_variable_is_in_env_example():
    used = set(re.findall(r"(?<!\$)\$\{([A-Z_]+)(?::\?|:-|\})", (CONFIG / "compose.yaml").read_text()))
    missing = used - set(env_example())
    assert not missing


def test_apps_publish_their_port_on_loopback_only():
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
    text = (CONFIG / "nginx" / "privacyfence-suite.conf.template").read_text()
    targets = set(re.findall(r"proxy_pass\s+([^;\s]+);", text))
    assert targets == {f"http://127.0.0.1:{p}" for p in PORTS.values()}
    pf_address = compose()["services"]["privacyfence"]["networks"]["pf"]["ipv4_address"]
    guard = text.split("location /api/provisioning/", 1)[1]
    assert f"$remote_addr != {pf_address}" in guard.split("}", 1)[0]
    assert "auth_basic" not in text.replace("no basic auth", "")
    assert not re.search(r"^\s*proxy_set_header\s+X-Forwarded-User", text, re.MULTILINE)
    assert not re.search(r"ssl_protocols[^;]*TLSv1(\.1)?[ ;]", text)


def test_project_name_follows_the_other_configurations():
    assert compose()["name"] == "privacyfence-nginx-host"


def test_privacyfence_env_example_names_no_provisioning_key():
    text = (CONFIG / "privacyfence.env.example").read_text()
    assert not re.search(r"^[^#]*PROVISIONING_KEY", text, re.MULTILINE)
    assert "PRIVACYFENCE_IDP_CLIENT_SECRET_FILE=/run/suite/idp_client_secret" in text


def render(tmp_path, nginx_dump=None, **env_lines):
    """Runs nginx/render.sh in a copy of the configuration; NGINX_DUMP is what a fake `nginx -T` prints."""
    work = tmp_path / "c"
    shutil.copytree(CONFIG, work)
    env = (work / ".env.example").read_text()
    values = {
        "PF_HOSTNAME": "pf.example.com",
        "PEEK_HOSTNAME": "peek.example.net",
        "GRIST_HOSTNAME": "grist.example.net",
        **env_lines,
    }
    for key, value in values.items():
        if re.search(rf"^{key}=", env, flags=re.MULTILINE):
            env = re.sub(rf"^{key}=.*$", f"{key}={value}", env, flags=re.MULTILINE)
        else:
            env += f"{key}={value}\n"
    (work / ".env").write_text(env)
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    for tool in ("sh", "sed", "awk", "cat", "dirname"):
        target = shutil.which(tool)
        if target:
            os.symlink(target, bin_dir / tool)
    if nginx_dump is not None:
        (tmp_path / "dump.txt").write_text(nginx_dump)
        (bin_dir / "nginx").write_text(f'#!/bin/sh\n[ "$1" = -T ] && cat "{tmp_path / "dump.txt"}"\n')
        (bin_dir / "nginx").chmod(0o755)
    return subprocess.run(
        ["sh", str(work / "nginx" / "render.sh")],
        capture_output=True,
        text=True,
        check=True,
        env={"PATH": str(bin_dir)},
    )


def test_render_fills_every_placeholder(tmp_path):
    out = render(tmp_path, GRIST_CERT="/etc/ssl/grist/chain.pem").stdout
    assert "@" not in re.sub(r"#.*", "", out)
    assert "server_name pf.example.com;" in out
    assert "ssl_certificate     /etc/ssl/certs/peek.example.net/fullchain.pem;" in out
    assert "ssl_certificate     /etc/ssl/grist/chain.pem;" in out
    assert re.search(r"^limit_req_zone .*zone=pf_oauth", out, re.MULTILINE)


def test_render_writes_peek_redirects(tmp_path):
    out = render(tmp_path, PEEK_REDIRECT_HOSTNAMES='"peek.example.com peek.example.org"').stdout
    for name in ("peek.example.com", "peek.example.org"):
        assert f"server_name {name};" in out
        assert f"ssl_certificate     /etc/ssl/certs/{name}/fullchain.pem;" in out
    assert out.count("return 301 https://peek.example.net$request_uri;") == 4


def test_render_uses_a_pf_oauth_zone_defined_elsewhere(tmp_path):
    dump = (
        "# configuration file /etc/nginx/conf.d/privacyfence-suite.conf:\n"
        "limit_req_zone $binary_remote_addr zone=pf_oauth:10m rate=30r/m;\n"
        "# configuration file /etc/nginx/sites-enabled/pf-all:\n"
        "limit_req_zone $binary_remote_addr zone=pf_oauth:10m rate=30r/m;\n"
    )
    result = render(tmp_path, dump)
    assert not re.search(r"^limit_req_zone", result.stdout, re.MULTILINE)
    assert "(already defined in /etc/nginx/sites-enabled/pf-all)" in result.stdout
    assert "limit_req zone=pf_oauth burst=20 nodelay;" in result.stdout
    assert "/etc/nginx/sites-enabled/pf-all already defines the pf_oauth zone" in result.stderr


def test_render_ignores_its_own_site_zone(tmp_path):
    dump = (
        "# configuration file /etc/nginx/conf.d/privacyfence-suite.conf:\n"
        "limit_req_zone $binary_remote_addr zone=pf_oauth:10m rate=30r/m;\n"
    )
    out = render(tmp_path, dump).stdout
    assert re.search(r"^limit_req_zone .*zone=pf_oauth", out, re.MULTILINE)


def test_render_lints():
    if not shutil.which("shellcheck"):
        return
    subprocess.run(["shellcheck", "-s", "sh", str(CONFIG / "nginx" / "render.sh")], check=True)
