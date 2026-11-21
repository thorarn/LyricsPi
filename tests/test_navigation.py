import pytest

from lyricspi import Action
from lyricspi.navigation import Navigation


@pytest.mark.parametrize(
    ("start", "action", "expected"),
    [
        (0, Action.NEXT_SONG, 1),
        (1, Action.PREVIOUS_SONG, 0),
        (2, Action.NEXT_SONG, 0),
        (0, Action.PREVIOUS_SONG, 2),
    ],
)
def test_song_navigation_wraps_and_resets_page(
    start: int, action: Action, expected: int
) -> None:
    nav = Navigation(song_index=start, page_index=3)
    nav.apply_action(action, song_count=3, page_count=4)

    assert (nav.song_index, nav.page_index) == (expected, 0)


@pytest.mark.parametrize(
    ("start", "action", "expected"),
    [
        (0, Action.NEXT_PAGE, 1),
        (1, Action.PREVIOUS_PAGE, 0),
        (0, Action.PREVIOUS_PAGE, 0),
        (2, Action.NEXT_PAGE, 2),
    ],
)
def test_page_navigation_stays_in_song(
    start: int, action: Action, expected: int
) -> None:
    nav = Navigation(song_index=1, page_index=start)
    nav.apply_action(action, song_count=3, page_count=3)

    assert (nav.song_index, nav.page_index) == (1, expected)


def test_empty_setlist_and_single_song() -> None:
    nav = Navigation()
    for action in Action:
        nav.apply_action(action, song_count=0, page_count=0)
    assert (nav.song_index, nav.page_index) == (0, 0)

    nav.apply_action(Action.NEXT_PAGE, song_count=1, page_count=3)
    assert nav.page_index == 1
    nav.apply_action(Action.PREVIOUS_SONG, song_count=1, page_count=3)
    assert (nav.song_index, nav.page_index) == (0, 0)


def test_relayout_clamps_only_when_needed() -> None:
    nav = Navigation(song_index=2, page_index=3)
    nav.clamp_page(8)
    assert nav.page_index == 3
    nav.clamp_page(2)
    assert nav.page_index == 1
    nav.clamp_page(0)
    assert (nav.song_index, nav.page_index) == (2, 0)
