import pygame
import pytest

from lyricspi import Action
from lyricspi.keyboard_controller import action_for_key


@pytest.mark.parametrize(
    ("key", "typed", "expected"),
    [
        (pygame.K_LEFT, "", Action.PREVIOUS_SONG),
        (pygame.K_RIGHT, "", Action.NEXT_SONG),
        (pygame.K_UP, "", Action.PREVIOUS_PAGE),
        (pygame.K_DOWN, "", Action.NEXT_PAGE),
        (pygame.K_MINUS, "-", Action.FONT_SMALLER),
        (pygame.K_PLUS, "+", Action.FONT_LARGER),
        (pygame.K_EQUALS, "+", Action.FONT_LARGER),
        (pygame.K_KP_PLUS, "", Action.FONT_LARGER),
        (pygame.K_KP_MINUS, "", Action.FONT_SMALLER),
        (pygame.K_ESCAPE, "\x1b", Action.EXIT),
        (pygame.K_MINUS, "_", None),
        (pygame.K_a, "a", None),
    ],
)
def test_keydown_maps_to_action(
    key: int, typed: str, expected: Action | None
) -> None:
    event = pygame.event.Event(pygame.KEYDOWN, key=key, unicode=typed)
    assert action_for_key(event) is expected


def test_keyup_does_not_trigger_action() -> None:
    event = pygame.event.Event(pygame.KEYUP, key=pygame.K_RIGHT)
    assert action_for_key(event) is None
