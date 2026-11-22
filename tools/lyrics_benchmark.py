"""Replay a local 16-bit PCM WAV against timestamped lyrics and compare models."""

import argparse
import json
import logging
import wave
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path
from statistics import mean
from time import perf_counter

from lyricspi.audio_capture import AudioBlock
from lyricspi.config import LyricsFollowingConfig, load_config
from lyricspi.lyrics_follower import PositionTracker
from lyricspi.lyrics_matcher import LyricsMatcher, Match
from lyricspi.speech_recognition import (
    MAX_RESULT_AGE, AudioWindow, AudioWindows, _load_model, _transcribe,
)


LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True)
class Cue:
    line_id: int
    start: float
    end: float


def load_cues(path: Path, lyrics: str, duration: float) -> tuple[Cue, ...]:
    data = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(data, list) or not data:
        raise ValueError("Die Zeitmarken müssen eine nicht leere JSON-Liste sein.")
    valid_ids = {line.id for line in LyricsMatcher(lyrics, 0.75).lines}
    cues: list[Cue] = []
    for row in data:
        if (
            not isinstance(row, dict)
            or type(row.get("line")) is not int
            or type(row.get("start")) not in (float, int)
            or type(row.get("end")) not in (float, int)
        ):
            raise ValueError("Jede Zeitmarke braucht line, start und end als Zahlen.")
        cue = Cue(row["line"] - 1, row["start"], row["end"])
        if (
            cue.line_id not in valid_ids or not 0 <= cue.start < cue.end <= duration
            or (cues and (cue.start < cues[-1].end or cue.line_id <= cues[-1].line_id))
        ):
            raise ValueError(f"Ungültige oder überlappende Zeitmarke {row!r}.")
        cues.append(cue)
    return tuple(cues)


def audio_windows(
    audio: wave.Wave_read, config: LyricsFollowingConfig,
) -> Iterator[AudioWindow]:
    rate = audio.getframerate()
    channels = audio.getnchannels()
    frames = audio.getnframes()
    width = rate * config.window_seconds
    hop = rate * (config.window_seconds - config.overlap_seconds)
    total = width + max(0, (frames - width + hop - 1) // hop) * hop
    block_size = max(1, rate // 10)
    audio.rewind()
    windows = AudioWindows(rate, channels, config.window_seconds, config.overlap_seconds)
    for sequence, start in enumerate(range(0, total, block_size), 1):
        count = min(block_size, total - start)
        pcm = audio.readframes(count).ljust(count * channels * 2, b"\0")
        window = windows.append(AudioBlock(pcm, (start + count) / rate, sequence))
        if window is not None:
            yield window


def score(
    matches: list[tuple[Match, float]], cues: tuple[Cue, ...],
) -> tuple[int, int, float | None]:
    by_line = {cue.line_id: cue for cue in cues}
    delays: dict[int, float] = {}
    false_jumps = 0
    for match, published_at in matches:
        cue = by_line.get(match.line_id)
        midpoint = (match.start + match.end) / 2
        if cue is not None and cue.start <= midpoint < cue.end:
            delays.setdefault(cue.line_id, published_at - cue.start)
        else:
            false_jumps += 1
    return len(delays), false_jumps, mean(delays.values()) if delays else None


def benchmark(
    label: str, model_path: str, audio: wave.Wave_read, lyrics: str,
    cues: tuple[Cue, ...], config: LyricsFollowingConfig,
) -> str:
    model = _load_model(model_path)
    tracker = PositionTracker(LyricsMatcher(lyrics, config.confidence_threshold), 0, 0)
    matches: list[tuple[Match, float]] = []
    elapsed_times = []
    available_at = 0.0
    for window in audio_windows(audio, config):
        started_at = max(available_at, window.end)
        if started_at - window.end > 1:
            LOGGER.debug("%s %.2f verworfen (Analyse im Rückstand).", label, window.end)
            continue
        hints = tracker.hints(config)
        clock = perf_counter()
        result = _transcribe(
            model, window.pcm, audio.getframerate(), audio.getnchannels(), config.language,
            window.start, window.end, 0, beam_size=config.beam_size, hints=hints,
        )
        elapsed = perf_counter() - clock
        elapsed_times.append(elapsed)
        available_at = started_at + elapsed
        LOGGER.debug(
            "%s %.2f–%.2f, %.0f ms, %r",
            label, window.start, window.end, elapsed * 1000,
            " ".join(word.text.strip() for word in result.words),
        )
        if available_at - window.end <= MAX_RESULT_AGE:
            match = tracker.update(result)
            if match is not None:
                matches.append((match, available_at))
    hits, false_jumps, delay = score(matches, cues)
    latency = f"{delay:.2f} s" if delay is not None else "–"
    return (
        f"| {label} | {hits}/{len(cues)} ({hits / len(cues):.0%}) | {false_jumps} "
        f"| {latency} | {mean(elapsed_times):.2f} s | {len(elapsed_times)} |"
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("audio", type=Path, help="Lokale 16-Bit-PCM-WAV-Datei")
    parser.add_argument("lyrics", type=Path, help="Zugehöriger Songtext in UTF-8")
    parser.add_argument("cues", type=Path, help="JSON-Zeitmarken pro Textzeile")
    parser.add_argument("--config", type=Path, help="LyricsPi-Konfiguration für den Vergleich")
    parser.add_argument("--model", action="append", help="Modellname oder Name=lokaler Pfad")
    parser.add_argument("--debug", action="store_true")
    args = parser.parse_args()
    logging.basicConfig(level=logging.WARNING, format="%(levelname)s %(message)s")
    if args.debug:
        logging.getLogger(__name__).setLevel(logging.DEBUG)
        logging.getLogger("lyricspi").setLevel(logging.DEBUG)
    models = args.model or ("tiny", "base", "small")
    try:
        config = load_config(args.config).lyrics_following if args.config else LyricsFollowingConfig()
        lyrics = args.lyrics.read_text(encoding="utf-8-sig")
        with wave.open(str(args.audio), "rb") as audio:
            if audio.getsampwidth() != 2 or not audio.getnframes():
                raise ValueError("Die WAV-Datei muss 16-Bit-PCM-Audio enthalten.")
            cues = load_cues(args.cues, lyrics, audio.getnframes() / audio.getframerate())
            print("| Modell | Zeilentreffer | Fehlsprünge | Verzögerung Ø | Zeit/Fenster Ø | Fenster |")
            print("|---|---:|---:|---:|---:|---:|")
            failures = False
            for selection in models:
                label, _, model_path = selection.partition("=")
                try:
                    print(benchmark(label, model_path or label, audio, lyrics, cues, config), flush=True)
                except (RuntimeError, OSError, ValueError) as error:
                    LOGGER.error("%s: %s", label, error)
                    failures = True
            return int(failures)
    except (OSError, ValueError, wave.Error) as error:
        parser.error(str(error))


if __name__ == "__main__":
    raise SystemExit(main())
