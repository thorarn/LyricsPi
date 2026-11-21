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
        (pygame.K_UP, Action.PREVIOUS_PAGE),     # A
        (pygame.K_DOWN, Action.NEXT_PAGE),       # B
        (pygame.K_LEFT, Action.PREVIOUS_SONG),   # C
        (pygame.K_RIGHT, Action.NEXT_SONG),     # D
    ],
)
def test_single_foot_press_is_dispatched_after_window(
    key: int, action: Action
) -> None:
    keyboard = KeyboardController(InputConfig(combo_window_ms=90))
    assert keyboard.handle_event(press(key), 0) == []
    assert keyboard.handle_event(release(key), 30) == []
    assert keyboard.poll(89) == []
    assert keyboard.poll(90) == [action]
    assert keyboard.poll(200) == []


@pytest.mark.parametrize(
    ("first", "second", "action"),
    [
        (pygame.K_UP, pygame.K_LEFT, Action.FONT_SMALLER),
        (pygame.K_LEFT, pygame.K_UP, Action.FONT_SMALLER),
        (pygame.K_DOWN, pygame.K_RIGHT, Action.FONT_LARGER),
        (pygame.K_RIGHT, pygame.K_DOWN, Action.FONT_LARGER),
    ],
)
def test_combination_only_emits_font_action(
    first: int, second: int, action: Action
) -> None:
    keyboard = KeyboardController(InputConfig())
    assert keyboard.handle_event(press(first), 0) == []
    assert keyboard.handle_event(press(second), 150) == [action]
    assert keyboard.poll(300) == []


def test_late_partner_does_not_consume_single_actions() -> None:
    keyboard = KeyboardController(InputConfig())
    assert keyboard.handle_event(press(pygame.K_UP), 0) == []
    assert keyboard.handle_event(press(pygame.K_LEFT), 151) == [
        Action.PREVIOUS_PAGE
    ]
    assert keyboard.poll(301) == [Action.PREVIOUS_SONG]


def test_repeat_is_suppressed_until_release_and_combo_can_retrigger() -> None:
    keyboard = KeyboardController(InputConfig())
    up, left = pygame.K_UP, pygame.K_LEFT
    assert keyboard.handle_event(press(up), 0) == []
    assert keyboard.handle_event(press(left), 50) == [Action.FONT_SMALLER]
    for now_ms in (300, 900, 1500, 2100):
        assert keyboard.handle_event(press(up), now_ms) == []
        assert keyboard.handle_event(press(left, repeat=True), now_ms) == []
    assert keyboard.poll(2250) == []
    keyboard.handle_event(release(up), 2300)
    keyboard.handle_event(release(left), 2300)
    assert keyboard.handle_event(press(up), 2320) == []
    assert keyboard.handle_event(press(left), 2350) == [Action.FONT_SMALLER]
    assert keyboard.poll(2550) == []


def test_missing_keyup_does_not_block_the_next_press_indefinitely() -> None:
    keyboard = KeyboardController(InputConfig())
    key = pygame.K_DOWN
    assert keyboard.handle_event(press(key), 0) == []
    assert keyboard.poll(150) == [Action.NEXT_PAGE]
    assert keyboard.handle_event(press(key), 1100) == []
    assert keyboard.poll(1250) == [Action.NEXT_PAGE]


def test_two_quick_taps_with_keyup_are_both_processed() -> None:
    keyboard = KeyboardController(InputConfig())
    key = pygame.K_RIGHT
    assert keyboard.handle_event(press(key), 0) == []
    assert keyboard.handle_event(release(key), 20) == []
    assert keyboard.handle_event(press(key), 70) == []
    assert keyboard.handle_event(release(key), 90) == []
    assert keyboard.poll(230) == [Action.NEXT_SONG, Action.NEXT_SONG]


def test_focus_loss_clears_pending_and_held_keys() -> None:
    keyboard = KeyboardController(InputConfig())
    key = pygame.K_RIGHT
    assert keyboard.handle_event(press(key), 0) == []
    assert keyboard.handle_event(pygame.event.Event(pygame.WINDOWFOCUSLOST), 40) == []
    assert keyboard.poll(150) == []
    assert keyboard.handle_event(press(key), 200) == []
    assert keyboard.poll(350) == [Action.NEXT_SONG]


def test_other_keys_are_independent_of_pending_arrows() -> None:
    keyboard = KeyboardController(InputConfig())
    assert keyboard.handle_event(press(pygame.K_UP), 0) == []
    assert keyboard.handle_event(press(pygame.K_DOWN), 30) == []
    assert keyboard.handle_event(press(pygame.K_a), 30) == []
    assert keyboard.handle_event(press(pygame.K_PLUS), 40) == [Action.FONT_LARGER]
    assert keyboard.handle_event(press(pygame.K_MINUS), 60) == [Action.FONT_SMALLER]
    assert keyboard.handle_event(press(pygame.K_ESCAPE), 100) == [Action.EXIT]
    assert keyboard.poll(180) == [Action.PREVIOUS_PAGE, Action.NEXT_PAGE]


def test_disabled_combinations_give_immediate_single_actions() -> None:
    keyboard = KeyboardController(InputConfig(enable_combinations=False))
    key = pygame.K_RIGHT
    assert keyboard.handle_event(press(key), 0) == [Action.NEXT_SONG]
    assert keyboard.handle_event(press(key), 20) == []
    assert keyboard.handle_event(press(pygame.K_DOWN), 80) == [Action.NEXT_PAGE]
    assert keyboard.poll(300) == []
