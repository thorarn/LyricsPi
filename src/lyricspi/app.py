"""Coordinate input, application state and rendering."""

import logging
from dataclasses import dataclass

import pygame

from . import Action
from .config import Config, DisplayConfig
from .keyboard_controller import action_for_key
from .renderer import Renderer
from .setlist import Setlist
from .song_loader import load_setlist


LOGGER = logging.getLogger(__name__)
FRAMES_PER_SECOND = 30


@dataclass
class AppState:
    font_size: int
    development_mode: bool
    running: bool = True
    last_action: Action | None = None
    setlist: Setlist = Setlist()

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

        if self.font_size != previous_size:
            LOGGER.info("Schriftgröße: %d → %d", previous_size, self.font_size)


def run(config: Config) -> None:
    loaded = load_setlist(config.songs)
    state = AppState(
        config.display.font_size,
        config.system.development_mode,
        setlist=loaded.setlist,
    )
    LOGGER.info("%d Songs geladen.", len(state.setlist))
    first_song = state.setlist.first
    if first_song is not None:
        LOGGER.debug(
            "Erster Song: %s (%s)", first_song.title, first_song.filename
        )
    notice = loaded.issue.value if loaded.issue is not None else None

    try:
        renderer = Renderer(config.display)
        clock = pygame.time.Clock()
        renderer.draw(state.font_size, notice)

        while state.running:
            previous_size = state.font_size
            redraw = False
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    state.apply_action(Action.EXIT, config.display)
                elif event.type == pygame.WINDOWEXPOSED:
                    redraw = True
                elif config.system.allow_keyboard:
                    action = action_for_key(event)
                    if action is not None:
                        LOGGER.debug("Tastaturaktion: %s", action.name)
                        if action is not Action.EXIT or state.development_mode:
                            state.apply_action(action, config.display)
                if not state.running:
                    break

            if state.running:
                if redraw or state.font_size != previous_size:
                    renderer.draw(state.font_size, notice)
                clock.tick(FRAMES_PER_SECOND)
    finally:
        pygame.quit()
