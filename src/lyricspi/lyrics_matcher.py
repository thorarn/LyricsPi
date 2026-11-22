"""Match timed words against the original song lines."""

import logging
import re
import unicodedata
from dataclasses import dataclass, replace
from difflib import SequenceMatcher
from functools import lru_cache

from .speech_recognition import Word


LOGGER = logging.getLogger(__name__)


def tokens(text: str) -> tuple[str, ...]:
    text = unicodedata.normalize("NFKC", text).casefold()
    text = re.sub(r"(?<=\w)['’](?=\w)", "", text)
    return tuple(re.findall(r"[^\W_]+", text))


@lru_cache(maxsize=4096)
def _similarity(left: str, right: str) -> float:
    if left == right:
        return 1.0
    if min(len(left), len(right)) < 4 or abs(len(left) - len(right)) > 2:
        return 0.0
    ratio = SequenceMatcher(None, left, right, autojunk=False).ratio()
    return ratio if ratio >= 0.74 else 0.0


@dataclass(frozen=True)
class LyricLine:
    id: int
    words: tuple[str, ...]
    text: str


@dataclass(frozen=True)
class Match:
    index: int
    line_id: int
    score: float
    start: float
    end: float
    word_count: int
    fresh_words: int
    lead_in: bool = False


def _has_lead_in(previous: Match | None, hit: Match) -> bool:
    return previous is not None and -0.1 <= hit.start - previous.end <= 1.6


def _match_line(
    line: LyricLine, index: int, heard: tuple[tuple[str, Word], ...],
    fresh_since: float,
) -> Match | None:
    if len(line.words) < 2:
        return None
    # Ordered alignment. Skipping a lyric word costs coverage, while unrelated
    # words inside a matched phrase also incur a small insertion penalty.
    empty = (0.0, 0, 0, 0, 0)
    previous = [empty] * (len(heard) + 1)
    for expected in line.words:
        row = [empty]
        for column, (word, timed) in enumerate(heard, 1):
            score, fresh, count, start, end = row[-1]
            skipped = (score - 0.18, fresh, count, start, end)
            best = max(empty, previous[column], skipped)
            spellings = [(column, _similarity(expected, word))]
            if column > 1 and len(expected) >= 5:
                other, before = heard[column - 2]
                if min(len(other), len(word)) >= 2 and -0.1 <= timed.start - before.end <= 0.25:
                    # Whisper sometimes splits one lyric word into two tokens.
                    spellings.append((column - 1, 0.95 * _similarity(expected, other + word)))
            for first, similarity in spellings:
                if not similarity:
                    continue
                onset = heard[first - 1][1].start
                new = int(onset >= fresh_since - 0.1 and timed.end > fresh_since + 0.15)
                score, fresh, count, start, end = previous[first - 1]
                best = max(best, (similarity, new, 1, first, column))
                if count and onset - heard[end - 1][1].end <= 1.8:
                    best = max(best, (score + similarity, fresh + new, count + 1, start, column))
            row.append(best)
        previous = row
    score, fresh, count, start, end = max(previous)
    if count < 2:
        return None
    return Match(
        index, line.id, score / len(line.words),
        heard[start - 1][1].start, heard[end - 1][1].end,
        count, fresh,
    )


class LyricsMatcher:
    def __init__(self, content: str, threshold: float) -> None:
        self.lines = tuple(
            LyricLine(index, words, line.strip())
            for index, line in enumerate(content.splitlines())
            if not re.fullmatch(r"\s*\[.*\]\s*", line)
            if (words := tokens(line))
        )
        self.threshold = threshold

    def expected_index(self, first_line: int, current: Match | None) -> int:
        if current is not None:
            return current.index + 1
        return next(
            (i for i, line in enumerate(self.lines) if line.id >= first_line),
            len(self.lines),
        )

    def find(
        self, words: tuple[Word, ...], first_line: int, current: Match | None,
        *, fresh_since: float = float("-inf"),
    ) -> Match | None:
        heard = tuple((token, word) for word in words for token in tokens(word.text))
        if len(heard) < 2:
            LOGGER.debug("Textabgleich verworfen (weniger als zwei verwertbare Wörter).")
            return None
        candidates = [
            hit for index, line in enumerate(self.lines)
            if (hit := _match_line(line, index, heard, fresh_since)) is not None
        ]
        matches = [hit for hit in candidates if hit.score >= self.threshold]
        expected = self.expected_index(first_line, current)
        by_index = {hit.index: hit for hit in matches}
        ranked: list[tuple[float, Match]] = []
        rejected = {hit.index: "Score unter Schwelle" for hit in candidates}
        for hit in matches:
            if hit.index < expected or (current and hit.start < current.end - 0.25):
                rejected[hit.index] = "vor der erwarteten Position oder bereits bestätigt"
                continue
            if not hit.fresh_words:
                rejected[hit.index] = "nur bereits verarbeitetes Audio"
                continue
            context = _has_lead_in(by_index.get(hit.index - 1), hit)
            neighbors = [
                other for other in matches if other.index != hit.index
                and abs(hit.score - other.score) < 0.07
                and other.start < hit.end and hit.start < other.end
            ]
            if neighbors:
                # For repeated phrases, require a unique lead-in or an
                # immediately preceding confirmed line with fresh word timing.
                confirmed_lead_in = (
                    current is not None and hit.index == expected
                    and -0.1 <= hit.start - current.end <= 6
                    and self.lines[current.index].words != self.lines[hit.index].words
                )
                unique_context = context and not any(
                    _has_lead_in(by_index.get(other.index - 1), other)
                    for other in neighbors
                )
                if not (confirmed_lead_in or unique_context):
                    rejected[hit.index] = "mehrdeutige Wiederholung ohne eindeutigen Kontext"
                    continue
            distance = hit.index - expected
            if distance > 3 and (hit.score < 0.90 or not context or hit.fresh_words < 3):
                rejected[hit.index] = "zu wenig Evidenz für einen großen Positionssprung"
                continue
            rank = hit.score + (0.10 if context else 0) - min(0.22, 0.025 * distance)
            ranked.append((rank, replace(hit, lead_in=context)))
            rejected.pop(hit.index)
        ranked.sort(key=lambda item: (-item[0], item[1].index))
        selected = ranked[0][1] if ranked else None
        best = max(candidates, key=lambda hit: hit.score, default=None)
        if best is not None:
            LOGGER.debug(
                "Bester Texttreffer Zeile %d %r, Score %.2f, %d neue Wörter: %s",
                best.line_id + 1, self.lines[best.index].text, best.score,
                best.fresh_words, rejected.get(best.index, "plausibel"),
            )
        return selected
