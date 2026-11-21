"""Translate Pygame key presses into input-independent actions."""

import pygame

from . import Action


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
