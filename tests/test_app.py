import logging

import pygame
import pytest

from lyricspi import Action
from lyricspi.app import AppState, run
from lyricspi.config import Config, DisplayConfig, SystemConfig


@pytest.mark.parametrize(
    ("action", "initial_size", "expected_size"),
    [
        (Action.FONT_LARGER, 48, 52),
        (Action.FONT_SMALLER, 48, 44),
        (Action.FONT_SMALLER, 25, 24),
        (Action.FONT_LARGER, 95, 96),
        (Action.NEXT_SONG, 48, 48),
    ],
)
def test_applies_action_to_state(
    action: Action, initial_size: int, expected_size: int
) -> None:
    state = AppState(initial_size, development_mode=True)

    state.apply_action(action, DisplayConfig())

    assert state.font_size == expected_size
    assert state.last_action is action
    assert state.running


def test_exit_stops_application_state() -> None:
    state = AppState(48, development_mode=True)

    state.apply_action(Action.EXIT, DisplayConfig())

    assert not state.running
    assert state.last_action is Action.EXIT


def test_demo_draws_resizes_logs_navigation_and_exits(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    monkeypatch.setenv("SDL_VIDEODRIVER", "dummy")
    batches = iter(
        [
            [
                pygame.event.Event(pygame.KEYDOWN, key=pygame.K_RIGHT),
                pygame.event.Event(pygame.KEYDOWN, key=pygame.K_PLUS),
            ],
            [pygame.event.Event(pygame.KEYDOWN, key=pygame.K_MINUS)],
            [pygame.event.Event(pygame.KEYDOWN, key=pygame.K_ESCAPE)],
        ]
    )
    screens: list[pygame.Surface] = []

    def get_events() -> list[pygame.event.Event]:
        screen = pygame.display.get_surface()
        assert screen is not None
        screens.append(screen.copy())
        return next(batches)

    monkeypatch.setattr(pygame.event, "get", get_events)
    with caplog.at_level(logging.DEBUG, logger="lyricspi.app"):
        run(Config())

    original, larger, restored = screens
    assert original.get_size() == (1280, 720)
    assert original.get_at((0, 0)) == pygame.Color("#000000")
    image_bytes = pygame.image.tobytes(original, "RGB")
    assert any(
        image_bytes[index : index + 3] == b"\xff\xff\xff"
        for index in range(0, len(image_bytes), 3)
    )
    assert image_bytes != pygame.image.tobytes(larger, "RGB")
    assert image_bytes == pygame.image.tobytes(restored, "RGB")
    assert "Tastaturaktion: NEXT_SONG" in caplog.text
    assert "Tastaturaktion: EXIT" in caplog.text
    assert not pygame.display.get_init()
    assert not pygame.font.get_init()


@pytest.mark.parametrize(
    "system",
    [SystemConfig(development_mode=False), SystemConfig(allow_keyboard=False)],
)
def test_escape_gate_allows_window_close(
    monkeypatch: pytest.MonkeyPatch, system: SystemConfig
) -> None:
    monkeypatch.setenv("SDL_VIDEODRIVER", "dummy")
    batches = iter(
        [
            [pygame.event.Event(pygame.KEYDOWN, key=pygame.K_ESCAPE)],
            [pygame.event.Event(pygame.QUIT)],
        ]
    )
    monkeypatch.setattr(pygame.event, "get", lambda: next(batches))

    run(Config(system=system))

    assert next(batches, None) is None


def test_configured_fullscreen_uses_desktop_resolution(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("SDL_VIDEODRIVER", "dummy")

    def get_events() -> list[pygame.event.Event]:
        screen = pygame.display.get_surface()
        assert screen is not None
        assert screen.get_flags() & pygame.FULLSCREEN
        assert screen.get_size() == pygame.display.get_desktop_sizes()[0]
        return [pygame.event.Event(pygame.QUIT)]

    monkeypatch.setattr(pygame.event, "get", get_events)
    run(Config(display=DisplayConfig(fullscreen=True)))
