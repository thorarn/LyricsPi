import pygame
import pytest

from lyricspi import Action, View
from lyricspi.config import InputConfig
from lyricspi.keyboard_controller import KeyboardController, action_for_key


@pytest.mark.parametrize(
    ("key", "typed", "expected"),
    [
        (pygame.K_LEFT, "", Action.PREVIOUS_PAGE),
        (pygame.K_RIGHT, "", Action.NEXT_PAGE),
        (pygame.K_UP, "", Action.PREVIOUS_SONG),
        (pygame.K_DOWN, "", Action.NEXT_SONG),
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


def test_keyup_does_not_map_to_stateless_action() -> None:
    assert action_for_key(release(pygame.K_RIGHT)) is None


@pytest.mark.parametrize("key", [pygame.K_PLUS, pygame.K_MINUS, pygame.K_KP_MINUS])
def test_font_shortcuts_do_not_add_menu_functions(key: int) -> None:
    assert action_for_key(press(key), View.MAIN_MENU) is None


def press(key: int, *, repeat: bool = False) -> pygame.event.Event:
    return pygame.event.Event(pygame.KEYDOWN, key=key, repeat=repeat)


def release(key: int) -> pygame.event.Event:
    return pygame.event.Event(pygame.KEYUP, key=key)


@pytest.mark.parametrize(
    ("view", "actions"),
    [
        (View.MAIN_MENU, (
            Action.CYCLE_FONT_SIZE, Action.ROTATE_DISPLAY,
            Action.OPEN_SONG_LIST, Action.BACK,
        )),
        (View.SONG_LIST, (
            Action.SELECT_PREVIOUS, Action.SELECT_NEXT,
            Action.OPEN_SELECTED_SONG, Action.BACK,
        )),
    ],
)
def test_menu_arrows_fire_once_on_press(view: View, actions: tuple[Action, ...]) -> None:
    keyboard = KeyboardController(InputConfig())
    keys = (pygame.K_UP, pygame.K_DOWN, pygame.K_LEFT, pygame.K_RIGHT)
    for key, action in zip(keys, actions, strict=True):
        assert keyboard.handle_event(press(key), 0, view) == [action]
        assert keyboard.handle_event(press(key), 3000, view) == []
        assert keyboard.poll(20000, is_pressed={key}.__contains__) == []
        assert keyboard.handle_event(release(key), 20100, view) == []


@pytest.mark.parametrize(
    ("key", "action"),
    [
        (pygame.K_LEFT, Action.PREVIOUS_PAGE),
        (pygame.K_RIGHT, Action.NEXT_PAGE),
        (pygame.K_PLUS, Action.FONT_LARGER),
        (pygame.K_MINUS, Action.FONT_SMALLER),
        (pygame.K_ESCAPE, Action.EXIT),
    ],
)
def test_other_keys_are_immediate_during_b_hold(key: int, action: Action) -> None:
    keyboard = KeyboardController(InputConfig())
    assert keyboard.handle_event(press(pygame.K_DOWN), 0) == []
    assert keyboard.handle_event(press(key), 80) == [action]
    assert keyboard.handle_event(press(key, repeat=True), 90) == []
    assert keyboard.handle_event(release(key), 100) == []
    assert keyboard.handle_event(release(pygame.K_DOWN), 200) == [Action.NEXT_SONG]


@pytest.mark.parametrize(
    ("held_key", "page_key", "song_action", "page_action"),
    [
        (pygame.K_UP, pygame.K_LEFT, Action.PREVIOUS_SONG, Action.PREVIOUS_PAGE),
        (pygame.K_UP, pygame.K_RIGHT, Action.PREVIOUS_SONG, Action.NEXT_PAGE),
        (pygame.K_DOWN, pygame.K_RIGHT, Action.NEXT_SONG, Action.NEXT_PAGE),
    ],
)
def test_old_chords_only_emit_individual_actions(
    held_key: int, page_key: int, song_action: Action, page_action: Action,
) -> None:
    keyboard = KeyboardController(InputConfig())
    assert keyboard.handle_event(press(held_key), 0) == []
    assert keyboard.handle_event(press(page_key), 50) == [page_action]
    assert keyboard.handle_event(release(held_key), 200) == [song_action]
    assert keyboard.handle_event(release(page_key), 200) == []


@pytest.mark.parametrize(
    ("key", "short", "long", "threshold"),
    [
        (pygame.K_UP, Action.PREVIOUS_SONG, Action.OPEN_MENU, 5000),
        (pygame.K_DOWN, Action.NEXT_SONG, Action.SHUTDOWN, 15000),
    ],
)
def test_tap_and_long_hold_are_exclusive(
    key: int, short: Action, long: Action, threshold: int
) -> None:
    keyboard = KeyboardController(InputConfig())
    held = {key}.__contains__
    assert keyboard.handle_event(press(key, repeat=True), 0) == []
    assert keyboard.handle_event(press(key), 100) == []
    assert keyboard.poll(threshold + 99, is_pressed=held) == []
    assert keyboard.handle_event(release(key), threshold + 99) == [short]
    assert keyboard.handle_event(release(key), threshold + 100) == []

    start = 2 * threshold
    assert keyboard.handle_event(press(key), start) == []
    assert keyboard.handle_event(press(key, repeat=True), start + 80) == []
    assert keyboard.handle_event(press(key), start + 1000) == []
    assert keyboard.poll(start + threshold - 0.1, is_pressed=held) == []
    assert keyboard.poll(start + threshold, is_pressed=held) == [long]
    assert keyboard.poll(start + threshold + 100, is_pressed=held) == []
    assert keyboard.handle_event(release(key), start + threshold + 200) == []


@pytest.mark.parametrize(
    ("key", "threshold"),
    [
        (pygame.K_UP, 5000),
        (pygame.K_DOWN, 15000),
    ],
)
def test_queued_keyup_cannot_trigger_unobserved_long_hold(
    key: int, threshold: int
) -> None:
    keyboard = KeyboardController(InputConfig())
    keyboard.handle_event(press(key), 0)
    assert keyboard.handle_event(release(key), threshold) == []
    keyboard.handle_event(press(key), 2 * threshold)
    keyboard.poll(3 * threshold - 10, is_pressed={key}.__contains__)
    assert keyboard.handle_event(release(key), 3 * threshold) == []


@pytest.mark.parametrize("key", [pygame.K_UP, pygame.K_DOWN])
@pytest.mark.parametrize("focus_lost", [True, False])
def test_loss_of_pressed_state_cancels_hold(key: int, focus_lost: bool) -> None:
    keyboard = KeyboardController(InputConfig())
    keyboard.handle_event(press(key), 0)
    keyboard.poll(100, is_pressed={key}.__contains__)
    if focus_lost:
        keyboard.handle_event(pygame.event.Event(pygame.WINDOWFOCUSLOST), 200)
    else:
        assert keyboard.poll(200, is_pressed=set().__contains__) == []
    assert keyboard.poll(16000, is_pressed={key}.__contains__) == []
    assert keyboard.handle_event(release(key), 16100) == []


def test_custom_hold_threshold() -> None:
    keyboard = KeyboardController(InputConfig(shutdown_hold_ms=18000))
    keyboard.handle_event(press(pygame.K_DOWN), 0)
    held = {pygame.K_DOWN}.__contains__
    assert keyboard.poll(15000, is_pressed=held) == []
    assert keyboard.poll(18000, is_pressed=held) == [Action.SHUTDOWN]


def test_view_change_consumes_held_arrows_until_release() -> None:
    keyboard = KeyboardController(InputConfig())
    held = {pygame.K_UP, pygame.K_DOWN}.__contains__
    keyboard.handle_event(press(pygame.K_UP), 0)
    keyboard.handle_event(press(pygame.K_DOWN), 50)
    assert keyboard.poll(5000, is_pressed=held) == [Action.OPEN_MENU]
    keyboard.view_changed()
    assert keyboard.handle_event(press(pygame.K_UP), 5100, View.MAIN_MENU) == []
    assert keyboard.handle_event(press(pygame.K_DOWN), 5100, View.MAIN_MENU) == []
    assert keyboard.poll(20000, is_pressed=held) == []
    assert keyboard.handle_event(release(pygame.K_DOWN), 21000, View.MAIN_MENU) == []
    assert keyboard.handle_event(release(pygame.K_UP), 21000, View.MAIN_MENU) == []
    assert keyboard.handle_event(press(pygame.K_UP), 22000, View.MAIN_MENU) == [
        Action.CYCLE_FONT_SIZE
    ]
