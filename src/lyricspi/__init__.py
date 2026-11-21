"""LyricsPi and its shared input actions."""

from enum import Enum, auto


class Action(Enum):
    PREVIOUS_SONG = auto()
    NEXT_SONG = auto()
    PREVIOUS_PAGE = auto()
    NEXT_PAGE = auto()
    FONT_SMALLER = auto()
    FONT_LARGER = auto()
    EXIT = auto()
