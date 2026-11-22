import json
import logging
from pathlib import Path
from unittest.mock import Mock

import pygame
import pytest

from lyricspi import Action, View
from lyricspi import app
from lyricspi.app import AppState, run
from lyricspi.config import (
    Config,
    DisplayConfig,
    SongsConfig,
    SystemConfig,
)
from lyricspi.layout import Page
from lyricspi.renderer import Renderer
from lyricspi.song_loader import SongLoadIssue


@pytest.fixture(autouse=True)
def isolated_display_settings(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    path = tmp_path / "state" / "settings.json"
    monkeypatch.setattr(app, "display_settings_path", lambda: path)
    return path


@pytest.mark.parametrize(
    ("action", "initial_size", "expected_size"),
    [
        (Action.FONT_LARGER, 48, 48),
        (Action.FONT_SMALLER, 48, 44),
        (Action.FONT_SMALLER, 25, 25),
        (Action.FONT_LARGER, 95, 95),
        (Action.NEXT_SONG, 48, 48),
    ],
)
def test_applies_action_to_state(
    action: Action, initial_size: int, expected_size: int
) -> None:
    state = AppState(initial_size, development_mode=True)

    state.apply_action(action)

    assert state.font_size == expected_size
    assert state.last_action is action
    assert state.running


def test_exit_stops_application_state() -> None:
    state = AppState(48, development_mode=True)

    state.apply_action(Action.EXIT)

    assert not state.running
    assert state.last_action is Action.EXIT


@pytest.mark.parametrize(("action", "attribute", "values"), [
    (Action.CYCLE_FONT_SIZE, "font_size", [32, 36, 40, 44, 48, 32, 36]),
    (Action.ROTATE_DISPLAY, "rotation", [0, 90, 180, 270, 0, 90]),
])
def test_display_values_cycle_in_main_menu(action, attribute, values) -> None:
    state = AppState(32, development_mode=True)
    state.apply_action(action)
    assert getattr(state, attribute) == values[0]
    state.apply_action(Action.OPEN_MENU)
    for expected in values[1:]:
        state.apply_action(action)
        assert getattr(state, attribute) == expected


def test_menu_saves_display_settings_immediately_and_restores_them_after_restart(
    tmp_path: Path, isolated_display_settings: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("SDL_VIDEODRIVER", "dummy")
    (tmp_path / "1_Test.txt").write_text("Erste Zeile\nZweite Zeile", encoding="utf-8")
    a, b, c, d = pygame.K_UP, pygame.K_DOWN, pygame.K_LEFT, pygame.K_RIGHT
    down, up = pygame.KEYDOWN, pygame.KEYUP
    batches = iter([
        (0, [(down, a)]),
        (5000, []),
        (5100, [(up, a), (down, a), (up, a)]),
        (5200, [(down, a), (up, a)]),
        (5300, [(down, b), (up, b)]),
        (5400, [(down, c), (up, c)]),
        (5500, [(down, d), (up, d)]),
        (5600, [(down, d), (up, d)]),
        (5700, None),
        (5800, None),
    ])
    held = {}
    now_ms = 0
    frames = []
    draw = app._draw

    def events() -> list[pygame.event.Event]:
        nonlocal now_ms
        now_ms, keys = next(batches)
        if keys is None:
            assert json.loads(isolated_display_settings.read_text()) == {
                "font_size": 40, "rotation": 90,
            }
            return [pygame.event.Event(pygame.QUIT)]
        for event, key in keys:
            held[key] = event == down
        return [pygame.event.Event(event, key=key) for event, key in keys]

    def capture(state, renderer, notice, *, view_page=0):
        frames.append((state.view, state.font_size, renderer.screen.get_size()))
        return draw(state, renderer, notice, view_page=view_page)

    monkeypatch.setattr(pygame.event, "get", events)
    monkeypatch.setattr(pygame.key, "get_focused", lambda: True)
    monkeypatch.setattr(pygame.key, "get_pressed", lambda: held)
    monkeypatch.setattr(app, "monotonic_ns", lambda: now_ms * 1_000_000)
    monkeypatch.setattr(app, "_draw", capture)
    config = Config(
        display=DisplayConfig(window_width=640, window_height=360),
        songs=SongsConfig(directory=str(tmp_path)),
    )
    run(config)
    run(config)

    assert frames == [
        (View.SONG_VIEW, 32, (640, 360)),
        (View.MAIN_MENU, 32, (640, 360)),
        (View.MAIN_MENU, 36, (640, 360)),
        (View.MAIN_MENU, 40, (640, 360)),
        (View.MAIN_MENU, 40, (360, 640)),
        (View.SONG_LIST, 40, (360, 640)),
        (View.MAIN_MENU, 40, (360, 640)),
        (View.SONG_VIEW, 40, (360, 640)),
        (View.SONG_VIEW, 40, (360, 640)),
    ]


def test_song_draws_resizes_logs_navigation_and_exits(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    (tmp_path / "01_Erster.txt").write_text("Erster Songtext", encoding="utf-8")
    (tmp_path / "02_Zweiter.txt").write_text("Zweiter Songtext", encoding="utf-8")
    monkeypatch.setenv("SDL_VIDEODRIVER", "dummy")
    monkeypatch.setattr(app, "platform", "win32")
    batches = iter(
        [
            [
                pygame.event.Event(pygame.KEYDOWN, key=pygame.K_DOWN),
                pygame.event.Event(pygame.KEYUP, key=pygame.K_DOWN),
                pygame.event.Event(pygame.KEYDOWN, key=pygame.K_PLUS),
            ],
            [pygame.event.Event(pygame.KEYDOWN, key=pygame.K_MINUS)],
            [
                pygame.event.Event(pygame.KEYDOWN, key=pygame.K_UP),
                pygame.event.Event(pygame.KEYUP, key=pygame.K_UP),
            ],
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
        run(Config(songs=SongsConfig(directory=str(tmp_path))))

    original, larger, second, restored = screens
    assert original.get_size() == (1280, 720)
    assert original.get_at((0, 0)) == pygame.Color("#000000")
    image_bytes = pygame.image.tostring(original, "RGB")
    assert any(
        image_bytes[index : index + 3] == b"\xff\xff\xff"
        for index in range(0, len(image_bytes), 3)
    )
    assert image_bytes != pygame.image.tostring(larger, "RGB")
    second_bytes = pygame.image.tostring(second, "RGB")
    assert second_bytes != pygame.image.tostring(larger, "RGB")
    assert image_bytes == pygame.image.tostring(restored, "RGB")
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
    monkeypatch.setattr(app, "platform", "win32")
    batches = iter(
        [
            [pygame.event.Event(pygame.KEYDOWN, key=pygame.K_ESCAPE)],
            [pygame.event.Event(pygame.QUIT)],
        ]
    )
    monkeypatch.setattr(pygame.event, "get", lambda: next(batches))

    run(Config(system=system))

    assert next(batches, None) is None


def test_escape_is_ignored_in_linux_development_mode(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("SDL_VIDEODRIVER", "dummy")
    monkeypatch.setattr(app, "platform", "linux")
    batches = iter([
        [pygame.event.Event(pygame.KEYDOWN, key=pygame.K_ESCAPE)],
        [pygame.event.Event(pygame.QUIT)],
    ])
    monkeypatch.setattr(pygame.event, "get", lambda: next(batches))

    run(Config())

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
        renderer: Renderer, font_size: int, page: Page, notice: str | None,
        **song_view,
    ) -> None:
        draw(renderer, font_size, page, notice, **song_view)

    monkeypatch.setattr(Renderer, "draw", draw_frame)
    with caplog.at_level(logging.DEBUG, logger="lyricspi.app"):
        run(config)

    load.assert_called_once_with(config.songs)
    draw.assert_called_once()
    if issue:
        assert draw.call_args.args[1:] == (32, (), issue.value)
        assert draw.call_args.kwargs["song"] is None
    else:
        assert draw.call_args.args[1:] == (32, ("Lied",), None)
        assert draw.call_args.kwargs["song"].title == "Demo"
        assert draw.call_args.kwargs["page_count"] == 1
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
            ([pygame.K_RIGHT], None),
            ([pygame.K_LEFT], None),
            ([pygame.K_RIGHT] * 20, None),
            ([pygame.K_RIGHT, pygame.K_MINUS], None),
            ([], (640, 720)),
            ([], (10, 5)),
            ([], (640, 720)),
            ([pygame.K_DOWN], None),
            ([pygame.K_DOWN], None),
            ([pygame.K_UP], None),
            (None, None),
        ]
    )
    frames: list[tuple[int, Page, str | None]] = []
    positions: list[tuple[int, int]] = []
    original_draw = Renderer.draw

    def draw(
        renderer: Renderer, size: int, page: Page, notice: str | None,
        **song_view,
    ) -> None:
        original_draw(renderer, size, page, notice, **song_view)
        frames.append((size, page, notice))
        positions.append((song_view["page_index"], song_view["page_count"]))

    def get_events() -> list[pygame.event.Event]:
        keys, size = next(steps)
        if keys is None:
            return [pygame.event.Event(pygame.QUIT)]
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
    display = DisplayConfig(window_width=640, window_height=160, font_size=36)
    run(Config(
        display=display,
        songs=SongsConfig(directory=str(tmp_path)),
    ))

    (
        start, second, previous, end, smaller, expanded, tiny, recovered,
        next_song, wrapped, back,
    ) = frames
    assert start == previous
    assert start[1][0] == first_lines[0]
    assert second[1][0] == first_lines[len(start[1])]
    assert end[1][-1] == smaller[1][-1] == first_lines[-1]
    assert smaller[0] == 32
    assert expanded == recovered == wrapped == (32, first_lines, None)
    assert tiny == (32, (), app.SMALL_WINDOW_NOTICE)
    assert next_song == back == (32, ("Zweiter Text",), None)
    assert positions[0][0] == 0
    assert positions[1][0] == 1
    assert positions[3][0] == positions[3][1] - 1
    assert positions[-1] == (0, 1)


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


def test_short_b_changes_song_and_logs_hid_events(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    path = tmp_path / "1_Lied.txt"
    path.write_text("Erste Seite\nZweite Seite", encoding="utf-8")
    (tmp_path / "2_Zweiter.txt").write_text("Zweiter Song", encoding="utf-8")
    monkeypatch.setenv("SDL_VIDEODRIVER", "dummy")
    batches = iter([
        [pygame.event.Event(pygame.KEYDOWN, key=pygame.K_DOWN)],
        [pygame.event.Event(pygame.KEYUP, key=pygame.K_DOWN)],
        [pygame.event.Event(pygame.QUIT)],
    ])
    times_ns = iter([0, 200_000_000, 300_000_000])
    pressed = {pygame.K_DOWN: False}

    def events() -> list[pygame.event.Event]:
        batch = next(batches)
        if batch[0].type != pygame.QUIT:
            pressed[pygame.K_DOWN] = batch[0].type == pygame.KEYDOWN
        return batch

    monkeypatch.setattr(pygame.event, "get", events)
    monkeypatch.setattr(pygame.key, "get_pressed", lambda: pressed)
    monkeypatch.setattr(pygame.key, "get_focused", lambda: True)
    monkeypatch.setattr(app, "monotonic_ns", lambda: next(times_ns))
    display = DisplayConfig(window_height=160, line_spacing=150)
    with caplog.at_level(logging.DEBUG, logger="lyricspi"):
        run(Config(display=display, songs=SongsConfig(directory=str(tmp_path))))

    assert [message for message in caplog.messages if message.startswith("Seite ")] == [
        "Seite 1/2",
        "Seite 1/1",
    ]
    assert "KEYDOWN down." in caplog.messages
    assert "KEYUP down nach 200 ms. Aktion NEXT_SONG." in caplog.messages


def test_controller_menu_restores_text_position_and_selects_songs(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    lines = tuple(f"Zeile {number}" for number in range(40))
    for filename, content in (
        ("10_Dritter.txt", "Dritter Song"),
        ("2_Zweiter.txt", "Zweiter Song"),
        ("01_Erster.txt", "\n".join(lines)),
    ):
        (tmp_path / filename).write_text(content, encoding="utf-8")
    monkeypatch.setenv("SDL_VIDEODRIVER", "dummy")
    a, b, c, d = pygame.K_UP, pygame.K_DOWN, pygame.K_LEFT, pygame.K_RIGHT
    down, up = pygame.KEYDOWN, pygame.KEYUP

    def tap(key: int) -> list[tuple[int, int]]:
        return [(down, key), (up, key)]

    steps = iter([
        (100, tap(d)),
        (200, [(down, a)]),
        (5200, []),
        (5300, [(up, a), *tap(a)]),
        (5350, tap(b)),
        (5400, [*tap(c), *tap(b)]),
        (5500, tap(d)),
        (5600, tap(d)),
        (5700, [(down, a)]),
        (10700, []),
        (10800, [(up, a), *tap(c), *tap(b), *tap(b), *tap(a)]),
        (10900, tap(c)),
        (11000, None),
    ])
    pressed: dict[int, bool] = {}
    now_ms = 0
    frames = []
    draw = app._draw

    def events() -> list[pygame.event.Event]:
        nonlocal now_ms
        now_ms, keys = next(steps)
        if keys is None:
            return [pygame.event.Event(pygame.QUIT)]
        batch = []
        for event_type, key in keys:
            pressed[key] = event_type == down
            batch.append(pygame.event.Event(event_type, key=key))
        return batch

    def capture(
        state: AppState, renderer: Renderer, notice: str | None, *,
        view_page: int = 0,
    ) -> int:
        font = Mock(wraps=renderer._font_for_size)
        with monkeypatch.context() as frame_patch:
            frame_patch.setattr(renderer, "_font_for_size", font)
            page_count = draw(state, renderer, notice, view_page=view_page)
        font.assert_called_once_with(state.font_size)
        assert state.song is not None
        frames.append((
            state.view, state.song.title, state.navigation.page_index,
            state.page, state.font_size, state.selected_song, state.rotation,
        ))
        return page_count

    monkeypatch.setattr(app, "_draw", capture)
    monkeypatch.setattr(app, "monotonic_ns", lambda: now_ms * 1_000_000)
    monkeypatch.setattr(pygame.event, "get", events)
    monkeypatch.setattr(pygame.key, "get_focused", lambda: True)
    monkeypatch.setattr(pygame.key, "get_pressed", lambda: pressed)
    run(Config(
        display=DisplayConfig(window_width=640, window_height=320),
        songs=SongsConfig(directory=str(tmp_path)),
    ))

    (
        initial, second_page, main, larger, rotated, song_list, back, resumed,
        reopened, selected, new_song,
    ) = frames
    assert initial[0:3] == (View.SONG_VIEW, "Erster", 0)
    assert second_page[0:3] == (View.SONG_VIEW, "Erster", 1)
    assert main[1:5] == second_page[1:5]
    assert all(
        frame[0] is View.MAIN_MENU for frame in (main, larger, rotated, back, reopened)
    )
    assert (main[4], larger[4], rotated[4]) == (32, 36, 36)
    assert (main[6], larger[6], rotated[6]) == (0, 0, 90)
    assert song_list[0] is selected[0] is View.SONG_LIST
    assert song_list[5] == selected[5] == 1
    assert song_list[1:5] == back[1:5] == rotated[1:5]
    assert all(frame[6] == 90 for frame in (song_list, back, resumed, new_song))
    assert resumed[0:2] == (View.SONG_VIEW, "Erster")
    assert second_page[3][0] in resumed[3]
    assert new_song[0:5] == (View.SONG_VIEW, "Zweiter", 0, ("Zweiter Song",), 36)


def test_small_menu_stays_on_one_page_and_keeps_direct_controls(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("SDL_VIDEODRIVER", "dummy")
    a, c, d = pygame.K_UP, pygame.K_LEFT, pygame.K_RIGHT
    down, up = pygame.KEYDOWN, pygame.KEYUP
    steps = iter([
        (0, [(down, a)]),
        (5000, []),
        (5001, [(up, a)]),
        (5000 + app.VIEW_PAGE_DURATION_MS, []),
        (5001 + app.VIEW_PAGE_DURATION_MS, [(down, c), (up, c)]),
        (5002 + app.VIEW_PAGE_DURATION_MS, [(down, d), (up, d)]),
        (5003 + app.VIEW_PAGE_DURATION_MS, [(down, d), (up, d)]),
        (5004 + app.VIEW_PAGE_DURATION_MS, None),
    ])
    pressed = {}
    now_ms = 0
    shown: list[tuple[View, int]] = []
    draw = app._draw

    def events() -> list[pygame.event.Event]:
        nonlocal now_ms
        now_ms, keys = next(steps)
        if keys is None:
            return [pygame.event.Event(pygame.QUIT)]
        for event_type, key in keys:
            pressed[key] = event_type == down
        return [pygame.event.Event(event_type, key=key) for event_type, key in keys]

    def capture(
        state: AppState, renderer: Renderer, notice: str | None, *,
        view_page: int = 0,
    ) -> int:
        shown.append((state.view, view_page))
        return draw(state, renderer, notice, view_page=view_page)

    monkeypatch.setattr(app, "_draw", capture)
    monkeypatch.setattr(app, "monotonic_ns", lambda: now_ms * 1_000_000)
    monkeypatch.setattr(pygame.event, "get", events)
    monkeypatch.setattr(pygame.key, "get_focused", lambda: True)
    monkeypatch.setattr(pygame.key, "get_pressed", lambda: pressed)
    run(Config(display=DisplayConfig(
        window_width=400, window_height=260, font_size=48,
    )))

    assert shown == [
        (View.SONG_VIEW, 0), (View.MAIN_MENU, 0),
        (View.SONG_LIST, 0), (View.MAIN_MENU, 0), (View.SONG_VIEW, 0),
    ]


def test_empty_song_list_can_be_aborted() -> None:
    state = AppState(48, development_mode=True)
    for action in (
        Action.OPEN_MENU, Action.OPEN_SONG_LIST, Action.SELECT_NEXT,
        Action.SELECT_PREVIOUS, Action.OPEN_SELECTED_SONG,
    ):
        state.apply_action(action)

    assert state.view is View.SONG_LIST
    assert state.song is None
    assert state.selected_song == 0
    state.apply_action(Action.BACK)
    assert state.view is View.MAIN_MENU
    state.apply_action(Action.BACK)
    assert state.view is View.SONG_VIEW


@pytest.mark.parametrize(
    "platform,development_mode,action",
    [
        ("win32", True, Action.EXIT),
        ("win32", False, Action.EXIT),
        ("linux", True, Action.EXIT),
        ("linux", False, Action.SHUTDOWN),
    ],
)
def test_long_b_exits_application_without_system_command(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
    platform: str,
    development_mode: bool,
    action: Action,
) -> None:
    monkeypatch.setenv("SDL_VIDEODRIVER", "dummy")
    monkeypatch.setattr(app, "platform", platform)
    monkeypatch.setattr(pygame.key, "get_focused", lambda: True)
    monkeypatch.setattr(pygame.key, "get_pressed", lambda: {
        pygame.K_DOWN: True,
    })
    monkeypatch.setattr(
        pygame.font, "SysFont", lambda names, size: pygame.font.Font(None, size)
    )
    system = Mock(side_effect=AssertionError("Unexpected OS command"))
    monkeypatch.setattr("os.system", system)
    monkeypatch.setattr("subprocess.Popen", system)
    def after_display_quit() -> None:
        assert not pygame.display.get_init()
        assert not pygame.font.get_init()

    shutdown = Mock(side_effect=after_display_quit)
    monkeypatch.setattr(app, "request_shutdown", shutdown)
    start = [
        pygame.event.Event(pygame.KEYDOWN, key=pygame.K_DOWN),
    ]
    batches = iter([start, [], []])
    times_ns = iter([0, 14_999_000_000, 15_000_000_000])
    monkeypatch.setattr(pygame.event, "get", lambda: next(batches))
    monkeypatch.setattr(app, "monotonic_ns", lambda: next(times_ns))

    with caplog.at_level(logging.DEBUG, logger="lyricspi.app"):
        run(Config(system=SystemConfig(development_mode=development_mode)))

    assert next(times_ns, None) is None
    assert [
        record.getMessage() for record in caplog.records
        if record.getMessage().startswith("Tastaturaktion")
    ] == [f"Tastaturaktion: {action.name}"]
    system.assert_not_called()
    if action is Action.SHUTDOWN:
        shutdown.assert_called_once_with()
    else:
        shutdown.assert_not_called()
    assert not pygame.display.get_init()


@pytest.mark.parametrize("has_logo", [False, True])
def test_splash_transitions_to_song_and_processes_input(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, has_logo: bool
) -> None:
    monkeypatch.setenv("SDL_VIDEODRIVER", "dummy")
    monkeypatch.setattr(app, "PROJECT_ROOT", tmp_path)
    song = tmp_path / "1_Lied.txt"
    song.write_text("Erster Songtext", encoding="utf-8")
    if has_logo:
        logo_path = tmp_path / "assets" / "logo.png"
        logo_path.parent.mkdir()
        image = pygame.Surface((12, 8))
        image.fill((255, 0, 0))
        pygame.image.save(image, str(logo_path))

    batches = iter([
        [pygame.event.Event(pygame.KEYDOWN, key=pygame.K_PLUS)],
        [],
        [pygame.event.Event(pygame.QUIT)],
    ])
    times_ns = iter([0, 200_000_000, 1_500_000_000, 1_600_000_000])
    frames: list[pygame.Surface] = []
    pages: list[tuple[int, Page]] = []
    draw = Renderer.draw

    def capture_page(
        renderer: Renderer, size: int, page: Page, notice: str | None,
        **song_view,
    ) -> None:
        pages.append((size, page))
        draw(renderer, size, page, notice, **song_view)

    def events() -> list[pygame.event.Event]:
        screen = pygame.display.get_surface()
        assert screen is not None
        frames.append(screen.copy())
        return next(batches)

    monkeypatch.setattr(Renderer, "draw", capture_page)
    monkeypatch.setattr(pygame.event, "get", events)
    monkeypatch.setattr(app, "monotonic_ns", lambda: next(times_ns))
    config = Config(
        system=SystemConfig(show_splash=True),
        songs=SongsConfig(directory=str(tmp_path)),
    )
    run(config)

    splash = frames[0]
    assert splash.get_at((0, 0)) == pygame.Color("black")
    pixel_data = pygame.image.tostring(splash, "RGB")
    if has_logo:
        assert splash.get_at(splash.get_rect().center) == pygame.Color("red")
    else:
        assert b"\xff\xff\xff" in pixel_data
    assert pygame.image.tostring(frames[1], "RGB") == pixel_data
    assert pages == [(36, ("Erster Songtext",))]


def test_missing_display_cleans_up(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("SDL_VIDEODRIVER", "dummy")
    monkeypatch.setattr(pygame.display, "get_desktop_sizes", lambda: [])
    with pytest.raises(RuntimeError, match="Kein Bildschirm"):
        run(Config())
    assert not pygame.display.get_init()
    assert not pygame.font.get_init()


def test_kmsdrm_egl_failure_preserves_cause_and_explains_diagnosis(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from lyricspi import renderer as renderer_module

    monkeypatch.setenv("SDL_VIDEODRIVER", "dummy")
    monkeypatch.setenv("SDL_KMSDRM_DEVICE_INDEX", "1")
    monkeypatch.setattr(renderer_module, "platform", "linux")
    monkeypatch.setattr(pygame.display, "get_driver", lambda: "KMSDRM")
    monkeypatch.setattr(pygame.display, "get_desktop_sizes", lambda: [(1920, 1080)])
    failure = pygame.error("EGL not initialized")
    set_mode = Mock(side_effect=failure)
    monkeypatch.setattr(pygame.display, "set_mode", set_mode)

    with pytest.raises(RuntimeError, match=r"KMSDRM.*1920.*EGL not initialized.*graphics_diagnostic") as raised:
        run(Config(display=DisplayConfig(fullscreen=True)))

    assert raised.value.__cause__ is failure
    set_mode.assert_called_once_with((1920, 1080), pygame.FULLSCREEN)
    assert not pygame.display.get_init()


def test_windows_windowed_mode_retains_configured_size_and_flags(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from lyricspi import renderer as renderer_module

    monkeypatch.setenv("SDL_VIDEODRIVER", "dummy")
    monkeypatch.setattr(renderer_module, "platform", "win32")
    set_mode = Mock(wraps=pygame.display.set_mode)
    monkeypatch.setattr(pygame.display, "set_mode", set_mode)
    try:
        Renderer(DisplayConfig(window_width=640, window_height=360), resizable=True)
        set_mode.assert_called_once_with((640, 360), pygame.RESIZABLE)
    finally:
        pygame.quit()
