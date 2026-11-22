"""Coordinate input, application state and rendering."""

import logging
from bisect import bisect_right
from dataclasses import dataclass, field
from pathlib import Path
from sys import platform
from time import monotonic_ns

import pygame

from . import Action, View
from .config import (
    FONT_SIZES, PROJECT_ROOT, Config, DisplaySettings, display_settings_path,
    load_display_settings, save_display_settings,
)
from .keyboard_controller import KeyboardController
from .layout import LayoutTooSmall, Page, TextPosition
from .navigation import Navigation
from .renderer import Renderer
from .setlist import Setlist, Song
from .shutdown import request_shutdown
from .song_loader import load_setlist


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
    rotation: int = 0

    @property
    def song(self) -> Song | None:
        if not self.setlist:
            return None
        return self.setlist[self.navigation.song_index]

    @property
    def page(self) -> Page:
        return self.pages[self.navigation.page_index] if self.pages else ()

    def apply_action(self, action: Action) -> None:
        self.last_action = action
        previous_size = self.font_size
        if action in (Action.EXIT, Action.SHUTDOWN):
            self.running = False
        elif action is Action.FONT_SMALLER and self.view is not View.MAIN_MENU:
            self.font_size = next(
                (size for size in reversed(FONT_SIZES) if size < self.font_size),
                self.font_size,
            )
        elif action is Action.FONT_LARGER and self.view is not View.MAIN_MENU:
            self.font_size = next(
                (size for size in FONT_SIZES if size > self.font_size), self.font_size
            )
        elif self.view is View.SONG_VIEW:
            self._apply_song_action(action)
        elif self.view is View.MAIN_MENU:
            if action is Action.CYCLE_FONT_SIZE:
                self.font_size = next(
                    (size for size in FONT_SIZES if size > self.font_size), FONT_SIZES[0]
                )
            elif action is Action.ROTATE_DISPLAY:
                self.rotation = (self.rotation + 90) % 360
                LOGGER.info("Bildschirmrotation: %d°", self.rotation)
            elif action is Action.OPEN_SONG_LIST:
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
    try:
        state.pages = renderer.layout(
            song.content, state.font_size,
            song=song, page_starts=state.page_starts,
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
        renderer.draw_main_menu(state.font_size)
        return 1
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
    renderer.draw(
        state.font_size,
        state.page,
        notice,
        song=state.song,
        page_index=state.navigation.page_index,
        page_count=len(state.pages),
    )
    return 1


def _apply_keyboard_action(
    action: Action, state: AppState, renderer: Renderer, settings_path: Path
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
    rotation = state.rotation
    view = state.view
    selection = state.selected_song
    state.apply_action(action)

    settings_changed = (font_size, rotation) != (state.font_size, state.rotation)
    if rotation != state.rotation:
        renderer.rotation = state.rotation
    if settings_changed:
        save_display_settings(settings_path, DisplaySettings(state.font_size, state.rotation))

    current_song = state.song
    song_changed = song is not current_song
    if song_changed and current_song is not None:
        LOGGER.debug("Songwechsel: %s", current_song.filename)
    if song_changed or settings_changed:
        _update_layout(state, renderer)
        return True
    return (
        page_index != state.navigation.page_index
        or view is not state.view
        or selection != state.selected_song
    )


def run(config: Config) -> None:
    loaded = load_setlist(config.songs)
    settings_path = display_settings_path()
    settings = load_display_settings(settings_path, config.display)
    state = AppState(
        settings.font_size,
        config.system.development_mode,
        setlist=loaded.setlist,
        rotation=settings.rotation,
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

    try:
        renderer = Renderer(config.display, resizable=state.development_mode)
        renderer.rotation = state.rotation
        pygame.key.set_repeat()
        LOGGER.info(
            "Tastatureingabe (einschließlich USB-HID): %s",
            "aktiv" if keyboard is not None else "deaktiviert",
        )
        clock = pygame.time.Clock()
        size = renderer.display_size
        _update_layout(state, renderer)
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
            new_size = renderer.display_size
            previous_view = state.view
            previous_selection = state.selected_song
            redraw = new_size != size
            if redraw:
                view_page = 0
                size = new_size
                _update_layout(state, renderer)
            for event in events:
                if event.type == pygame.QUIT:
                    state.apply_action(Action.EXIT)
                    break
                elif event.type == pygame.WINDOWEXPOSED:
                    redraw = True
                elif keyboard is not None:
                    for action in keyboard.handle_event(event, now_ms, state.view):
                        view = state.view
                        redraw |= _apply_keyboard_action(
                            action, state, renderer, settings_path
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
                        action, state, renderer, settings_path
                    )
                    if state.view is not view:
                        keyboard.view_changed()
                        break
                    if not state.running:
                        break

            if state.running:
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
    if state.last_action is Action.SHUTDOWN:
        request_shutdown()
