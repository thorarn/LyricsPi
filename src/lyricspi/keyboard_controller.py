"""Translate Pygame key presses into input-independent actions."""

import logging

import pygame

from . import Action
from .config import InputConfig


KEY_ACTIONS = {
    pygame.K_LEFT: Action.PREVIOUS_SONG,
    pygame.K_RIGHT: Action.NEXT_SONG,
    pygame.K_UP: Action.PREVIOUS_PAGE,
    pygame.K_DOWN: Action.NEXT_PAGE,
    pygame.K_MINUS: Action.FONT_SMALLER,
    pygame.K_KP_MINUS: Action.FONT_SMALLER,
    pygame.K_PLUS: Action.FONT_LARGER,
    pygame.K_KP_PLUS: Action.FONT_LARGER,
    pygame.K_ESCAPE: Action.EXIT,
}
LOGGER = logging.getLogger(__name__)


def action_for_key(event: pygame.event.Event) -> Action | None:
    if event.type != pygame.KEYDOWN:
        return None

    # SDL reports the typed character independently from the physical key.
    typed = getattr(event, "unicode", "")
    if typed == "+":
        return Action.FONT_LARGER
    if typed == "-":
        return Action.FONT_SMALLER
    if typed and event.key in (pygame.K_PLUS, pygame.K_MINUS):
        return None
    return KEY_ACTIONS.get(event.key)


class KeyboardController:
    """Distinguish a short tap on B from a confirmed shutdown hold."""

    def __init__(self, config: InputConfig) -> None:
        self.config = config
        self._down_since: float | None = None
        self._hold_confirmed = False
        self._shutdown_fired = False

    def _reset_hold(self) -> None:
        self._down_since = None
        self._hold_confirmed = False
        self._shutdown_fired = False

    def poll(
        self, now_ms: float, *, shutdown_pressed: bool = False
    ) -> list[Action]:
        if self._down_since is None:
            return []
        if not shutdown_pressed:
            LOGGER.debug("Arrow Down ohne KEYUP freigegeben. Haltezeit verworfen.")
            self._reset_hold()
            return []
        self._hold_confirmed = True
        duration_ms = now_ms - self._down_since
        if not self._shutdown_fired and duration_ms >= self.config.shutdown_hold_ms:
            self._shutdown_fired = True
            LOGGER.debug("Arrow Down %.0f ms gehalten. Aktion SHUTDOWN.", duration_ms)
            return [Action.SHUTDOWN]
        return []

    def handle_event(
        self, event: pygame.event.Event, now_ms: float
    ) -> list[Action]:
        if event.type == pygame.WINDOWFOCUSLOST:
            self._reset_hold()
            return []

        if event.type not in (pygame.KEYDOWN, pygame.KEYUP):
            return []
        if event.key != pygame.K_DOWN:
            action = action_for_key(event)
            return [action] if action and not getattr(event, "repeat", False) else []
        if event.type == pygame.KEYDOWN:
            if self._down_since is not None or getattr(event, "repeat", False):
                LOGGER.debug("KEYDOWN Arrow Down (Autorepeat ignoriert).")
            else:
                LOGGER.debug("KEYDOWN Arrow Down.")
                self._down_since = now_ms
            return []

        if self._down_since is None:
            LOGGER.debug("KEYUP Arrow Down ohne zugehörigen KEYDOWN.")
            return []
        duration_ms = now_ms - self._down_since
        if self._shutdown_fired:
            action = None
        elif duration_ms < self.config.shutdown_hold_ms:
            action = Action.NEXT_PAGE
        else:
            action = Action.SHUTDOWN if self._hold_confirmed else None
        self._reset_hold()
        LOGGER.debug(
            "KEYUP Arrow Down nach %.0f ms. Aktion %s.",
            duration_ms,
            action.name if action is not None else "keine",
        )
        return [action] if action is not None else []
