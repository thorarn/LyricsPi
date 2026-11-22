"""Capture Windows playback in bounded, in-memory PCM blocks."""

import logging
from collections.abc import Callable, Iterator, Sequence
from contextlib import contextmanager
from dataclasses import dataclass
from queue import Empty, Full, Queue
from time import monotonic
from typing import TypeVar


LOGGER = logging.getLogger(__name__)
T = TypeVar("T")


def put_latest(queue: Queue[T], item: T) -> None:
    """Drop old data rather than blocking a producer."""
    try:
        queue.put_nowait(item)
    except Full:
        try:
            queue.get_nowait()
        except Empty:
            pass
        queue.put_nowait(item)


@dataclass(frozen=True)
class AudioBlock:
    pcm: bytes
    end: float
    sequence: int
    discontinuity: bool = False


def select_loopback(
    devices: Sequence[dict], selection: str, default_name: str = "",
) -> dict:
    if selection == "default":
        matches = [
            device for device in devices
            if device["name"].removesuffix(" [Loopback]") == default_name
        ]
    else:
        matches = [
            device for device in devices
            if selection in (str(device["index"]), device["name"])
        ]
    if len(matches) != 1:
        reason = "mehrdeutig" if matches else "nicht verfügbar"
        raise OSError(f"WASAPI-Loopback-Gerät {selection!r} ist {reason}.")
    return matches[0]


@contextmanager
def windows_loopback(
    selection: str, blocks: Queue[AudioBlock], stopping: Callable[[], bool],
) -> Iterator[tuple[int, int, Callable[[], bool]]]:
    try:
        import pyaudiowpatch as audio
    except ImportError as error:
        raise RuntimeError("PyAudioWPatch fehlt. Installiere .[lyrics-following].") from error

    with audio.PyAudio() as manager:
        devices = list(manager.get_loopback_device_info_generator())
        LOGGER.info(
            "WASAPI-Loopback-Geräte: %s",
            ", ".join(f'{d["index"]}: {d["name"]}' for d in devices) or "keine",
        )
        default_name = ""
        if selection == "default":
            default_name = manager.get_default_wasapi_device(d_out=True)["name"]
        device = select_loopback(devices, selection, default_name)
        rate = int(device["defaultSampleRate"])
        channels = int(device["maxInputChannels"])
        sequence = 0

        def receive(
            data: bytes, _frame_count: int, _time_info: dict, status: int,
        ) -> tuple[None, int]:
            nonlocal sequence
            if stopping():
                return None, audio.paComplete
            sequence += 1
            if data:
                # Callback arrival approximates the end of this playback block.
                put_latest(blocks, AudioBlock(data, monotonic(), sequence, bool(status)))
            return None, audio.paContinue

        LOGGER.info("WASAPI-Aufnahme: %s (%d Hz, %d Kanäle)", device["name"], rate, channels)
        with manager.open(
            format=audio.paInt16, channels=channels, rate=rate, input=True,
            input_device_index=device["index"], frames_per_buffer=rate // 10,
            stream_callback=receive,
        ) as stream:
            try:
                yield rate, channels, stream.is_active
            finally:
                LOGGER.debug("WASAPI-Aufnahme beendet.")
