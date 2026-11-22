"""Run short overlapping local Whisper transcriptions off the UI thread."""

import logging
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from queue import Empty, Queue
from threading import Event, Thread
from time import monotonic
from typing import TYPE_CHECKING

from .audio_capture import AudioBlock, put_latest, windows_loopback
from .config import PROJECT_ROOT, LyricsFollowingConfig

if TYPE_CHECKING:
    import numpy as np
    from faster_whisper import WhisperModel
    from numpy.typing import NDArray


LOGGER = logging.getLogger(__name__)
MAX_RESULT_AGE = 5.0
WHISPER_RATE = 16000
SILENCE_RMS = 0.002


@dataclass(frozen=True)
class Word:
    text: str
    start: float
    end: float
    quality: float


@dataclass(frozen=True)
class Transcript:
    start: float
    end: float
    words: tuple[Word, ...] = ()
    pause_ms: int = 0
    continuity: int = 0


@dataclass(frozen=True)
class RecognitionHints:
    initial_prompt: str | None = None
    hotwords: str | None = None


@dataclass(frozen=True)
class AudioWindow:
    start: float
    end: float
    pcm: bytes


class AudioWindows:
    """Assemble overlapping windows on the sample clock."""

    def __init__(
        self, rate: int, channels: int, window_seconds: int = 6, overlap_seconds: int = 2,
    ) -> None:
        self.bytes_per_second = rate * channels * 2
        self.window_bytes = window_seconds * self.bytes_per_second
        self.hop_bytes = (window_seconds - overlap_seconds) * self.bytes_per_second
        self.buffer = bytearray()
        self.previous: AudioBlock | None = None
        self.continuity = 0

    def append(self, block: AudioBlock) -> AudioWindow | None:
        previous = self.previous
        if block.discontinuity or (
            previous is not None and (
                previous.sequence + 1 != block.sequence
                or block.end - previous.end > len(block.pcm) / self.bytes_per_second + 0.25
            )
        ):
            self.buffer.clear()
            self.continuity += 1
        self.previous = block
        self.buffer.extend(block.pcm)
        surplus = len(self.buffer) - self.window_bytes
        if surplus < 0:
            return None
        end = block.end - surplus / self.bytes_per_second
        window = AudioWindow(
            end - self.window_bytes / self.bytes_per_second,
            end, bytes(self.buffer[:self.window_bytes]),
        )
        del self.buffer[:self.hop_bytes]
        return window


def _load_model(selection: str) -> "WhisperModel":
    try:
        from faster_whisper import WhisperModel, download_model
    except ImportError as error:
        raise RuntimeError("faster-whisper fehlt. Installiere .[lyrics-following].") from error

    directory = PROJECT_ROOT / Path(selection)
    if not directory.is_dir():
        try:
            directory = Path(download_model(selection, local_files_only=True))
        except (OSError, ValueError) as error:
            raise RuntimeError(
                f"Whisper-Modell {selection!r} fehlt lokal. Siehe docs/lyrics-following.md."
            ) from error
    for filename in ("model.bin", "config.json", "tokenizer.json"):
        if not (directory / filename).is_file():
            raise RuntimeError(f"Im lokalen Whisper-Modell fehlt {directory / filename}.")
    return WhisperModel(
        str(directory), device="cpu", compute_type="int8",
        cpu_threads=2, local_files_only=True,
    )


def _prepare_pcm(pcm: bytes, rate: int, channels: int) -> "NDArray[np.float32]":
    """Convert interleaved WASAPI Int16 PCM into Whisper's 16 kHz mono input."""
    import numpy as np

    if rate < 1 or channels < 1 or len(pcm) % (2 * channels):
        raise ValueError("Ungültiges WASAPI-PCM-Format oder unvollständiger Audioframe.")

    samples = np.frombuffer(pcm, dtype="<i2").astype(np.float32)
    if channels > 1:
        samples = samples.reshape(-1, channels).mean(axis=1)
    samples *= 1 / 32768
    if rate == WHISPER_RATE or not samples.size:
        return samples

    if rate > WHISPER_RATE:
        # A centered low-pass filter suppresses aliasing without shifting the window.
        radius = (16 * rate + WHISPER_RATE - 1) // WHISPER_RATE
        offsets = np.arange(-radius, radius + 1)
        cutoff = 0.45 * WHISPER_RATE / rate
        kernel = np.sinc(2 * cutoff * offsets) * np.hanning(offsets.size)
        kernel = (kernel / kernel.sum()).astype(np.float32)
        padded = np.pad(samples, radius, mode="edge")
        samples = np.convolve(padded, kernel, mode="valid")
        np.clip(samples, -1, 32767 / 32768, out=samples)

    count = (samples.size * WHISPER_RATE + rate // 2) // rate
    positions = np.arange(count) * (rate / WHISPER_RATE)
    return np.interp(positions, np.arange(samples.size), samples).astype(np.float32)


def _transcribe(
    model: "WhisperModel", pcm: bytes, rate: int, channels: int, language: str,
    start: float, end: float, continuity: int, *, beam_size: int = 5,
    hints: RecognitionHints = RecognitionHints(),
) -> Transcript:
    import numpy as np

    samples = _prepare_pcm(pcm, rate, channels)
    if not samples.size or np.mean(samples ** 2) <= SILENCE_RMS ** 2:
        return Transcript(
            start, end, pause_ms=round((end - start) * 1000), continuity=continuity,
        )

    tail = 0
    step = WHISPER_RATE // 10
    for stop in range(len(samples), step - 1, -step):
        if np.mean(samples[stop - step:stop] ** 2) > SILENCE_RMS ** 2:
            break
        tail += 100

    segments, _ = model.transcribe(
        samples, language=language, beam_size=beam_size, word_timestamps=True,
        condition_on_previous_text=False, temperature=0.0,
        initial_prompt=hints.initial_prompt, hotwords=hints.hotwords,
        max_new_tokens=max(16, round(8 * (end - start))),
    )
    words = tuple(
        Word(word.word, start + word.start, start + word.end, word.probability)
        for segment in segments
        for word in (segment.words or ())
        if word.probability >= 0.25 and word.start < word.end
    )
    return Transcript(start, end, words, tail, continuity)


class RecognitionWorker:
    def __init__(
        self, config: LyricsFollowingConfig,
        context: Callable[[], tuple[RecognitionHints, Callable[[Transcript], None]]],
    ) -> None:
        self.config = config
        self.context = context
        self.failed = Event()
        self._stop = Event()
        self._thread = Thread(target=self._run, name="LyricsPi speech", daemon=True)

    def start(self) -> None:
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()

    @property
    def finished(self) -> bool:
        return not self._thread.is_alive()

    def close(self) -> None:
        self.stop()
        if self._thread.is_alive():
            self._thread.join(timeout=2)
        if self._thread.is_alive():
            LOGGER.warning("Die laufende Whisper-Analyse konnte noch nicht beendet werden.")

    def _run(self) -> None:
        try:
            model = _load_model(self.config.model)
            if self._stop.is_set():
                return
            LOGGER.info("Lokales Whisper-Modell bereit (%s, %s, CPU).",
                        self.config.model, self.config.language)
            blocks: Queue[AudioBlock] = Queue(maxsize=10 * (self.config.window_seconds + 1))
            with windows_loopback(
                self.config.audio_device, blocks, self._stop.is_set
            ) as source:
                self._recognize(model, blocks, *source)
        except Exception as error:
            if not self._stop.is_set():
                self.failed.set()
                LOGGER.warning("Textverfolgung beendet, manuelle Bedienung aktiv: %s", error)
                LOGGER.debug("Fehlerdetails der Textverfolgung", exc_info=True)

    def _recognize(
        self, model: "WhisperModel", blocks: Queue[AudioBlock], rate: int, channels: int,
        active: Callable[[], bool],
    ) -> None:
        windows = AudioWindows(
            rate, channels, self.config.window_seconds, self.config.overlap_seconds,
        )
        while not self._stop.is_set():
            if not active():
                raise OSError("WASAPI-Aufnahmestrom wurde unterbrochen.")
            try:
                block = blocks.get(timeout=0.2)
            except Empty:
                continue
            window = windows.append(block)
            if window is None or monotonic() - window.end > 1:
                continue
            hints, publish = self.context()
            started = monotonic()
            result = _transcribe(
                model, window.pcm, rate, channels, self.config.language,
                window.start, window.end, windows.continuity,
                beam_size=self.config.beam_size, hints=hints,
            )
            elapsed = monotonic() - started
            LOGGER.debug(
                "Whisper %s, Fenster %.2f–%.2f, Transkription %.0f ms, Pause %d ms, Wörter: %s",
                self.config.model, result.start, result.end, elapsed * 1000, result.pause_ms,
                " ".join(f"{w.text.strip()}@{w.start:.2f}({w.quality:.2f})"
                         for w in result.words) or "keine",
            )
            if not self._stop.is_set() and monotonic() - result.end <= MAX_RESULT_AGE:
                publish(result)
            elif not self._stop.is_set():
                LOGGER.debug("Whisper-Fenster %.2f verworfen (Ergebnis zu alt).", result.end)
