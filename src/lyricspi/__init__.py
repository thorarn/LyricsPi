"""LyricsPi and its shared input actions."""

from enum import Enum, auto


class Action(Enum):
    PREVIOUS_SONG = auto()
    NEXT_SONG = auto()
    PREVIOUS_PAGE = auto()
    NEXT_PAGE = auto()
    FONT_SMALLER = auto()
    FONT_LARGER = auto()
    CYCLE_FONT_SIZE = auto()
    ROTATE_DISPLAY = auto()
    OPEN_MENU = auto()
    OPEN_SONG_LIST = auto()
    BACK = auto()
    SELECT_PREVIOUS = auto()
    SELECT_NEXT = auto()
    OPEN_SELECTED_SONG = auto()
    EXIT = auto()
    SHUTDOWN = auto()


class View(Enum):
    SONG_VIEW = auto()
    MAIN_MENU = auto()
    SONG_LIST = auto()
