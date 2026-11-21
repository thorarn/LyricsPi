"""Coordinate input, application state and rendering."""

import logging
from dataclasses import dataclass, field

import pygame

from . import Action
from .config import Config, DisplayConfig
from .keyboard_controller import action_for_key
from .layout import LayoutTooSmall, Page
from .navigation import Navigation
from .renderer import Renderer
from .setlist import Setlist, Song
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
        if action is Action.EXIT:
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

    try:
        renderer = Renderer(config.display, resizable=state.development_mode)
        clock = pygame.time.Clock()
        size = renderer.screen.get_size()
        _update_layout(state, renderer)
        _draw(state, renderer, notice)

        while state.running:
            events = pygame.event.get()
            new_size = renderer.screen.get_size()
            redraw = new_size != size
            if redraw:
                size = new_size
                _update_layout(state, renderer)
            for event in events:
                if event.type == pygame.QUIT:
                    state.apply_action(Action.EXIT, config.display)
                elif event.type == pygame.WINDOWEXPOSED:
                    redraw = True
                elif config.system.allow_keyboard:
                    action = action_for_key(event)
                    if action is not None:
                        LOGGER.debug("Tastaturaktion: %s", action.name)
                        if action is not Action.EXIT or state.development_mode:
                            song_index = state.navigation.song_index
                            page_index = state.navigation.page_index
                            font_size = state.font_size
                            state.apply_action(action, config.display)
                            song_changed = (
                                song_index != state.navigation.song_index
                            )
                            if song_changed and state.song is not None:
                                LOGGER.debug(
                                    "Songwechsel: %s", state.song.filename
                                )
                            if song_changed or font_size != state.font_size:
                                _update_layout(state, renderer)
                                redraw = True
                            if page_index != state.navigation.page_index:
                                redraw = True
                if not state.running:
                    break

            if state.running:
                if redraw:
                    _draw(state, renderer, notice)
                clock.tick(FRAMES_PER_SECOND)
    except pygame.error as error:
        raise RuntimeError("Fehler bei der Bildschirmausgabe.") from error
    finally:
        pygame.quit()
