#!/usr/bin/env python3
"""Consistency checks for configs/*/ (see docs/privacyfence-suite-plan.md, "scripts/check_configs.py")."""

import re
import sys
from pathlib import Path

import yaml

REQUIRED_SERVICES = ["init", "privacyfence", "peek", "grist", "grist-provisioner"]
HARDENED = ["privacyfence", "peek", "grist-provisioner"]
SAME_IMAGE = ["privacyfence", "peek", "grist", "grist-provisioner"]
PROXIES = ["caddy", "nginx"]
SECRET_VOLUMES = {
    "pf-secrets": "privacyfence",
    "peek-secrets": "peek",
    "grist-secrets": "grist",
    "provisioner-secrets": "grist-provisioner",
}
HOSTNAME_VARS = ["PF_HOSTNAME", "PEEK_HOSTNAME", "GRIST_HOSTNAME"]
IMAGE_RE = re.compile(r"^[^$]+:\$\{[A-Z0-9_]+_IMAGE_TAG:\?pin a version in \.env\}$")
SECRET_KEY_RE = re.compile(r"(?i)(secret|password|_key)$")
COMPOSE_VAR_RE = re.compile(r"(?<!\$)\$\{([A-Za-z_][A-Za-z0-9_]*)(:-)?")
TEMPLATE_BRACED_RE = re.compile(r"\$\{([A-Za-z_][A-Za-z0-9_]*)\}")
CADDY_VAR_RE = re.compile(r"\{\$([A-Za-z_][A-Za-z0-9_]*)\}")


def tag_name(service: str) -> str:
    return "ALPINE" if service == "init" else service.upper().replace("-", "_")


def read_env_example(path: Path) -> dict[str, str]:
    values = {}
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        values[key.strip()] = value.strip()
    return values


def find_proxy(services: dict) -> str | None:
    for name in PROXIES:
        if name in services:
            return name
    return None


def depends_on_map(service: dict) -> dict:
    deps = service.get("depends_on") or {}
    if isinstance(deps, list):
        return {name: {} for name in deps}
    return deps


def volume_sources(service: dict) -> list[str]:
    sources = []
    for entry in service.get("volumes") or []:
        if isinstance(entry, str):
            sources.append(entry.split(":")[0])
        elif isinstance(entry, dict) and "source" in entry:
            sources.append(str(entry["source"]))
    return sources


def proxy_networks(service: dict) -> list[dict]:
    networks = service.get("networks") or {}
    if isinstance(networks, dict):
        return [n or {} for n in networks.values()]
    return []


def check_template_locations(path: Path, rel: str) -> list[str]:
    problems = []
    stack: list[str] = []
    for number, raw in enumerate(path.read_text().splitlines(), start=1):
        line = raw.split("#", 1)[0]
        is_location = re.match(r"\s*location\b", line) is not None
        for char in line:
            if char == "{":
                stack.append("location" if is_location else "other")
                is_location = False
            elif char == "}" and stack:
                stack.pop()
        if re.search(r"\bproxy_set_header\b", line) and "location" in stack:
            problems.append(f"proxy_set_header inside a location in {rel}:{number}")
    return problems


def check_config(root: Path, cfg: Path) -> list[str]:
    problems = []
    for name in ("compose.yaml", ".env.example", "init.sh"):
        if not (cfg / name).is_file():
            problems.append(f"missing {name}")
    if (cfg / "init.sh").is_file():
        common = root / "common" / "init.sh"
        if not common.is_file() or (cfg / "init.sh").read_bytes() != common.read_bytes():
            problems.append("init.sh differs from common/init.sh")
    if not (cfg / "compose.yaml").is_file():
        return problems

    compose_text = (cfg / "compose.yaml").read_text()
    compose = yaml.safe_load(compose_text) or {}
    services = compose.get("services") or {}
    env_example = read_env_example(cfg / ".env.example") if (cfg / ".env.example").is_file() else None
    proxy = find_proxy(services)

    for name in REQUIRED_SERVICES:
        if name not in services:
            problems.append(f"missing service {name}")

    for name, svc in services.items():
        image = svc.get("image")
        if image is not None and not IMAGE_RE.match(str(image)):
            problems.append(f"{name} image must use ${{{tag_name(name)}_IMAGE_TAG:?pin a version in .env}}")

    if env_example is not None:
        for key, value in env_example.items():
            if key.endswith("_IMAGE_TAG") and (
                not value or (value == "latest" and key != "PRIVACYFENCE_IMAGE_TAG")
            ):
                problems.append(f"{key} must pin a version")

    # 5 and 5b: variables used but not assigned / not in the proxy's environment
    templates = sorted((cfg / "templates").glob("*.template")) if (cfg / "templates").is_dir() else []
    caddyfile = cfg / "Caddyfile"
    used: list[str] = []
    for match in COMPOSE_VAR_RE.finditer(compose_text):
        if not match.group(2):
            used.append(match.group(1))
    proxy_used: list[str] = []
    for template in templates:
        text = template.read_text()
        used += [m.group(1) for m in COMPOSE_VAR_RE.finditer(text) if not m.group(2)]
        proxy_used += TEMPLATE_BRACED_RE.findall(text)
    if caddyfile.is_file():
        found = CADDY_VAR_RE.findall(caddyfile.read_text())
        used += found
        proxy_used += found
    if env_example is not None:
        for var in dict.fromkeys(used):
            if var not in env_example:
                problems.append(f"{var} is used but not in .env.example")
    if proxy:
        proxy_env = services[proxy].get("environment")
        keys = set(proxy_env) if isinstance(proxy_env, dict) else set()
        for var in dict.fromkeys(proxy_used):
            if var not in keys:
                problems.append(f"{var} is used by the proxy config but not in its environment")

    for name, svc in services.items():
        if name == "init":
            continue
        condition = (depends_on_map(svc).get("init") or {}).get("condition")
        if condition != "service_completed_successfully":
            problems.append(f"{name} must depend on init with service_completed_successfully")
    if proxy and set(depends_on_map(services[proxy])) != {"init"}:
        problems.append("the proxy must depend only on init")

    for name in HARDENED:
        svc = services.get(name)
        if svc is None:
            continue
        ok = (
            svc.get("read_only") is True
            and svc.get("cap_drop") == ["ALL"]
            and "no-new-privileges:true" in (svc.get("security_opt") or [])
        )
        if not ok:
            problems.append(f"{name} must be read_only with cap_drop ALL and no-new-privileges")

    if proxy:
        proxy_svc = services[proxy]
        address = None
        aliases: list[str] = []
        for network in proxy_networks(proxy_svc):
            address = address or network.get("ipv4_address")
            aliases += [str(a) for a in network.get("aliases") or []]
        pf_env = (services.get("privacyfence") or {}).get("environment")
        trusted = pf_env.get("PRIVACYFENCE_TRUSTED_PROXIES") if isinstance(pf_env, dict) else None
        if address is None or str(trusted) != str(address):
            problems.append("PRIVACYFENCE_TRUSTED_PROXIES must equal the proxy address")
        if not all(any(a.startswith("${" + var + ":?") for a in aliases) for var in HOSTNAME_VARS):
            problems.append("proxy aliases must list the three hostnames")

    for name, svc in services.items():
        env = svc.get("environment")
        if env is None:
            continue
        if not isinstance(env, dict):
            problems.append(f"{name}.environment must be a mapping")
            continue
        for key in env:
            if SECRET_KEY_RE.search(str(key)):
                problems.append(f"{name}.{key} must come from a file")

    for name, svc in services.items():
        if name == "init":
            continue
        for source in volume_sources(svc):
            if source in SECRET_VOLUMES and SECRET_VOLUMES[source] != name:
                problems.append(f"{name} mounts {source}")

    for template in templates:
        problems += check_template_locations(template, str(template.relative_to(cfg)))
    return problems


def main(root: Path) -> int:
    configs = sorted(p for p in (root / "configs").glob("*/") if p.is_dir()) if (root / "configs").is_dir() else []
    problems: list[tuple[str, str]] = []
    images: dict[str, tuple[str, str]] = {}
    for cfg in configs:
        problems += [(cfg.name, p) for p in check_config(root, cfg)]
        if not (cfg / "compose.yaml").is_file():
            continue
        services = (yaml.safe_load((cfg / "compose.yaml").read_text()) or {}).get("services") or {}
        for name in SAME_IMAGE:
            image = (services.get(name) or {}).get("image")
            if image is None:
                continue
            if name not in images:
                images[name] = (cfg.name, str(image))
            elif images[name][1] != str(image):
                problems.append((cfg.name, f"{name} image differs from configs/{images[name][0]}"))
    if problems:
        for cfg_name, message in problems:
            print(f"{cfg_name}: {message}")
        return 1
    print(f"ok: {len(configs)} configurations")
    return 0


if __name__ == "__main__":
    sys.exit(main(Path(__file__).resolve().parent.parent))
