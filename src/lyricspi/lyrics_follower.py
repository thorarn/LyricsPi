"""Confirm lyric positions and propose forward page turns for the simulator."""

import logging
from collections.abc import Callable
from dataclasses import dataclass
from queue import Empty, Queue
from time import monotonic

from .audio_capture import put_latest
from .config import LyricsFollowingConfig
from .lyrics_matcher import LyricsMatcher, Match, tokens
from .speech_recognition import (
    MAX_RESULT_AGE, RecognitionHints, RecognitionWorker, Transcript, Word,
)


LOGGER = logging.getLogger(__name__)
TURN_GRACE = 0.35
MAX_WORD_AGE = 7.0


class PositionTracker:
    def __init__(self, matcher: LyricsMatcher, first_line: int, since: float) -> None:
        self.matcher = matcher
        self.first_line = first_line
        self.since = since
        self.current: Match | None = None
        self.pending: Match | None = None
        self.history: tuple[Word, ...] = ()
        self.last_end = since
        self.continuity: int | None = None

    def hints(self, config: LyricsFollowingConfig) -> RecognitionHints:
        if not config.use_initial_prompt and not config.hotwords:
            return RecognitionHints()
        index = self.matcher.expected_index(self.first_line, self.current)
        start = index - 1 if self.current is not None else index
        lines = self.matcher.lines[start:start + 3]
        context = " ".join(dict.fromkeys(line.text for line in lines))
        prompt = " ".join(context.split()[:32])[:160].strip()
        available = f" {' '.join(tokens(context))} "
        hotwords = []
        for entry in config.hotwords.split(","):
            words = tokens(entry)
            if words and f" {' '.join(words)} " in available:
                hotwords.append(entry.strip())
        hotword_hint = " ".join(dict.fromkeys(hotwords[:8]))[:96].strip()
        return RecognitionHints(
            initial_prompt=(prompt or None) if config.use_initial_prompt else None,
            hotwords=hotword_hint or None,
        )

    def update(self, result: Transcript) -> Match | None:
        if result.end <= self.last_end:
            LOGGER.debug("Fenster %.2f verworfen (bereits verarbeitet).", result.end)
            return None
        if self.continuity != result.continuity or result.start > self.last_end + 0.3:
            self.pending = None
            self.history = ()
        fresh_since = self.last_end
        self.continuity = result.continuity
        self.last_end = result.end
        words = tuple(
            word for word in self.history
            if result.start - 3 <= word.start and word.end <= result.start
        ) + tuple(
            word for word in result.words
            if word.start >= max(self.since, result.start) and word.end <= result.end + 0.05
        )
        # Keep a short prefix for long sung lines spanning two windows. Only
        # the newer hypothesis supplies words within the overlapping portion.
        self.history = tuple(word for word in words if word.end >= result.end - 9)
        current_line = self.current.line_id + 1 if self.current else None
        hit = self.matcher.find(
            words, self.first_line, self.current, fresh_since=fresh_since,
        )
        if hit is None:
            LOGGER.debug(
                "Fenster %.2f ohne neuen eindeutigen Treffer, bestätigt %s.",
                result.end, current_line,
            )
            return None
        if result.end - hit.end > MAX_WORD_AGE:
            LOGGER.debug("Treffer Zeile %d verworfen (Audio zu alt).", hit.line_id + 1)
            return None
        expected = self.matcher.expected_index(self.first_line, self.current)
        distance = hit.index - expected
        previous = self.pending
        strong_phrase = hit.fresh_words >= 3 and hit.score >= 0.86 and distance <= 1
        joined_phrase = (
            distance <= 1 and hit.word_count >= 4
            and 2 <= hit.fresh_words < hit.word_count and hit.score >= 0.92
        )
        ordered_context = hit.lead_in and hit.fresh_words >= 2
        follows_pending = previous is not None and (
            (hit.index == previous.index + 1 and -0.1 <= hit.start - previous.end <= 2.5)
            or (hit.index == previous.index and hit.start <= previous.end
                and hit.end > previous.end + 0.15 and hit.word_count > previous.word_count)
        )
        if not (strong_phrase or joined_phrase or ordered_context or follows_pending):
            self.pending = hit
            LOGGER.debug(
                "Zeile %d %r, Score %.2f vorläufig (zu wenig neue Evidenz), bestätigt %s.",
                hit.line_id + 1, self.matcher.lines[hit.index].text, hit.score, current_line,
            )
            return None
        self.current = hit
        self.pending = None
        LOGGER.debug(
            "Zeile %d %r bestätigt, Score %.2f, bisher %s.",
            hit.line_id + 1, self.matcher.lines[hit.index].text, hit.score, current_line,
        )
        return hit


@dataclass(frozen=True)
class PositionUpdate:
    tracker: PositionTracker
    result: Transcript
    match: Match | None


@dataclass(frozen=True)
class PageTurn:
    target: int
    ready_at: float
    word_end: float


class LyricsFollower:
    def __init__(self, config: LyricsFollowingConfig) -> None:
        self.config = config
        self._content: str | None = None
        self._tracker: PositionTracker | None = None
        self._results: Queue[PositionUpdate] = Queue(maxsize=4)
        self._worker = RecognitionWorker(config, self._recognition_context)
        self._pending_turn: PageTurn | None = None
        self._last_turn = float("-inf")
        self._observed_target: int | None = None
        self.line_id: int | None = None
        self._line_end: float | None = None
        self._last_visible: int | None = None

    def start(self) -> None:
        self._worker.start()

    def close(self) -> None:
        self._worker.close()

    def stop(self) -> None:
        self._worker.stop()

    @property
    def finished(self) -> bool:
        return self._worker.finished

    def synchronize(
        self, content: str | None, first_line: int, now: float, *, manual: bool = False,
    ) -> None:
        matcher = (
            self._tracker.matcher
            if self._tracker is not None and content == self._content
            else None
        )
        self._content = content
        self._tracker = None if content is None else PositionTracker(
            matcher or LyricsMatcher(content, self.config.confidence_threshold),
            first_line, now,
        )
        self.line_id = None
        self._line_end = None
        self._last_visible = None
        self._pending_turn = None
        self._observed_target = None
        if manual:
            self._last_turn = now

    def _recognition_context(
        self,
    ) -> tuple[RecognitionHints, Callable[[Transcript], None]]:
        tracker = self._tracker
        if tracker is None:
            return RecognitionHints(), lambda result: None
        return tracker.hints(self.config), lambda result: self._process(result, tracker=tracker)

    def _process(self, result: Transcript, *, tracker: PositionTracker | None = None) -> None:
        tracker = tracker if tracker is not None else self._tracker
        if tracker is not None:
            match = tracker.update(result)
            put_latest(self._results, PositionUpdate(tracker, result, match))

    def _handle_update(
        self, update: PositionUpdate, page: int, page_ids: list[tuple[int, ...]],
        now: float,
    ) -> None:
        hit = update.match
        if hit is None:
            # Silence or ambiguity leaves the visible line in place.
            self._pending_turn = None
            return
        self.line_id = hit.line_id
        self._line_end = hit.end
        LOGGER.info(
            "Textposition Zeile %d bei t=%.2f (Matching-Score %.2f, Latenz %.0f ms)",
            hit.line_id + 1, hit.end, hit.score, (now - hit.end) * 1000,
        )
        self._pending_turn = None
        if not page_ids or hit.line_id in page_ids[page]:
            return
        target = next(
            (index for index in range(page + 1, len(page_ids))
             if hit.line_id in page_ids[index]),
            None,
        )
        if target is None or now - hit.end > MAX_WORD_AGE:
            return
        if self.config.mode == "observe" or not self.config.auto_page_turn:
            if target != self._observed_target:
                LOGGER.info("Möglicher Seitenwechsel %d → %d.", page + 1, target + 1)
                self._observed_target = target
            return
        if now - self._last_turn < self.config.min_turn_interval_ms / 1000:
            return
        wait_for_pause = (
            self.config.prefer_pause and update.result.pause_ms < self.config.pause_duration_ms
        )
        self._pending_turn = PageTurn(
            target, now + TURN_GRACE if wait_for_pause else now, hit.end,
        )

    def poll(
        self, page: int, page_ids: list[tuple[int, ...]], now: float,
    ) -> int | None:
        if self._worker.failed.is_set():
            self.line_id = None
            self._pending_turn = None
            return None
        for _ in range(self._results.maxsize):
            try:
                update = self._results.get_nowait()
            except Empty:
                break
            if (
                update.tracker is self._tracker
                and now - update.result.end <= MAX_RESULT_AGE
            ):
                self._handle_update(update, page, page_ids, now)
        turn = self._pending_turn
        if turn is None or now < turn.ready_at:
            return None
        self._pending_turn = None
        if page < turn.target < len(page_ids) and now - turn.word_end <= MAX_WORD_AGE:
            self._last_turn = now
            LOGGER.info("Automatischer Seitenwechsel %d → %d.", page + 1, turn.target + 1)
            return turn.target
        return None

    def layout_changed(self) -> None:
        self._pending_turn = None
        self._observed_target = None

    def mark_visible(self) -> None:
        if (
            self._line_end is not None and self.line_id is not None
            and self.line_id != self._last_visible
        ):
            self._last_visible = self.line_id
            LOGGER.debug(
                "Markierung Zeile %d sichtbar, %.0f ms nach Audio.",
                self.line_id + 1, (monotonic() - self._line_end) * 1000,
            )
