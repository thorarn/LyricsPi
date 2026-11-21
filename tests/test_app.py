import logging
from pathlib import Path
from unittest.mock import Mock

import pygame
import pytest

from lyricspi import Action
from lyricspi import app
from lyricspi.app import AppState, run
from lyricspi.config import (
    Config,
    DisplayConfig,
    InputConfig,
    SongsConfig,
    SystemConfig,
)
from lyricspi.layout import Page
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


def test_song_draws_resizes_logs_navigation_and_exits(
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
            [pygame.event.Event(pygame.KEYDOWN, key=pygame.K_LEFT)],
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
        run(Config(input=InputConfig(enable_combinations=False)))

    original, larger, second, restored = screens
    assert original.get_size() == (1280, 720)
    assert original.get_at((0, 0)) == pygame.Color("#000000")
    image_bytes = pygame.image.tobytes(original, "RGB")
    assert any(
        image_bytes[index : index + 3] == b"\xff\xff\xff"
        for index in range(0, len(image_bytes), 3)
    )
    assert image_bytes != pygame.image.tobytes(larger, "RGB")
    second_bytes = pygame.image.tobytes(second, "RGB")
    assert second_bytes != pygame.image.tobytes(larger, "RGB")
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
        renderer: Renderer, font_size: int, page: Page, notice: str | None
    ) -> None:
        draw(renderer, font_size, page, notice)

    monkeypatch.setattr(Renderer, "draw", draw_frame)
    with caplog.at_level(logging.DEBUG, logger="lyricspi.app"):
        run(config)

    load.assert_called_once_with(config.songs)
    draw.assert_called_once()
    if issue:
        assert draw.call_args.args[1:] == (48, (), issue.value)
    else:
        assert draw.call_args.args[1:] == (48, ("Lied",), None)
    assert not pygame.display.get_init()
    if issue:
        assert "0 Songs geladen." in caplog.text
    else:
        assert "1 Songs geladen." in caplog.text
        assert "Erster Song: Demo (1_Demo.txt)" in caplog.text


def test_page_layout_follows_font_and_window_changes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    first_lines = tuple(f"Erste Zeile {index}" for index in range(12))
    (tmp_path / "1_Erster_Titel.txt").write_text(
        "\n".join(first_lines), encoding="utf-8"
    )
    second_song = tmp_path / "2_Zweiter_Titel.txt"
    second_song.write_text("Zweiter Text", encoding="utf-8")
    monkeypatch.setenv("SDL_VIDEODRIVER", "dummy")
    steps = iter(
        [
            ([pygame.K_DOWN], None),
            ([pygame.K_UP], None),
            ([pygame.K_DOWN] * 20, None),
            ([pygame.K_DOWN, pygame.K_MINUS], None),
            ([], (640, 720)),
            ([], (10, 5)),
            ([], (640, 720)),
            ([pygame.K_RIGHT], None),
            ([pygame.K_RIGHT], None),
            ([pygame.K_LEFT], None),
            ([pygame.K_ESCAPE], None),
        ]
    )
    frames: list[tuple[int, Page, str | None]] = []
    original_draw = Renderer.draw

    def draw(
        renderer: Renderer, size: int, page: Page, notice: str | None
    ) -> None:
        original_draw(renderer, size, page, notice)
        frames.append((size, page, notice))

    def get_events() -> list[pygame.event.Event]:
        keys, size = next(steps)
        events = [
            pygame.event.Event(event_type, key=key)
            for key in keys
            for event_type in (pygame.KEYDOWN, pygame.KEYUP)
        ]
        if size is not None:
            # The dummy driver needs an explicit change to the drawing surface.
            pygame.display.set_mode(size, pygame.RESIZABLE)
            events.append(
                pygame.event.Event(
                    pygame.WINDOWSIZECHANGED, x=size[0], y=size[1]
                )
            )
        return events

    monkeypatch.setattr(Renderer, "draw", draw)
    monkeypatch.setattr(pygame.event, "get", get_events)
    display = DisplayConfig(window_width=640, window_height=160, font_step=24)
    run(Config(
        display=display,
        songs=SongsConfig(directory=str(tmp_path)),
        input=InputConfig(enable_combinations=False),
    ))

    (
        start, second, previous, end, smaller, expanded, tiny, recovered,
        next_song, wrapped, back,
    ) = frames
    assert start == previous
    assert start[1][0] == first_lines[0]
    assert second[1][0] == first_lines[len(start[1])]
    assert end[1][-1] == smaller[1][-1] == first_lines[-1]
    assert smaller[0] == 24
    assert expanded == recovered == wrapped == (24, first_lines, None)
    assert tiny == (24, (), app.SMALL_WINDOW_NOTICE)
    assert next_song == back == (24, ("Zweiter Text",), None)


def test_renderer_keeps_all_glyphs_inside_content_area(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("SDL_VIDEODRIVER", "dummy")
    config = DisplayConfig(
        window_width=240, window_height=180, margin_percent=10
    )
    try:
        renderer = Renderer(config)
        pages = renderer.layout("ÄgWp" * 40 + "\n  Am    C\nGrüße", 36)
        assert len(pages) > 1
        for page in pages:
            renderer.draw(36, page)
            mask = pygame.mask.from_threshold(
                renderer.screen, (0, 0, 0, 255), (1, 1, 1, 255)
            )
            mask.invert()
            glyph_bounds = mask.get_bounding_rects()
            assert glyph_bounds
            assert all(
                renderer._content_area().contains(bounds)
                for bounds in glyph_bounds
            )
    finally:
        pygame.quit()


def test_default_hid_combinations_and_delayed_navigation_use_app_actions(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    (tmp_path / "1_Erstes_Lied.txt").write_text("Erstes Lied", encoding="utf-8")
    (tmp_path / "2_Zweites_Lied.txt").write_text("Zweites Lied", encoding="utf-8")
    monkeypatch.setenv("SDL_VIDEODRIVER", "dummy")
    up, down, left, right = pygame.K_UP, pygame.K_DOWN, pygame.K_LEFT, pygame.K_RIGHT
    press, release = pygame.KEYDOWN, pygame.KEYUP
    now_ms = 0
    steps = iter(
        [
            (0, [(press, up)]),
            (80, [(press, left)]),
            (100, [(release, up), (release, left)]),
            (260, [(press, right)]),
            (300, [(press, down)]),
            (330, [(release, right), (release, down)]),
            (500, [(press, right), (release, right)]),
            (649, []),
            (650, []),
            (700, [(press, pygame.K_ESCAPE)]),
        ]
    )
    original_draw = Renderer.draw
    frames: list[tuple[int, Page]] = []

    def capture(
        renderer: Renderer, size: int, page: Page, notice: str | None
    ) -> None:
        original_draw(renderer, size, page, notice)
        frames.append((size, page))

    def get_events() -> list[pygame.event.Event]:
        nonlocal now_ms
        now_ms, events = next(steps)
        return [
            pygame.event.Event(event_type, key=key)
            for event_type, key in events
        ]

    monkeypatch.setattr(Renderer, "draw", capture)
    monkeypatch.setattr(pygame.event, "get", get_events)
    monkeypatch.setattr(app, "monotonic_ns", lambda: now_ms * 1_000_000)
    with caplog.at_level(logging.DEBUG, logger="lyricspi.app"):
        run(Config(songs=SongsConfig(directory=str(tmp_path))))

    initial, smaller, restored, next_song = frames
    assert initial == restored
    assert smaller == (44, initial[1])
    assert next_song[0] == 48
    assert next_song[1] != initial[1]
    assert [
        record.getMessage() for record in caplog.records
        if record.getMessage().startswith("Tastaturaktion")
    ] == [
        "Tastaturaktion: FONT_SMALLER",
        "Tastaturaktion: FONT_LARGER",
        "Tastaturaktion: NEXT_SONG",
        "Tastaturaktion: EXIT",
    ]
