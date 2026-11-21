"""Translate Pygame key presses into input-independent actions."""

from collections import deque

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
COMBINATIONS = {
    pygame.K_UP: (pygame.K_LEFT, Action.FONT_SMALLER),  # A + C
    pygame.K_LEFT: (pygame.K_UP, Action.FONT_SMALLER),
    pygame.K_DOWN: (pygame.K_RIGHT, Action.FONT_LARGER),  # B + D
    pygame.K_RIGHT: (pygame.K_DOWN, Action.FONT_LARGER),
}


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
    """Collect paired arrow presses without blocking the event loop."""

    def __init__(self, config: InputConfig) -> None:
        self.config = config
        self._release_timeout_ms = max(1000, 2 * config.combo_window_ms)
        self._held_until: dict[int, int] = {}
        self._pending: deque[tuple[int, int]] = deque()

    def poll(self, now_ms: int) -> list[Action]:
        actions = []
        while self._pending and self._pending[0][0] <= now_ms:
            _, key = self._pending.popleft()
            actions.append(KEY_ACTIONS[key])
        return actions

    def handle_event(self, event: pygame.event.Event, now_ms: int) -> list[Action]:
        if event.type == pygame.WINDOWFOCUSLOST:
            self._held_until.clear()
            self._pending.clear()
            return []

        # A second press at the deadline can still form a combination.
        actions = self.poll(now_ms - 1)
        if event.type == pygame.KEYUP:
            self._held_until.pop(event.key, None)
            return actions

        action = action_for_key(event)
        if action is None:
            return actions

        combination = COMBINATIONS.get(event.key)
        repeated = getattr(event, "repeat", False)
        if combination is not None:
            held = self._held_until.get(event.key, now_ms) > now_ms
            self._held_until[event.key] = now_ms + self._release_timeout_ms
            repeated = repeated or held
        if repeated:
            return actions

        if not self.config.enable_combinations or combination is None:
            actions.append(action)
            return actions

        partner, combined_action = combination
        for index in range(len(self._pending) - 1, -1, -1):
            if self._pending[index][1] == partner:
                del self._pending[index]
                actions.append(combined_action)
                return actions
        self._pending.append((now_ms + self.config.combo_window_ms, event.key))
        return actions
