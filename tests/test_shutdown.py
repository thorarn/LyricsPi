import subprocess
from unittest.mock import Mock

import pytest

from lyricspi import shutdown


@pytest.mark.parametrize("platform", ["win32", "darwin"])
def test_poweroff_is_linux_only(monkeypatch: pytest.MonkeyPatch, platform: str) -> None:
    runner = Mock()
    monkeypatch.setattr(shutdown, "platform", platform)
    monkeypatch.setattr(shutdown.subprocess, "run", runner)
    shutdown.request_shutdown()
    runner.assert_not_called()


def test_linux_poweroff_uses_fixed_noninteractive_logind_call(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runner = Mock()
    monkeypatch.setattr(shutdown, "platform", "linux")
    monkeypatch.setattr(shutdown.subprocess, "run", runner)
    shutdown.request_shutdown()
    runner.assert_called_once_with(
        (
            "busctl", "--system", "--timeout=5s", "call",
            "org.freedesktop.login1", "/org/freedesktop/login1",
            "org.freedesktop.login1.Manager", "PowerOff", "b", "false",
        ),
        check=True, capture_output=True, text=True, timeout=6,
    )


@pytest.mark.parametrize("error", [
    FileNotFoundError("busctl fehlt"),
    subprocess.TimeoutExpired("busctl", 6),
    subprocess.CalledProcessError(1, "busctl", stderr="Access denied"),
])
def test_poweroff_failures_are_logged_without_retry(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
    error: Exception,
) -> None:
    runner = Mock(side_effect=error)
    monkeypatch.setattr(shutdown, "platform", "linux")
    monkeypatch.setattr(shutdown.subprocess, "run", runner)
    shutdown.request_shutdown()
    runner.assert_called_once()
    assert "Linux-Shutdown fehlgeschlagen" in caplog.text
