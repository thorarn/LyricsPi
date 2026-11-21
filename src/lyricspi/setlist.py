"""Song metadata and the ordered, read-only setlist."""

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Song:
    number: int
    filename: str
    path: Path
    title: str
    content: str


@dataclass(frozen=True)
class Setlist:
    songs: tuple[Song, ...] = ()

    def __len__(self) -> int:
        return len(self.songs)

    def __getitem__(self, index: int) -> Song:
        return self.songs[index]

    @property
    def first(self) -> Song | None:
        return self.songs[0] if self.songs else None

    @property
    def last(self) -> Song | None:
        return self.songs[-1] if self.songs else None
