import pygame
import pytest

from lyricspi import Action
from lyricspi.config import InputConfig
from lyricspi.keyboard_controller import KeyboardController, action_for_key


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


def press(key: int, *, repeat: bool = False) -> pygame.event.Event:
    return pygame.event.Event(pygame.KEYDOWN, key=key, repeat=repeat)


def release(key: int) -> pygame.event.Event:
    return pygame.event.Event(pygame.KEYUP, key=key)


@pytest.mark.parametrize(
    ("key", "action"),
    [
        (pygame.K_UP, Action.PREVIOUS_PAGE),
        (pygame.K_LEFT, Action.PREVIOUS_SONG),
        (pygame.K_RIGHT, Action.NEXT_SONG),
        (pygame.K_PLUS, Action.FONT_LARGER),
        (pygame.K_MINUS, Action.FONT_SMALLER),
        (pygame.K_ESCAPE, Action.EXIT),
    ],
)
def test_other_keys_are_immediate_during_b_hold(key: int, action: Action) -> None:
    keyboard = KeyboardController(InputConfig())
    assert keyboard.handle_event(press(pygame.K_DOWN), 0) == []
    assert keyboard.poll(40, shutdown_pressed=True) == []
    assert keyboard.handle_event(press(key), 80) == [action]
    assert keyboard.handle_event(release(key), 100) == []
    assert keyboard.handle_event(release(pygame.K_DOWN), 200) == [
        Action.NEXT_PAGE
    ]


@pytest.mark.parametrize("duration_ms", [200, 3000, 14900])
def test_short_b_fires_one_next_page_on_release(duration_ms: int) -> None:
    keyboard = KeyboardController(InputConfig())
    assert keyboard.handle_event(press(pygame.K_DOWN), 0) == []
    assert keyboard.poll(duration_ms - 1, shutdown_pressed=True) == []
    assert keyboard.handle_event(release(pygame.K_DOWN), duration_ms) == [
        Action.NEXT_PAGE
    ]
    assert keyboard.handle_event(release(pygame.K_DOWN), duration_ms + 1) == []
    assert keyboard.poll(20000) == []


@pytest.mark.parametrize("duration_ms", [15000, 20000])
def test_long_b_fires_once_without_navigation(duration_ms: int) -> None:
    keyboard = KeyboardController(InputConfig())
    key = pygame.K_DOWN
    assert keyboard.handle_event(press(key, repeat=True), 0) == []
    assert keyboard.handle_event(press(key), 50) == []
    assert keyboard.poll(55, shutdown_pressed=True) == []
    assert keyboard.handle_event(press(key, repeat=True), 80) == []
    assert keyboard.handle_event(press(key), 1000) == []
    assert keyboard.poll(15049.9, shutdown_pressed=True) == []
    assert keyboard.poll(50 + duration_ms, shutdown_pressed=True) == [
        Action.SHUTDOWN
    ]
    assert keyboard.poll(23000, shutdown_pressed=True) == []
    assert keyboard.handle_event(release(key), 24000) == []
    assert keyboard.handle_event(press(key), 24200) == []
    assert keyboard.handle_event(release(key), 24400) == [Action.NEXT_PAGE]


def test_keyup_at_threshold_uses_confirmed_hold() -> None:
    keyboard = KeyboardController(InputConfig())
    keyboard.handle_event(press(pygame.K_DOWN), 0)
    keyboard.poll(14990, shutdown_pressed=True)
    assert keyboard.handle_event(release(pygame.K_DOWN), 15000) == [
        Action.SHUTDOWN
    ]


def test_keyup_after_unconfirmed_hold_does_not_shutdown() -> None:
    keyboard = KeyboardController(InputConfig())
    keyboard.handle_event(press(pygame.K_DOWN), 0)
    assert keyboard.handle_event(release(pygame.K_DOWN), 15000) == []


def test_loss_of_pressed_state_without_keyup_cancels_hold() -> None:
    keyboard = KeyboardController(InputConfig())
    keyboard.handle_event(press(pygame.K_DOWN), 0)
    assert keyboard.poll(100, shutdown_pressed=True) == []
    assert keyboard.poll(200, shutdown_pressed=False) == []
    assert keyboard.poll(16000, shutdown_pressed=True) == []
    assert keyboard.handle_event(release(pygame.K_DOWN), 16100) == []


def test_focus_loss_cancels_hold() -> None:
    keyboard = KeyboardController(InputConfig())
    keyboard.handle_event(press(pygame.K_DOWN), 0)
    keyboard.poll(200, shutdown_pressed=True)
    keyboard.handle_event(pygame.event.Event(pygame.WINDOWFOCUSLOST), 300)
    assert keyboard.poll(15000, shutdown_pressed=True) == []


def test_custom_hold_threshold() -> None:
    keyboard = KeyboardController(InputConfig(shutdown_hold_ms=18000))
    keyboard.handle_event(press(pygame.K_DOWN), 0)
    assert keyboard.poll(15000, shutdown_pressed=True) == []
    assert keyboard.poll(18000, shutdown_pressed=True) == [Action.SHUTDOWN]


@pytest.mark.parametrize(
    ("first", "second", "first_actions", "second_actions", "released_actions"),
    [
        (pygame.K_UP, pygame.K_LEFT, [Action.PREVIOUS_PAGE], [Action.PREVIOUS_SONG], []),
        (pygame.K_DOWN, pygame.K_RIGHT, [], [Action.NEXT_SONG], [Action.NEXT_PAGE]),
        (pygame.K_UP, pygame.K_RIGHT, [Action.PREVIOUS_PAGE], [Action.NEXT_SONG], []),
    ],
)
def test_old_combinations_only_produce_individual_actions(
    first: int,
    second: int,
    first_actions: list[Action],
    second_actions: list[Action],
    released_actions: list[Action],
) -> None:
    keyboard = KeyboardController(InputConfig())
    assert keyboard.handle_event(press(first), 0) == first_actions
    assert keyboard.handle_event(press(second), 50) == second_actions
    assert keyboard.handle_event(release(first), 200) == released_actions
    assert keyboard.handle_event(release(second), 200) == []
    assert keyboard.poll(20000) == []
