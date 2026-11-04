"""Builds a release with scripts/build_release.sh and installs from it over file://."""

import subprocess
import tarfile
import zipfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
CONFIGS = ["caddy-google", "caddy-idp", "localhost", "nginx-google", "nginx-host"]
EPOCH = "1700000000"


def run(args, cwd=None, env=None, stdin=None):
    return subprocess.run(args, cwd=cwd, env=env, input=stdin, capture_output=True, text=True, check=False)


def build(out: Path):
    result = run(
        ["sh", str(ROOT / "scripts" / "build_release.sh"), "1.2.3", str(out)],
        env={"PATH": "/usr/bin:/bin:/usr/local/bin", "SOURCE_DATE_EPOCH": EPOCH, "HOME": str(out.parent)},
    )
    assert result.returncode == 0, result.stderr
    return out


@pytest.fixture(scope="module")
def dist(tmp_path_factory):
    return build(tmp_path_factory.mktemp("release") / "dist")


def install_env(dist, tmp_path):
    return {
        "PATH": "/usr/bin:/bin:/usr/local/bin",
        "HOME": str(tmp_path),
        "PRIVACYFENCE_SUITE_BASE_URL": f"file://{dist}",
    }


def test_asset_list(dist):
    expected = {"install.sh", "SHA256SUMS"}
    for config in CONFIGS:
        expected |= {f"privacyfence-suite-{config}.tar.gz", f"privacyfence-suite-{config}.zip"}
    assert {p.name for p in dist.iterdir()} == expected


def test_archives_come_from_git_not_the_working_tree(dist, tmp_path):
    """A local edit to a tracked file must not reach an archive (the build exports HEAD)."""
    readme = ROOT / "README.md"
    original = readme.read_bytes()
    out = tmp_path / "dist"
    try:
        readme.write_bytes(original + b"\nLOCAL EDIT NOT COMMITTED\n")
        build(out)
    finally:
        readme.write_bytes(original)
    with tarfile.open(out / "privacyfence-suite-localhost.tar.gz") as tar:
        member = tar.extractfile("privacyfence-localhost/README.md")
        assert member is not None
        assert b"LOCAL EDIT NOT COMMITTED" not in member.read()
    assert (out / "privacyfence-suite-localhost.tar.gz").read_bytes() == (
        dist / "privacyfence-suite-localhost.tar.gz"
    ).read_bytes()


def test_checksums(dist):
    result = run(["sha256sum", "-c", "SHA256SUMS"], cwd=dist)
    assert result.returncode == 0, result.stdout + result.stderr


def test_reproducible(dist, tmp_path):
    second = build(tmp_path / "dist")
    for config in CONFIGS:
        name = f"privacyfence-suite-{config}.tar.gz"
        assert (dist / name).read_bytes() == (second / name).read_bytes()


def members(dist, config):
    with tarfile.open(dist / f"privacyfence-suite-{config}.tar.gz") as tar:
        tar_names = tar.getnames()
        version = tar.extractfile(f"privacyfence-{config}/VERSION").read().decode().strip()
    with zipfile.ZipFile(dist / f"privacyfence-suite-{config}.zip") as z:
        zip_names = [n.rstrip("/") for n in z.namelist()]
    return tar_names, zip_names, version


@pytest.mark.parametrize("config", CONFIGS)
def test_archive_contents(dist, config):
    top = f"privacyfence-{config}"
    tar_names, zip_names, version = members(dist, config)
    assert version == "1.2.3"
    for names in (tar_names, zip_names):
        for name in names:
            assert name == top or name.startswith(top + "/"), name
        for required in ("compose.yaml", ".env.example", "init.sh", "VERSION", "README.md", "LICENSE"):
            assert f"{top}/{required}" in names, required
        for name in names:
            base = name.rsplit("/", 1)[-1]
            assert base != ".env", name
            assert not base.endswith(".pem"), name
            if "/secrets/" in name:
                assert base in (".gitkeep", "README.md"), name


def test_install_script_is_stamped(dist):
    text = (dist / "install.sh").read_text()
    assert "1.2.3" in text
    assert "@VERSION@" not in text
    assert "@CONFIGS@" not in text
    assert text.rstrip("\n").splitlines()[-1] == 'main "$@"'


def test_install_fresh_and_upgrade(dist, tmp_path):
    env = install_env(dist, tmp_path)
    target = tmp_path / "X"
    result = run(["sh", str(dist / "install.sh"), "localhost", "--dir", str(target)], env=env)
    assert result.returncode == 0, result.stderr
    assert (target / ".env").read_bytes() == (target / ".env.example").read_bytes()
    assert (target / "init.sh").read_bytes() == (ROOT / "common" / "init.sh").read_bytes()
    assert "docker compose logs privacyfence" in result.stdout

    again = run(["sh", str(dist / "install.sh"), "localhost", "--dir", str(target)], env=env)
    assert again.returncode == 1
    assert f"install: {target} exists; use --upgrade to update it" in again.stderr

    # piping the script to sh
    piped_dir = tmp_path / "Y"
    piped = run(
        ["sh", "-s", "--", "caddy-idp", "--dir", str(piped_dir)],
        env=env,
        stdin=(dist / "install.sh").read_text(),
    )
    assert piped.returncode == 0, piped.stderr
    assert "secrets/idp_client_secret" in piped.stdout

    (target / ".env").write_text("EDITED=1\n")
    (piped_dir / "secrets" / "idp_client_secret").write_text("not-a-real-secret\n")
    up_x = run(["sh", str(dist / "install.sh"), "localhost", "--dir", str(target), "--upgrade"], env=env)
    assert up_x.returncode == 0, up_x.stderr
    assert "upgraded 1.2.3 -> 1.2.3" in up_x.stdout
    up_y = run(["sh", str(dist / "install.sh"), "caddy-idp", "--dir", str(piped_dir), "--upgrade"], env=env)
    assert up_y.returncode == 0, up_y.stderr
    assert (target / ".env").read_text() == "EDITED=1\n"
    assert (piped_dir / "secrets" / "idp_client_secret").read_text() == "not-a-real-secret\n"

    host_dir = tmp_path / "H"
    host = run(["sh", str(dist / "install.sh"), "nginx-host", "--dir", str(host_dir)], env=env)
    assert host.returncode == 0, host.stderr
    assert (host_dir / "privacyfence.env").read_bytes() == (host_dir / "privacyfence.env.example").read_bytes()
    assert (host_dir / "privacyfence.env").stat().st_mode & 0o777 == 0o600
    assert (host_dir / "nginx" / "render.sh").stat().st_mode & 0o111
    assert "nginx/render.sh" in host.stdout
    (host_dir / "privacyfence.env").write_text("PRIVACYFENCE_MODE=org\n")
    up_h = run(["sh", str(dist / "install.sh"), "nginx-host", "--dir", str(host_dir), "--upgrade"], env=env)
    assert up_h.returncode == 0, up_h.stderr
    assert (host_dir / "privacyfence.env").read_text() == "PRIVACYFENCE_MODE=org\n"

    not_suite = tmp_path / "empty"
    not_suite.mkdir()
    bad = run(["sh", str(dist / "install.sh"), "localhost", "--dir", str(not_suite), "--upgrade"], env=env)
    assert bad.returncode == 1
    assert "is not a suite folder" in bad.stderr


def test_tampered_archive(dist, tmp_path):
    mirror = tmp_path / "mirror"
    mirror.mkdir()
    for path in dist.iterdir():
        (mirror / path.name).write_bytes(path.read_bytes())
    with (mirror / "privacyfence-suite-localhost.tar.gz").open("ab") as f:
        f.write(b"tampered")
    env = install_env(mirror, tmp_path)
    target = tmp_path / "T"
    result = run(["sh", str(mirror / "install.sh"), "localhost", "--dir", str(target)], env=env)
    assert result.returncode == 1
    assert "checksum mismatch" in result.stderr
    assert not target.exists()


@pytest.mark.parametrize("args", [[], ["nope"]])
def test_usage_errors(dist, tmp_path, args):
    result = run(["sh", str(dist / "install.sh"), *args], env=install_env(dist, tmp_path), cwd=tmp_path)
    assert result.returncode == 2
    output = result.stdout + result.stderr
    assert "usage:" in output
    for config in CONFIGS:
        assert config in output


def test_truncated_script_changes_nothing(dist, tmp_path):
    text = (dist / "install.sh").read_text()
    work = tmp_path / "work"
    work.mkdir()
    result = run(
        ["sh", "-s", "--", "localhost"],
        env=install_env(dist, tmp_path),
        cwd=work,
        stdin=text[: len(text) // 2],
    )
    assert result.returncode != 0
    assert list(work.iterdir()) == []
    assert not (tmp_path / "privacyfence-localhost").exists()
