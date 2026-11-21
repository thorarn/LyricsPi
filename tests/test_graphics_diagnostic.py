import logging

import pygame
import pytest

from tools import graphics_diagnostic as diagnostic


@pytest.fixture(autouse=True)
def dummy_display(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SDL_VIDEODRIVER", "dummy")
    monkeypatch.setattr(diagnostic, "log_linux_resources", lambda: None)


def test_diagnostic_draws_test_image_and_quits(caplog: pytest.LogCaptureFixture) -> None:
    with caplog.at_level(logging.INFO, logger=diagnostic.LOGGER.name):
        assert diagnostic.main(["--windowed", "--seconds", "0"]) == 0

    assert "Aktiver SDL-Treiber: dummy" in caplog.text
    assert "Testbild ausgegeben: 640 × 360" in caplog.text
    assert not pygame.display.get_init()


def test_report_only_logs_selected_driver_and_card_without_initializing(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    monkeypatch.delenv("SDL_KMSDRM_DEVICE_INDEX", raising=False)
    monkeypatch.setenv("SDL_KMSDRM_DEVICE_INDEX", "0")
    with caplog.at_level(logging.INFO, logger=diagnostic.LOGGER.name):
        assert diagnostic.main(["--report-only", "--driver", "kmsdrm", "--card", "1"]) == 0

    assert "SDL_VIDEODRIVER=kmsdrm" in caplog.text
    assert "SDL_KMSDRM_DEVICE_INDEX=1" in caplog.text
    assert not pygame.display.get_init()


def test_diagnostic_logs_egl_failure_with_traceback(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    def fail(*args) -> None:
        raise pygame.error("EGL not initialized")

    monkeypatch.setattr(pygame.display, "set_mode", fail)
    assert diagnostic.main(["--seconds", "0"]) == 1
    assert "Traceback" in caplog.text
    assert "EGL not initialized" in caplog.text
    assert not pygame.display.get_init()
