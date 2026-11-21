"""Zero-based navigation for songs and pages."""

from dataclasses import dataclass

from . import Action


@dataclass
class Navigation:
    song_index: int = 0
    page_index: int = 0

    def clamp_page(self, page_count: int) -> None:
        self.page_index = max(0, min(self.page_index, page_count - 1))

    def apply_action(
        self, action: Action, song_count: int, page_count: int
    ) -> None:
        if not song_count:
            return
        if action in (Action.PREVIOUS_SONG, Action.NEXT_SONG):
            step = 1 if action is Action.NEXT_SONG else -1
            self.song_index = (self.song_index + step) % song_count
            self.page_index = 0
        elif action in (Action.PREVIOUS_PAGE, Action.NEXT_PAGE):
            self.page_index += 1 if action is Action.NEXT_PAGE else -1
            self.clamp_page(page_count)
