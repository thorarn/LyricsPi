import os
import shutil
import subprocess
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="module")
def bash() -> str:
    if os.name == "nt":
        git = shutil.which("git")
        if git:
            git_bash = Path(git).resolve().parents[1] / "bin" / "bash.exe"
            if git_bash.is_file():
                return str(git_bash)
        executable = shutil.which("bash")
        if executable and "system32" not in executable.lower():
            return executable
    else:
        executable = shutil.which("bash")
        if executable:
            return executable
    pytest.skip("Bash or Git Bash is required to exercise the deployment script")


def shell(
    bash: str, command: str, *args: str
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [bash, "-c", f"source ./deploy/install.sh; {command}", "test", *args],
        cwd=ROOT,
        capture_output=True,
        encoding="utf-8",
        timeout=10,
    )


@pytest.mark.parametrize(
    "model,machine,release",
    [
        ("Raspberry Pi 2 Model B Rev 1.1", "armv7l", "trixie"),
        ("Raspberry Pi 2 Model B Rev 1.2", "armv7l", "bookworm"),
        ("Raspberry Pi 2 Model B Revision 1.3", "armv7l", "trixie"),
        ("Raspberry Pi 2 Model B", "armv7l", "bookworm"),
        ("Raspberry Pi 3 Model B Rev 1.2", "armv7l", "trixie"),
        ("Raspberry Pi 3 Model B+ Rev 1.3", "aarch64", "bookworm"),
        ("Raspberry Pi 3 Model B Plus", "armv8l", "trixie"),
        ("Raspberry Pi 3 Model A+", "armv7l", "trixie"),
    ],
)
def test_supported_platforms(
    bash: str, model: str, machine: str, release: str
) -> None:
    result = shell(bash, 'check_platform "$@"', model, machine, "armhf", "32", release)
    assert result.returncode == 0, result.stderr


@pytest.mark.parametrize(
    "model,machine,architecture,bits,release,message",
    [
        ("", "armv7l", "armhf", "32", "trixie", "Modellinformationen"),
        ("   ", "armv7l", "armhf", "32", "trixie", "Modellinformationen"),
        ("Raspberry Pi 4 Model B", "armv7l", "armhf", "32", "trixie", "Nicht unterstütztes Modell"),
        ("Raspberry Pi 2 Model B", "armv6l", "armhf", "32", "trixie", "ARMv7"),
        ("Raspberry Pi 3 Model B+", "aarch64", "arm64", "64", "trixie", "32 Bit"),
        ("Raspberry Pi 3 Model B", "aarch64", "armhf", "64", "bookworm", "32 Bit"),
        ("Raspberry Pi 2 Model B", "armv7l", "armhf", "32", "bullseye", "Trixie oder Bookworm"),
    ],
)
def test_unsupported_platforms_are_diagnosed(
    bash: str, model: str, machine: str, architecture: str, bits: str,
    release: str, message: str,
) -> None:
    result = shell(bash, 'check_platform "$@"', model, machine, architecture, bits, release)
    assert result.returncode == 1
    assert message in result.stderr


@pytest.mark.parametrize(
    "version,expected",
    [("3.10.19", 1), ("3.11.2", 0), ("3.13.5", 0), ("3.14.0", 0), ("unknown", 1)],
)
def test_python_version_check(bash: str, version: str, expected: int) -> None:
    result = shell(bash, 'check_python_version "$@"', version)
    assert result.returncode == expected
    if expected:
        assert "Python 3.11" in result.stderr


@pytest.mark.parametrize(
    "release,font", [("trixie", "fonts-dejavu-mono"), ("bookworm", "fonts-dejavu-core")]
)
def test_armhf_package_profiles(bash: str, release: str, font: str) -> None:
    result = shell(bash, 'system_packages "$@"', release)
    assert result.returncode == 0, result.stderr
    packages = set(result.stdout.splitlines())
    assert {"python3", "python3-pygame", "python3-venv", "python3-setuptools", font} <= packages
    assert {name for name in packages if name.startswith("fonts-")} == {font}


def test_package_check_skips_installed_packages(bash: str) -> None:
    result = shell(
        bash,
        'dpkg-query() { case "${@: -1}" in python3) printf installed;; '
        'python3-venv) printf config-files;; *) return 1;; esac; }; '
        'missing_packages python3 python3-venv python3-pygame',
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout.splitlines() == ["python3-venv", "python3-pygame"]


def test_identical_deployment_can_be_reused(bash: str, tmp_path: Path) -> None:
    current = tmp_path / "current"
    staged = tmp_path / "staged"
    for directory in (current, staged / "app"):
        for folder in ("src", "assets", "demo_songs", "config"):
            (directory / folder).mkdir(parents=True)
        for name in ("README.md", "pyproject.toml", "config/config.example.json", "config/config.json"):
            (directory / name).write_text("same", encoding="utf-8")
    (current / "src" / "__pycache__").mkdir()
    unit = current / "lyricspi.service"
    unit.write_text("same unit", encoding="utf-8")
    staged_unit = staged / unit.name
    staged_unit.write_text("same unit", encoding="utf-8")
    args = (current.as_posix(), staged.as_posix(), unit.as_posix())

    identical = shell(bash, 'deployment_matches "$@"', *args)
    assert identical.returncode == 0, identical.stderr
    staged_unit.write_text("changed unit", encoding="utf-8")
    assert shell(bash, 'deployment_matches "$@"', *args).returncode == 1
