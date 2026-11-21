"""Coordinate input, application state and rendering."""

import logging
from dataclasses import dataclass, field
from sys import platform
from time import monotonic_ns

import pygame

from . import Action
from .config import PROJECT_ROOT, Config, DisplayConfig
from .keyboard_controller import KeyboardController
from .layout import LayoutTooSmall, Page
from .navigation import Navigation
from .renderer import Renderer
from .setlist import Setlist, Song
from .shutdown import request_shutdown
from .song_loader import load_setlist


LOGGER = logging.getLogger(__name__)
FRAMES_PER_SECOND = 30
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
        else:
            self.navigation.apply_action(
                action, len(self.setlist), len(self.pages)
            )

        if self.font_size != previous_size:
            LOGGER.info("Schriftgröße: %d → %d", previous_size, self.font_size)


def _update_layout(state: AppState, renderer: Renderer) -> None:
    song = state.song
    if song is None:
        return
    try:
        state.pages = renderer.layout(song.content, state.font_size)
    except LayoutTooSmall:
        state.pages = ()
    state.navigation.clamp_page(len(state.pages))
    LOGGER.debug(
        "Layout neu berechnet für %s (%d × %d, Schriftgröße %d, %d Seiten)",
        song.filename,
        *renderer.screen.get_size(),
        state.font_size,
        len(state.pages),
    )


def _draw(
    state: AppState, renderer: Renderer, source_notice: str | None
) -> None:
    notice = source_notice
    if state.setlist and not state.pages:
        notice = SMALL_WINDOW_NOTICE
    if state.pages:
        LOGGER.debug(
            "Seite %d/%d", state.navigation.page_index + 1, len(state.pages)
        )
    renderer.draw(state.font_size, state.page, notice)


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
        state.development_mode or shutdown_requested
    ):
        return False
    if action is Action.SHUTDOWN:
        LOGGER.info("Shutdown angefordert. LyricsPi wird beendet.")
    song = state.song
    page_index = state.navigation.page_index
    font_size = state.font_size
    state.apply_action(action, display)

    current_song = state.song
    song_changed = song is not current_song
    if song_changed and current_song is not None:
        LOGGER.debug("Songwechsel: %s", current_song.filename)
    if song_changed or font_size != state.font_size:
        _update_layout(state, renderer)
        return True
    return page_index != state.navigation.page_index


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
        splash_until = None
        logo = None
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
            redraw = new_size != size
            if redraw:
                size = new_size
                _update_layout(state, renderer)
            actions: list[Action] = []
            for event in events:
                if event.type == pygame.QUIT:
                    state.apply_action(Action.EXIT, config.display)
                    break
                elif event.type == pygame.WINDOWEXPOSED:
                    redraw = True
                elif keyboard is not None:
                    actions.extend(keyboard.handle_event(event, now_ms))
            if not state.running:
                break
            if keyboard is not None:
                pressed = pygame.key.get_pressed()
                shutdown_pressed = pressed[pygame.K_DOWN] and pygame.key.get_focused()
                actions.extend(
                    keyboard.poll(now_ms, shutdown_pressed=shutdown_pressed)
                )
            for action in actions:
                changed = _apply_keyboard_action(
                    action, state, config.display, renderer
                )
                redraw = redraw or changed
                if not state.running:
                    break

            if state.running:
                if splash_until is not None and now_ms >= splash_until:
                    splash_until = None
                    redraw = True
                if redraw:
                    if splash_until is None:
                        _draw(state, renderer, notice)
                    else:
                        renderer.draw_splash(logo)
                clock.tick(FRAMES_PER_SECOND)
    except pygame.error as error:
        raise RuntimeError("Fehler bei der Bildschirmausgabe.") from error
    finally:
        pygame.quit()
    if state.last_action is Action.SHUTDOWN:
        request_shutdown()
