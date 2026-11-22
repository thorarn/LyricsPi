"""Coordinate input, application state and rendering."""

import logging
from bisect import bisect_right
from dataclasses import dataclass, field, replace
from sys import platform
from time import monotonic, monotonic_ns
from typing import TYPE_CHECKING

import pygame

from . import Action, View
from .config import PROJECT_ROOT, Config, DisplayConfig
from .keyboard_controller import KeyboardController
from .layout import LayoutTooSmall, Page, TextPosition
from .navigation import Navigation
from .renderer import Renderer
from .setlist import Setlist, Song
from .shutdown import request_shutdown
from .song_loader import load_setlist

if TYPE_CHECKING:
    from .config import LyricsFollowingConfig
    from .lyrics_follower import LyricsFollower

LOGGER = logging.getLogger(__name__)
FRAMES_PER_SECOND = 30
VIEW_PAGE_DURATION_MS = 3000
SMALL_WINDOW_NOTICE = "Fenster zu klein."


@dataclass
class AppState:
    font_size: int
    development_mode: bool
    running: bool = True
    last_action: Action | None = None
    setlist: Setlist = Setlist()
    navigation: Navigation = field(default_factory=Navigation)
    pages: tuple[Page, ...] = ()
    page_starts: list[TextPosition] = field(default_factory=list)
    text_position: TextPosition = (0, 0)
    view: View = View.SONG_VIEW
    selected_song: int = 0
    follower: "LyricsFollower | None" = None
    page_line_ids: list[tuple[int, ...]] = field(default_factory=list)

    @property
    def song(self) -> Song | None:
        if not self.setlist:
            return None
        return self.setlist[self.navigation.song_index]

    @property
    def page(self) -> Page:
        return self.pages[self.navigation.page_index] if self.pages else ()

    def apply_action(self, action: Action, display: DisplayConfig) -> None:
        self.last_action = action
        previous_size = self.font_size
        if action in (Action.EXIT, Action.SHUTDOWN):
            self.running = False
        elif action is Action.FONT_SMALLER:
            self.font_size = max(
                display.font_min, self.font_size - display.font_step
            )
        elif action is Action.FONT_LARGER:
            self.font_size = min(
                display.font_max, self.font_size + display.font_step
            )
        elif self.view is View.SONG_VIEW:
            self._apply_song_action(action)
        elif self.view is View.MAIN_MENU:
            if action is Action.OPEN_SONG_LIST:
                self.selected_song = self.navigation.song_index
                self.view = View.SONG_LIST
            elif action is Action.BACK:
                self.view = View.SONG_VIEW
        elif action is Action.BACK:
            self.view = View.MAIN_MENU
        elif self.setlist:
            if action is Action.OPEN_SELECTED_SONG:
                self.navigation.song_index = self.selected_song
                self.navigation.page_index = 0
                self.text_position = (0, 0)
                self.view = View.SONG_VIEW
            elif action in (Action.SELECT_PREVIOUS, Action.SELECT_NEXT):
                step = 1 if action is Action.SELECT_NEXT else -1
                self.selected_song = max(
                    0, min(self.selected_song + step, len(self.setlist) - 1)
                )

        if self.font_size != previous_size:
            LOGGER.info("Schriftgröße: %d → %d", previous_size, self.font_size)

    def _apply_song_action(self, action: Action) -> None:
        if action is Action.OPEN_MENU:
            self.view = View.MAIN_MENU
        elif action in (Action.PREVIOUS_SONG, Action.NEXT_SONG):
            self.navigation.apply_action(
                action, len(self.setlist), len(self.pages)
            )
            self.text_position = (0, 0)
        elif action in (Action.PREVIOUS_PAGE, Action.NEXT_PAGE):
            previous_page = self.navigation.page_index
            self.navigation.apply_action(
                action, len(self.setlist), len(self.pages)
            )
            if self.navigation.page_index != previous_page:
                self.text_position = self.page_starts[self.navigation.page_index]


def _update_layout(state: AppState, renderer: Renderer) -> None:
    song = state.song
    if song is None:
        return
    state.page_starts.clear()
    state.page_line_ids.clear()
    if state.follower is not None:
        state.follower.layout_changed()
    try:
        state.pages = renderer.layout(
            song.content, state.font_size,
            song=song, page_starts=state.page_starts,
            page_line_ids=state.page_line_ids if state.follower is not None else None,
        )
    except LayoutTooSmall:
        state.pages = ()
    state.navigation.page_index = bisect_right(
        state.page_starts, state.text_position
    ) - 1
    state.navigation.clamp_page(len(state.pages))
    LOGGER.debug(
        "Layout neu berechnet für %s (%d × %d, Schriftgröße %d, %d Seiten)",
        song.filename,
        *renderer.screen.get_size(),
        state.font_size,
        len(state.pages),
    )


def _draw(
    state: AppState, renderer: Renderer, source_notice: str | None,
    *, view_page: int = 0,
) -> int:
    if state.view is View.MAIN_MENU:
        return renderer.draw_main_menu(state.font_size, view_page)
    if state.view is View.SONG_LIST:
        return renderer.draw_song_list(
            state.setlist, state.selected_song, state.font_size, view_page
        )

    notice = source_notice
    if state.setlist and not state.pages:
        notice = SMALL_WINDOW_NOTICE
    if state.pages:
        LOGGER.debug(
            "Seite %d/%d", state.navigation.page_index + 1, len(state.pages)
        )
    highlighted_rows = ()
    if (
        state.follower is not None and state.follower.config.highlight_current_line
        and state.page_line_ids
    ):
        line_ids = state.page_line_ids[state.navigation.page_index]
        highlighted_rows = tuple(
            row for row, line_id in enumerate(line_ids)
            if line_id == state.follower.line_id
        )
    renderer.draw(
        state.font_size,
        state.page,
        notice,
        song=state.song,
        page_index=state.navigation.page_index,
        page_count=len(state.pages),
        highlighted_rows=highlighted_rows,
    )
    if highlighted_rows and state.follower is not None:
        state.follower.mark_visible()
    return 1


def _apply_keyboard_action(
    action: Action, state: AppState, display: DisplayConfig, renderer: Renderer
) -> bool:
    shutdown_requested = action is Action.SHUTDOWN
    if shutdown_requested and (
        not platform.startswith("linux") or state.development_mode
    ):
        action = Action.EXIT
    LOGGER.debug("Tastaturaktion: %s", action.name)
    if action is Action.EXIT and not (
        (state.development_mode and platform == "win32") or shutdown_requested
    ):
        return False
    if action is Action.SHUTDOWN:
        LOGGER.info("Shutdown angefordert. LyricsPi wird beendet.")
    song = state.song
    page_index = state.navigation.page_index
    font_size = state.font_size
    view = state.view
    selection = state.selected_song
    state.apply_action(action, display)

    current_song = state.song
    song_changed = song is not current_song
    if song_changed and current_song is not None:
        LOGGER.debug("Songwechsel: %s", current_song.filename)
    if song_changed or font_size != state.font_size:
        _update_layout(state, renderer)
    navigated = (
        song_changed or view is not state.view
        or (font_size == state.font_size and page_index != state.navigation.page_index)
    )
    reset_song = state.view is View.SONG_VIEW and (
        action in (Action.PREVIOUS_SONG, Action.NEXT_SONG, Action.OPEN_SELECTED_SONG)
    )
    if state.follower is not None and (navigated or reset_song):
        _sync_follower(state, manual=True)
        return True
    return navigated or font_size != state.font_size or selection != state.selected_song


def _sync_follower(state: AppState, *, manual: bool = False) -> None:
    if state.follower is None:
        return
    song = state.song if state.view is View.SONG_VIEW else None
    state.follower.synchronize(
        song.content if song is not None else None,
        state.page_starts[state.navigation.page_index][0] if state.page_starts else 0,
        monotonic(), manual=manual,
    )


def _start_follower(
    state: AppState, renderer: Renderer, config: "LyricsFollowingConfig",
) -> None:
    from .lyrics_follower import LyricsFollower

    state.follower = LyricsFollower(config)
    _update_layout(state, renderer)
    _sync_follower(state)
    state.follower.start()
    LOGGER.info("Textverfolgung aktiv (%s).", config.mode)


def _poll_follower(state: AppState) -> bool:
    follower = state.follower
    if follower is None or state.view is not View.SONG_VIEW:
        return False
    previous_line = follower.line_id
    page = follower.poll(state.navigation.page_index, state.page_line_ids, monotonic())
    if page is not None:
        state.navigation.page_index = page
        state.text_position = state.page_starts[page]
        return True
    return previous_line != follower.line_id and follower.config.highlight_current_line


def run(config: Config) -> None:
    loaded = load_setlist(config.songs)
    state = AppState(
        config.display.font_size,
        config.system.development_mode,
        setlist=loaded.setlist,
    )
    LOGGER.info("%d Songs geladen.", len(state.setlist))
    first_song = state.song
    if first_song is not None:
        LOGGER.debug(
            "Erster Song: %s (%s)", first_song.title, first_song.filename
        )
    notice = loaded.issue.value if loaded.issue is not None else None
    keyboard = (
        KeyboardController(config.input) if config.system.allow_keyboard else None
    )
    following_config = config.lyrics_following
    following_supported = platform == "win32" and state.development_mode
    retiring_follower = None

    try:
        renderer = Renderer(config.display, resizable=state.development_mode)
        pygame.key.set_repeat()
        LOGGER.info(
            "Tastatureingabe (einschließlich USB-HID): %s",
            "aktiv" if keyboard is not None else "deaktiviert",
        )
        clock = pygame.time.Clock()
        size = renderer.screen.get_size()
        _update_layout(state, renderer)
        if following_supported and following_config.enabled:
            _start_follower(state, renderer, following_config)
        splash_until = None
        logo = None
        view_page = 0
        view_page_count = 1
        next_view_page_ms = 0.0
        if config.system.show_splash:
            logo = renderer.load_splash_logo(
                PROJECT_ROOT / "assets" / "logo.png"
            )
            renderer.draw_splash(logo)
            splash_until = (
                monotonic_ns() / 1_000_000 + config.system.splash_duration_ms
            )
        else:
            _draw(state, renderer, notice)

        while state.running:
            events = pygame.event.get()
            now_ms = monotonic_ns() / 1_000_000
            new_size = renderer.screen.get_size()
            previous_view = state.view
            previous_selection = state.selected_song
            redraw = new_size != size
            if redraw:
                view_page = 0
                size = new_size
                _update_layout(state, renderer)
            for event in events:
                if event.type == pygame.QUIT:
                    state.apply_action(Action.EXIT, config.display)
                    break
                elif event.type == pygame.WINDOWEXPOSED:
                    redraw = True
                elif (
                    following_supported and keyboard is not None
                    and event.type == pygame.KEYDOWN
                    and event.key in (pygame.K_F8, pygame.K_F9)
                ):
                    if event.key == pygame.K_F8:
                        if state.follower is not None:
                            retiring_follower = state.follower
                            retiring_follower.stop()
                            state.follower = None
                            state.page_line_ids.clear()
                            LOGGER.info("Textverfolgung deaktiviert.")
                        elif retiring_follower is None or retiring_follower.finished:
                            retiring_follower = None
                            _start_follower(state, renderer, following_config)
                        else:
                            LOGGER.info("Die vorige Textverfolgung wird noch beendet.")
                        redraw = True
                    elif state.follower is not None:
                        auto = not (
                            following_config.mode == "auto"
                            and following_config.auto_page_turn
                        )
                        following_config = replace(
                            following_config, mode="auto" if auto else "observe",
                            auto_page_turn=auto,
                        )
                        state.follower.config = following_config
                        state.follower.layout_changed()
                        LOGGER.info("Textverfolgung: %s.", following_config.mode)
                elif keyboard is not None:
                    for action in keyboard.handle_event(event, now_ms, state.view):
                        view = state.view
                        redraw |= _apply_keyboard_action(
                            action, state, config.display, renderer
                        )
                        if state.view is not view:
                            keyboard.view_changed()
                    if not state.running:
                        break
            if not state.running:
                break
            if keyboard is not None:
                pressed = pygame.key.get_pressed()
                focused = pygame.key.get_focused()
                for action in keyboard.poll(
                    now_ms, is_pressed=lambda key: focused and pressed[key]
                ):
                    view = state.view
                    redraw |= _apply_keyboard_action(
                        action, state, config.display, renderer
                    )
                    if state.view is not view:
                        keyboard.view_changed()
                        break
                    if not state.running:
                        break

            if state.running:
                redraw |= _poll_follower(state)
                if splash_until is not None and (
                    now_ms >= splash_until or state.view is not View.SONG_VIEW
                ):
                    splash_until = None
                    redraw = True
                if state.view is not previous_view or (
                    state.selected_song != previous_selection
                ):
                    view_page = 0
                if (
                    not redraw and view_page_count > 1
                    and now_ms >= next_view_page_ms
                ):
                    view_page = (view_page + 1) % view_page_count
                    redraw = True
                if redraw:
                    if splash_until is None:
                        view_page_count = _draw(
                            state, renderer, notice, view_page=view_page
                        )
                        next_view_page_ms = now_ms + VIEW_PAGE_DURATION_MS
                    else:
                        renderer.draw_splash(logo)
                clock.tick(FRAMES_PER_SECOND)
    except pygame.error as error:
        raise RuntimeError("Fehler bei der Bildschirmausgabe.") from error
    finally:
        pygame.quit()
        if state.follower is not None:
            state.follower.close()
        if retiring_follower is not None:
            retiring_follower.close()
    if state.last_action is Action.SHUTDOWN:
        request_shutdown()
