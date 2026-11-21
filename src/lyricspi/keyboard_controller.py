"""Translate Pygame key presses into actions for the active view."""

import logging
from collections.abc import Callable

import pygame

from . import Action, View
from .config import InputConfig


ARROW_ACTIONS = {
    View.SONG_VIEW: {
        pygame.K_UP: Action.PREVIOUS_SONG,
        pygame.K_DOWN: Action.NEXT_SONG,
        pygame.K_LEFT: Action.PREVIOUS_PAGE,
        pygame.K_RIGHT: Action.NEXT_PAGE,
    },
    View.MAIN_MENU: {
        pygame.K_UP: Action.FONT_SMALLER,
        pygame.K_DOWN: Action.FONT_LARGER,
        pygame.K_LEFT: Action.OPEN_SONG_LIST,
        pygame.K_RIGHT: Action.BACK,
    },
    View.SONG_LIST: {
        pygame.K_UP: Action.SELECT_PREVIOUS,
        pygame.K_DOWN: Action.SELECT_NEXT,
        pygame.K_LEFT: Action.OPEN_SELECTED_SONG,
        pygame.K_RIGHT: Action.BACK,
    },
}
KEY_ACTIONS = {
    pygame.K_MINUS: Action.FONT_SMALLER,
    pygame.K_KP_MINUS: Action.FONT_SMALLER,
    pygame.K_PLUS: Action.FONT_LARGER,
    pygame.K_KP_PLUS: Action.FONT_LARGER,
    pygame.K_ESCAPE: Action.EXIT,
}
MENU_HOLD_MS = 5000
LOGGER = logging.getLogger(__name__)


def action_for_key(
    event: pygame.event.Event, view: View = View.SONG_VIEW
) -> Action | None:
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
    return ARROW_ACTIONS[view].get(event.key) or KEY_ACTIONS.get(event.key)


class KeyboardController:
    """Track real A/B holds while preventing repeats across view changes."""

    def __init__(self, config: InputConfig) -> None:
        self._long_actions = {
            pygame.K_UP: (MENU_HOLD_MS, Action.OPEN_MENU),
            pygame.K_DOWN: (config.shutdown_hold_ms, Action.SHUTDOWN),
        }
        self._arrows_down: set[int] = set()
        self._holds: dict[int, float] = {}

    def view_changed(self) -> None:
        # Keep held arrows consumed until release, even in the next view.
        self._holds.clear()

    def poll(
        self, now_ms: float, *, is_pressed: Callable[[int], bool]
    ) -> list[Action]:
        actions: list[Action] = []
        released = {key for key in self._arrows_down if not is_pressed(key)}
        self._arrows_down.difference_update(released)
        for key in released:
            if self._holds.pop(key, None) is not None:
                LOGGER.debug("%s ohne KEYUP freigegeben.", pygame.key.name(key))

        for key, since_ms in tuple(self._holds.items()):
            threshold, action = self._long_actions[key]
            duration = now_ms - since_ms
            if duration >= threshold:
                del self._holds[key]
                LOGGER.debug(
                    "%s %.0f ms gehalten. Aktion %s.",
                    pygame.key.name(key), duration, action.name,
                )
                actions.append(action)
        return actions

    def handle_event(
        self, event: pygame.event.Event, now_ms: float,
        view: View = View.SONG_VIEW,
    ) -> list[Action]:
        if event.type == pygame.WINDOWFOCUSLOST:
            self._arrows_down.clear()
            self._holds.clear()
            return []

        if event.type not in (pygame.KEYDOWN, pygame.KEYUP):
            return []
        key = event.key
        if event.type == pygame.KEYUP:
            self._arrows_down.discard(key)
            since_ms = self._holds.pop(key, None)
            if since_ms is None:
                return []
            duration = now_ms - since_ms
            threshold, _ = self._long_actions[key]
            # A queued KEYUP cannot prove the key was down at the threshold.
            if duration >= threshold:
                LOGGER.debug(
                    "KEYUP %s nach %.0f ms ohne bestätigten Langdruck.",
                    pygame.key.name(key), duration,
                )
                return []
            action = ARROW_ACTIONS[View.SONG_VIEW][key]
            LOGGER.debug(
                "KEYUP %s nach %.0f ms. Aktion %s.",
                pygame.key.name(key), duration, action.name,
            )
            return [action]

        if getattr(event, "repeat", False) or key in self._arrows_down:
            return []
        if key in ARROW_ACTIONS[view]:
            self._arrows_down.add(key)
            if view is View.SONG_VIEW and key in self._long_actions:
                self._holds[key] = now_ms
                LOGGER.debug("KEYDOWN %s.", pygame.key.name(key))
                return []
        action = action_for_key(event, view)
        return [action] if action is not None else []
