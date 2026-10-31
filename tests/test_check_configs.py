import importlib.util
import shutil
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parent.parent
_spec = importlib.util.spec_from_file_location("check_configs", ROOT / "scripts" / "check_configs.py")
check_configs = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(check_configs)

FIXTURES = Path(__file__).resolve().parent / "fixtures"


def make_tree(tmp_path: Path, name: str = "good") -> Path:
    tree = tmp_path / "tree"
    shutil.copytree(FIXTURES / name, tree)
    return tree


def edit_compose(tree: Path, edit, config: str = "a") -> None:
    path = tree / "configs" / config / "compose.yaml"
    data = yaml.safe_load(path.read_text())
    edit(data)
    path.write_text(yaml.safe_dump(data, sort_keys=False))


def replace_in(path: Path, old: str, new: str) -> None:
    text = path.read_text()
    assert old in text
    path.write_text(text.replace(old, new))


def assert_fails(tree: Path, capsys, *messages: str) -> None:
    code = check_configs.main(tree)
    out = capsys.readouterr().out
    assert out == "".join(f"{m}\n" for m in messages)
    assert code == 1


def test_good_tree_ok(tmp_path, capsys):
    assert check_configs.main(make_tree(tmp_path)) == 0
    assert capsys.readouterr().out == "ok: 1 configurations\n"


def test_proxy_tree_ok(tmp_path, capsys):
    assert check_configs.main(make_tree(tmp_path, "proxy")) == 0
    assert capsys.readouterr().out == "ok: 1 configurations\n"


def test_no_configs_ok(tmp_path, capsys):
    assert check_configs.main(tmp_path) == 0
    assert capsys.readouterr().out == "ok: 0 configurations\n"


def test_check_1(tmp_path, capsys):
    tree = make_tree(tmp_path)
    (tree / "configs/a/.env.example").unlink()
    assert_fails(tree, capsys, "a: missing .env.example")


def test_check_1b(tmp_path, capsys):
    tree = make_tree(tmp_path)
    (tree / "configs/a/init.sh").write_text("#!/bin/sh\necho different\n")
    assert_fails(tree, capsys, "a: init.sh differs from common/init.sh")


def test_check_2(tmp_path, capsys):
    tree = make_tree(tmp_path)
    edit_compose(tree, lambda d: d["services"].pop("peek"))
    assert_fails(tree, capsys, "a: missing service peek")


def test_check_3(tmp_path, capsys):
    tree = make_tree(tmp_path)
    edit_compose(tree, lambda d: d["services"]["peek"].update(image="ghcr.io/privacyfence/peek:0.18.0"))
    assert_fails(tree, capsys, "a: peek image must use ${PEEK_IMAGE_TAG:?pin a version in .env}")


@pytest.mark.parametrize("value", ["latest", ""])
def test_check_4(tmp_path, capsys, value):
    tree = make_tree(tmp_path)
    replace_in(tree / "configs/a/.env.example", "PEEK_IMAGE_TAG=0.18.0", f"PEEK_IMAGE_TAG={value}")
    assert_fails(tree, capsys, "a: PEEK_IMAGE_TAG must pin a version")


def test_check_5(tmp_path, capsys):
    tree = make_tree(tmp_path)
    replace_in(tree / "configs/a/.env.example", "ALLOWED_DOMAIN=example.com\n", "")
    assert_fails(tree, capsys, "a: ALLOWED_DOMAIN is used but not in .env.example")


def test_check_5b(tmp_path, capsys):
    tree = make_tree(tmp_path, "proxy")
    (tree / "configs/a/Caddyfile").write_text("{$OTHER_HOSTNAME} {\n\trespond 404\n}\n")
    with (tree / "configs/a/.env.example").open("a") as f:
        f.write("OTHER_HOSTNAME=\n")
    assert_fails(tree, capsys, "a: OTHER_HOSTNAME is used by the proxy config but not in its environment")


def test_check_6(tmp_path, capsys):
    tree = make_tree(tmp_path)
    edit_compose(tree, lambda d: d["services"]["peek"]["depends_on"]["init"].update(condition="service_started"))
    assert_fails(tree, capsys, "a: peek must depend on init with service_completed_successfully")


def test_check_6b(tmp_path, capsys):
    tree = make_tree(tmp_path, "proxy")
    edit_compose(tree, lambda d: d["services"]["caddy"]["depends_on"].update(grist={"condition": "service_healthy"}))
    assert_fails(tree, capsys, "a: the proxy must depend only on init")


def test_check_7(tmp_path, capsys):
    tree = make_tree(tmp_path)
    edit_compose(tree, lambda d: d["services"]["peek"].pop("read_only"))
    assert_fails(tree, capsys, "a: peek must be read_only with cap_drop ALL and no-new-privileges")


def test_check_8(tmp_path, capsys):
    tree = make_tree(tmp_path)
    shutil.copytree(tree / "configs/a", tree / "configs/b")
    edit_compose(
        tree,
        lambda d: d["services"]["privacyfence"].update(
            image="ghcr.io/other/privacyfence-org:${PRIVACYFENCE_IMAGE_TAG:?pin a version in .env}"
        ),
        config="b",
    )
    assert_fails(tree, capsys, "b: privacyfence image differs from configs/a")


def test_check_9(tmp_path, capsys):
    tree = make_tree(tmp_path, "proxy")
    replace_in(
        tree / "configs/a/compose.yaml",
        "PRIVACYFENCE_TRUSTED_PROXIES: 172.30.87.2",
        "PRIVACYFENCE_TRUSTED_PROXIES: 172.30.87.9",
    )
    assert_fails(tree, capsys, "a: PRIVACYFENCE_TRUSTED_PROXIES must equal the proxy address")


def test_check_9b(tmp_path, capsys):
    tree = make_tree(tmp_path, "proxy")
    edit_compose(tree, lambda d: d["services"]["caddy"]["networks"]["pf"]["aliases"].pop())
    assert_fails(tree, capsys, "a: proxy aliases must list the three hostnames")


def test_check_10(tmp_path, capsys):
    tree = make_tree(tmp_path)
    edit_compose(tree, lambda d: d["services"]["peek"].update(environment=["PEEK_X=1"]))
    assert_fails(tree, capsys, "a: peek.environment must be a mapping")


def test_check_10b(tmp_path, capsys):
    tree = make_tree(tmp_path)
    edit_compose(tree, lambda d: d["services"]["peek"]["environment"].update(PEEK_API_SECRET="x"))
    assert_fails(tree, capsys, "a: peek.PEEK_API_SECRET must come from a file")


def test_check_11(tmp_path, capsys):
    tree = make_tree(tmp_path)
    edit_compose(tree, lambda d: d["services"]["peek"]["volumes"].append("grist-secrets:/run/other:ro"))
    assert_fails(tree, capsys, "a: peek mounts grist-secrets")


def test_check_12(tmp_path, capsys):
    tree = make_tree(tmp_path, "proxy")
    templates = tree / "configs/a/templates"
    templates.mkdir()
    (templates / "default.conf.template").write_text(
        "server {\n    location / {\n        proxy_set_header Host $host;\n    }\n}\n"
    )
    assert_fails(tree, capsys, "a: proxy_set_header inside a location in templates/default.conf.template:3")
