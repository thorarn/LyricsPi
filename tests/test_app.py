import logging
from pathlib import Path
from unittest.mock import Mock

import pygame
import pytest

from lyricspi import Action
from lyricspi import app
from lyricspi.app import AppState, run
from lyricspi.config import Config, DisplayConfig, SongsConfig, SystemConfig
from lyricspi.renderer import Renderer
from lyricspi.song_loader import SongLoadIssue


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


@pytest.mark.parametrize(
    ("source", "issue"),
    [
        ("valid", None),
        ("missing", SongLoadIssue.DIRECTORY_MISSING),
        ("empty", SongLoadIssue.NO_SONGS),
        ("usb", SongLoadIssue.USB_MISSING),
    ],
)
def test_app_loads_setlist_once_and_draws_startup_notice(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
    source: str,
    issue: SongLoadIssue | None,
) -> None:
    directory = tmp_path / source
    if source in ("valid", "empty"):
        directory.mkdir()
    if source == "valid":
        (directory / "1_Demo.txt").write_text("Lied", encoding="utf-8")
    config = Config(
        songs=SongsConfig(
            directory=str(directory),
            source_mode="usb" if source == "usb" else "directory",
        )
    )
    load = Mock(wraps=app.load_setlist)
    monkeypatch.setattr(app, "load_setlist", load)
    monkeypatch.setattr("lyricspi.song_loader._usb_roots", lambda config: [])
    monkeypatch.setenv("SDL_VIDEODRIVER", "dummy")
    monkeypatch.setattr(
        pygame.event, "get", lambda: [pygame.event.Event(pygame.QUIT)]
    )
    draw = Mock(wraps=Renderer.draw)

    # Mock the unbound method via a function so it still receives the instance.
    def draw_frame(
        renderer: Renderer, font_size: int, notice: str | None
    ) -> None:
        draw(renderer, font_size, notice)

    monkeypatch.setattr(Renderer, "draw", draw_frame)
    with caplog.at_level(logging.DEBUG, logger="lyricspi.app"):
        run(config)

    load.assert_called_once_with(config.songs)
    draw.assert_called_once()
    assert draw.call_args.args[1:] == (48, issue.value if issue else None)
    if issue:
        assert "0 Songs geladen." in caplog.text
    else:
        assert "1 Songs geladen." in caplog.text
        assert "Erster Song: Demo (1_Demo.txt)" in caplog.text
