import json
import sys
import wave
from contextlib import contextmanager
from pathlib import Path
from queue import Queue
from threading import Event
from time import monotonic
from types import SimpleNamespace
from unittest.mock import MagicMock

import pygame
import pytest

from lyricspi import Action, app, speech_recognition
from lyricspi.audio_capture import AudioBlock, put_latest, select_loopback, windows_loopback
from lyricspi.config import Config, ConfigError, DisplayConfig, LyricsFollowingConfig, load_config
from lyricspi.layout import paginate
from lyricspi.lyrics_follower import LyricsFollower, PositionTracker
from lyricspi.lyrics_matcher import LyricsMatcher, Match
from lyricspi.renderer import LYRIC_HIGHLIGHT, Renderer
from lyricspi.setlist import Setlist, Song
from lyricspi.speech_recognition import (
    AudioWindow, AudioWindows, RecognitionHints, RecognitionWorker, Transcript, Word,
)
from tools.lyrics_benchmark import Cue, audio_windows, load_cues, score


def heard(text: str, end: float, *, start: float = 10, pause: int = 0) -> Transcript:
    words = tuple(
        Word(word, start + i * 0.2, start + (i + 1) * 0.2, 0.9)
        for i, word in enumerate(text.split())
    )
    return Transcript(end - 4, end, words, pause)


def test_loopback_defaults_and_explicit_devices() -> None:
    internal = {"name": "Lautsprecher [Loopback]", "index": 5}
    usb = {"name": "Lautsprecher (USB) [Loopback]", "index": 7}
    devices = [internal, usb]
    assert select_loopback(devices, "default", "Lautsprecher") is internal
    assert select_loopback(devices, "7") is usb
    assert select_loopback(devices, usb["name"]) is usb
    with pytest.raises(OSError, match="nicht verfügbar"):
        select_loopback(devices, "default", "HDMI")
    with pytest.raises(OSError, match="mehrdeutig"):
        select_loopback([internal, dict(internal, index=8)], "default", "Lautsprecher")


def test_unavailable_audio_source_falls_back_to_manual(monkeypatch, caplog) -> None:
    monkeypatch.setattr(speech_recognition, "_load_model", lambda _: object())

    @contextmanager
    def unavailable(*args):
        yield 48000, 2, lambda: False

    monkeypatch.setattr(speech_recognition, "windows_loopback", unavailable)
    follower = LyricsFollower(LyricsFollowingConfig(mode="auto", auto_page_turn=True))
    follower.line_id = 1
    follower.start()
    try:
        assert follower._worker.failed.wait(2)
        assert follower.poll(0, [(0,), (1,)], 10) is None
        assert follower.line_id is None
    finally:
        follower.close()
    assert "WASAPI-Aufnahmestrom wurde unterbrochen" in caplog.text


def test_loopback_callback_captures_and_releases_stream(monkeypatch) -> None:
    manager = MagicMock()
    manager.__enter__.return_value = manager
    manager.get_loopback_device_info_generator.return_value = [{
        "name": "Lautsprecher [Loopback]", "index": 5,
        "defaultSampleRate": 48000, "maxInputChannels": 2,
    }]
    backend = SimpleNamespace(
        PyAudio=lambda: manager, paInt16=8, paContinue=0, paComplete=1,
    )
    monkeypatch.setitem(sys.modules, "pyaudiowpatch", backend)
    queue: Queue[AudioBlock] = Queue(maxsize=2)
    stopping = Event()
    with windows_loopback("5", queue, stopping.is_set) as (rate, channels, _):
        assert (rate, channels) == (48000, 2)
        options = manager.open.call_args.kwargs
        assert options["input_device_index"] == 5
        assert "output" not in options
        receive = options["stream_callback"]
        assert receive(b"\0" * 19200, 4800, {}, 0) == (None, backend.paContinue)
        assert queue.get_nowait().pcm == b"\0" * 19200
        stopping.set()
        assert receive(b"\0" * 19200, 4800, {}, 0) == (None, backend.paComplete)
        assert queue.empty()
    manager.open.return_value.__exit__.assert_called_once()
    manager.__exit__.assert_called_once()


def test_audio_queue_drops_old_blocks_and_windows_overlap() -> None:
    queue: Queue[int] = Queue(maxsize=2)
    for index in range(10):
        put_latest(queue, index)
    assert [queue.get_nowait(), queue.get_nowait()] == [8, 9]

    windows = AudioWindows(10, 1)
    blocks = {n: bytes([n]) * 20 for n in range(1, 18)}
    emitted = [
        window for n in (*range(1, 11), *range(12, 18))
        if (window := windows.append(AudioBlock(blocks[n], n, n))) is not None
    ]
    assert emitted == [
        AudioWindow(start, start + 6, b"".join(blocks[n] for n in range(start + 1, start + 7)))
        for start in (0, 4, 11)
    ]
    assert windows.continuity == 1


@pytest.fixture
def numpy():
    return pytest.importorskip("numpy")


def test_mono_pcm_is_normalized_to_float32(numpy) -> None:
    pcm = numpy.array([-32768, -16384, 0, 16384, 32767], dtype="<i2")
    samples = speech_recognition._prepare_pcm(pcm.tobytes(), 16000, 1)

    assert samples.dtype == numpy.float32
    assert samples.shape == (5,)
    numpy.testing.assert_array_equal(samples, [-1, -0.5, 0, 0.5, 32767 / 32768])


def test_interleaved_stereo_is_averaged_without_int16_overflow(numpy) -> None:
    pcm = numpy.array([[32767, 32767], [-16384, 16384], [0, 16384]], dtype="<i2")
    samples = speech_recognition._prepare_pcm(pcm.tobytes(), 16000, 2)

    assert samples.dtype == numpy.float32
    numpy.testing.assert_array_equal(samples, [32767 / 32768, 0, 0.25])


@pytest.mark.parametrize("rate", [8000, 11025, 16000, 44100, 48000, 96000])
def test_resampling_preserves_duration_and_speech_band(numpy, rate) -> None:
    frames = rate // 5 + 7
    pcm = (16384 * numpy.sin(2 * numpy.pi * 660 * numpy.arange(frames) / rate))
    samples = speech_recognition._prepare_pcm(pcm.astype("<i2").tobytes(), rate, 1)

    assert samples.dtype == numpy.float32
    assert samples.shape == (round(frames * 16000 / rate),)
    expected = 0.5 * numpy.sin(2 * numpy.pi * 660 * numpy.arange(samples.size) / 16000)
    numpy.testing.assert_allclose(samples[32:-32], expected[32:-32], atol=0.018)


def test_downsampling_suppresses_frequencies_that_would_alias(numpy) -> None:
    pcm = (16384 * numpy.sin(2 * numpy.pi * 12000 * numpy.arange(4800) / 48000))
    samples = speech_recognition._prepare_pcm(pcm.astype("<i2").tobytes(), 48000, 1)

    assert numpy.max(numpy.abs(samples[32:-32])) < 0.002


@pytest.mark.parametrize(("pcm", "rate", "channels"), [
    (b"\x00", 16000, 1), (b"\0\0", 48000, 2),
    (b"\0\0", 0, 1), (b"\0\0", 16000, 0),
])
def test_invalid_pcm_raises_a_clear_error(numpy, pcm, rate, channels) -> None:
    with pytest.raises(ValueError, match="WASAPI-PCM"):
        speech_recognition._prepare_pcm(pcm, rate, channels)


@pytest.mark.parametrize("pcm", [b"", b"\0" * 64000, b"\0\x40\0\xc0" * 16000])
def test_silent_pcm_skips_whisper(numpy, pcm) -> None:
    result = speech_recognition._transcribe(
        None, pcm, 16000, 2, "de", 10, 12, 3,
    )
    assert result == Transcript(10, 12, pause_ms=2000, continuity=3)


def test_transcribe_passes_voice_signal_to_whisper_without_decoding(numpy, monkeypatch) -> None:
    decoder = MagicMock(
        side_effect=TypeError("open() got an unexpected keyword argument 'metadata_errors'")
    )
    monkeypatch.setitem(sys.modules, "faster_whisper.audio", SimpleNamespace(decode_audio=decoder))

    # Voiced vowel harmonics followed by a 300 ms pause in a 48 kHz stereo window.
    rate = 48000
    time = numpy.arange(2 * rate) / rate
    voiced = numpy.sin(2 * numpy.pi * 150 * time) + 0.4 * numpy.sin(2 * numpy.pi * 750 * time)
    voiced[time >= 1.7] = 0
    pcm = numpy.column_stack((voiced * 12000, voiced * 6000)).astype("<i2")
    model = MagicMock()
    model.transcribe.return_value = (iter([SimpleNamespace(words=[
        SimpleNamespace(word=" Hallo", start=0.25, end=0.75, probability=0.9),
        SimpleNamespace(word=" Rauschen", start=0.8, end=1.1, probability=0.1),
    ])]), None)

    result = speech_recognition._transcribe(
        model, pcm.tobytes(), rate, 2, "de", 10, 12, 4, beam_size=3,
        hints=RecognitionHints("Heute am Bahnhof.", "Sternenbrücke"),
    )

    model.transcribe.assert_called_once()
    args, kwargs = model.transcribe.call_args
    samples, = args
    assert isinstance(samples, numpy.ndarray)
    assert samples.dtype == numpy.float32
    assert samples.shape == (32000,)
    assert samples.flags.c_contiguous
    expected_rms = (9000 / 32768) * numpy.sqrt((1 + 0.4 ** 2) / 2 * 1.7 / 2)
    assert numpy.sqrt(numpy.mean(samples ** 2)) == pytest.approx(expected_rms, abs=0.001)
    assert kwargs["language"] == "de" and kwargs["word_timestamps"]
    assert kwargs["beam_size"] == 3
    assert kwargs["initial_prompt"] == "Heute am Bahnhof."
    assert kwargs["hotwords"] == "Sternenbrücke"
    assert kwargs["condition_on_previous_text"] is False
    assert kwargs["max_new_tokens"] == 16
    assert result == Transcript(10, 12, (Word(" Hallo", 10.25, 10.75, 0.9),), 300, 4)
    decoder.assert_not_called()


def test_model_requires_local_tokenizer_and_never_downloads(tmp_path, monkeypatch) -> None:
    calls = []
    monkeypatch.setattr(speech_recognition, "PROJECT_ROOT", tmp_path)

    def download_model(name, *, local_files_only):
        calls.append((name, local_files_only))
        return str(tmp_path)

    monkeypatch.setitem(sys.modules, "faster_whisper", SimpleNamespace(
        WhisperModel=lambda *args, **kwargs: calls.append((args, kwargs)),
        download_model=download_model,
    ))
    (tmp_path / "model.bin").touch()
    (tmp_path / "config.json").touch()
    with pytest.raises(RuntimeError, match="tokenizer.json"):
        speech_recognition._load_model("tiny")
    assert calls == [("tiny", True)]
    (tmp_path / "tokenizer.json").touch()
    speech_recognition._load_model("tiny")
    assert calls[-1] == (
        (str(tmp_path),),
        {"device": "cpu", "compute_type": "int8", "cpu_threads": 2, "local_files_only": True},
    )


@pytest.mark.parametrize("text", [
    "HEUTE TANZEN UNSERE HERZEN!",
    "Heute, tanzen unsere... Herzen.",
    "Heute tanßen unsere Herzen",
    "Heute unsere Herzen",
])
def test_matching_preserves_ids_and_tolerates_transcription_differences(text) -> None:
    matcher = LyricsMatcher("[Refrain]\n\nHeute tanzen unsere Herzen\nDie Straßen sind still", 0.75)
    hit = matcher.find(heard(text, 11).words, 0, None)
    assert hit is not None
    assert hit.line_id == 2
    assert 0.75 <= hit.score <= 1
    assert matcher.find(heard("Refrain Straßen", 11).words, 0, None) is None


def test_repeated_chorus_needs_context_and_never_rewinds() -> None:
    matcher = LyricsMatcher(
        "Der Morgen leuchtet\nWir gehen weiter\nDie Lichter sinken\n"
        "[Refrain]\nWir gehen weiter\nDer Abend kommt", 0.75,
    )
    chorus = heard("Wir gehen weiter", 11)
    assert matcher.find(chorus.words, 0, None) is None

    intro = matcher.find(heard("Der Morgen leuchtet", 10, start=8).words, 0, None)
    assert intro is not None
    first = matcher.find(chorus.words, 0, intro)
    assert first is not None and first.line_id == 1
    assert matcher.find(chorus.words, 0, first) is None

    second = matcher.find(
        heard("Die Lichter sinken Wir gehen weiter", 13, start=11).words, 0, first,
    )
    assert second is not None and second.line_id == 4
    assert matcher.find(heard("Der Morgen leuchtet", 14, start=13).words, 0, second) is None


def test_ambiguous_lines_with_similar_scores_are_held() -> None:
    matcher = LyricsMatcher("Heute tanzen alle\nHeute tanzen alle", 0.75)
    assert matcher.find(heard("Heute tanzen alle", 11).words, 0, None) is None


def test_whisper_splitting_a_word_does_not_lose_the_phrase() -> None:
    tracker = PositionTracker(LyricsMatcher("Wir erreichen heute Hamburg", 0.75), 0, 9)
    match = tracker.update(heard("Wir erreichen heute Ham burg", 12))
    assert match is not None and match.word_count == match.fresh_words == 4
    assert match.score == pytest.approx(0.9875)


def test_tracking_requires_consistent_results_and_fresh_words() -> None:
    matcher = LyricsMatcher("Die helle Brücke leuchtet\nDanach wird es dunkel", 0.75)
    tracker = PositionTracker(matcher, 0, 9)
    assert tracker.update(heard("Die Brücke leuchtet", 11)) is None
    assert tracker.pending is not None
    assert tracker.update(heard("Die helle Brücke leuchtet", 12, start=10.05)) is None
    assert tracker.current is None
    assert tracker.update(heard("Danach wird dunkel", 13, start=12.05)).line_id == 1
    assert tracker.update(heard("Die helle Brücke leuchtet", 14, start=13.1)) is None
    assert tracker.current.line_id == 1


def test_new_words_at_overlap_seam_complete_a_partial_line() -> None:
    matcher = LyricsMatcher("Wir sehen den roten Abendhimmel", 0.75)
    tracker = PositionTracker(matcher, 0, 9)
    early = heard("Wir sehen den roten", 10.8)
    assert tracker.update(early) is None
    full = heard("Wir sehen den roten Abendhimmel", 12)
    match = tracker.update(full)
    assert match is not None and match.line_id == 0 and match.fresh_words == 1


def test_long_sung_line_uses_previous_words_without_counting_the_overlap_twice() -> None:
    matcher = LyricsMatcher("Wir bleiben bis morgen an diesem Ort", 0.75)
    tracker = PositionTracker(matcher, 0, 0)
    words = tuple(
        Word(text, start, start + 0.5, 0.9)
        for text, start in zip("Wir bleiben bis morgen an diesem Ort".split(),
                               (2.2, 3.0, 4.3, 5.4, 6.4, 7.3, 8.8))
    )
    assert tracker.update(Transcript(0, 6, words[:4])) is None
    assert tracker.pending is None
    match = tracker.update(Transcript(4, 10, words[2:]))
    assert match is not None and match.line_id == 0
    assert match.word_count == 7 and match.fresh_words == 3


def test_distant_exact_phrase_needs_an_ordered_lead_in(caplog) -> None:
    content = "\n".join(
        f"Unterschiedliche rote Fahnen {i}" for i in range(6)
    ) + "\nDie Küste glänzt im Sonnenlicht\nAlle Schiffe kehren heim"
    tracker = PositionTracker(LyricsMatcher(content, 0.75), 0, 9)
    caplog.set_level("DEBUG", logger="lyricspi")
    assert tracker.update(heard("Alle Schiffe kehren heim", 11)) is None
    assert "großen Positionssprung" in caplog.text
    match = tracker.update(heard(
        "Die Küste glänzt im Sonnenlicht Alle Schiffe kehren heim", 14, start=11.1,
    ))
    assert match is not None and match.line_id == 7


def test_context_is_bounded_updated_and_opt_in() -> None:
    content = (
        "[Strophe]\nDie Brücke leuchtet\nSchon am frühen Morgen\n"
        "Bei unserer Sternenbrücke\nEin ganz neuer Abschnitt " + "bleibt " * 40
    )
    tracker = PositionTracker(LyricsMatcher(content, 0.75), 0, 9)
    assert tracker.hints(LyricsFollowingConfig()) == RecognitionHints()
    config = LyricsFollowingConfig(
        use_initial_prompt=True, hotwords="Sternenbrücke, fremdes Wort",
    )
    hints = tracker.hints(config)
    assert "[Strophe]" not in hints.initial_prompt
    assert "neuer Abschnitt" not in hints.initial_prompt
    assert hints.hotwords == "Sternenbrücke"
    tracker.update(heard("Schon am frühen Morgen", 11))
    hints = tracker.hints(config)
    assert "neuer Abschnitt" in hints.initial_prompt
    assert len(hints.initial_prompt) <= 160
    assert len(hints.initial_prompt.split()) <= 32


def test_manual_navigation_invalidates_context_of_inflight_inference() -> None:
    follower = LyricsFollower(LyricsFollowingConfig(use_initial_prompt=True))
    follower.synchronize("Wir bleiben heute wach", 0, 9)
    hints, publish = follower._recognition_context()
    assert hints.initial_prompt == "Wir bleiben heute wach"
    follower.synchronize("Der Wind bewegt die Wolken", 0, 10, manual=True)
    publish(heard("Wir bleiben heute wach", 12, start=10.1))
    assert follower.poll(0, [(0,)], 12) is None
    assert follower.line_id is None
    new_hints, _ = follower._recognition_context()
    assert new_hints.initial_prompt == "Der Wind bewegt die Wolken"


def test_pause_preference_can_be_disabled() -> None:
    follower = LyricsFollower(LyricsFollowingConfig(
        mode="auto", auto_page_turn=True, prefer_pause=False,
    ))
    follower.synchronize("Das Lied beginnt\nJetzt wird alles heller", 0, 9)
    follower._process(heard("Jetzt wird alles heller", 11))
    assert follower.poll(0, [(0,), (1,)], 11) == 1


def confirm_later_page(follower, *, pause: int = 0) -> None:
    follower._process(heard("Jetzt wird alles heller", 12, pause=pause))


@pytest.mark.parametrize(("mode", "auto", "expected"), [
    ("observe", False, None), ("observe", True, None),
    ("auto", False, None), ("auto", True, 1),
])
def test_observe_logs_and_auto_advances_a_later_page(mode, auto, expected, caplog) -> None:
    caplog.set_level("INFO", logger="lyricspi.lyrics_follower")
    follower = LyricsFollower(LyricsFollowingConfig(mode=mode, auto_page_turn=auto))
    follower.synchronize("Das Lied beginnt\nJetzt wird alles heller", 0, 9)
    confirm_later_page(follower, pause=800)
    assert follower.poll(0, [(0,), (1,)], 12) == expected
    assert follower.line_id == 1
    if expected is None:
        assert "Möglicher Seitenwechsel 1 → 2." in caplog.text


def test_no_turn_on_silence_stale_evidence_or_manual_reset() -> None:
    follower = LyricsFollower(LyricsFollowingConfig(mode="auto", auto_page_turn=True))
    content = "Das Lied beginnt\nJetzt wird alles heller"
    pages = [(0,), (1,)]
    follower.synchronize(content, 0, 9)
    confirm_later_page(follower)
    assert follower.poll(0, pages, 12) is None  # wait briefly for continuous music
    follower._process(Transcript(9, 12.25, pause_ms=900))
    assert follower.poll(0, pages, 12.5) is None
    assert follower.line_id == 1

    follower.synchronize(content, 0, 9)
    confirm_later_page(follower, pause=800)
    follower.synchronize(content, 0, 12.1, manual=True)
    assert follower.poll(0, pages, 12.1) is None
    assert follower.line_id is None
    confirm_later_page(follower)
    assert follower.poll(0, pages, 13) is None

    follower.synchronize(content, 0, 9)
    confirm_later_page(follower, pause=800)
    assert follower.poll(0, pages, 20) is None


def test_minimum_interval_and_current_page_prevent_turns() -> None:
    follower = LyricsFollower(LyricsFollowingConfig(mode="auto", auto_page_turn=True))
    content = "Das Lied beginnt\nJetzt wird alles heller"
    follower.synchronize(content, 0, 9, manual=True)
    confirm_later_page(follower, pause=800)
    assert follower.poll(0, [(0,), (1,)], 12) is None
    follower.synchronize(content, 0, 9)
    confirm_later_page(follower, pause=800)
    assert follower.poll(1, [(0,), (1,)], 14) is None


def test_confirmed_line_survives_one_inference_interval() -> None:
    follower = LyricsFollower(LyricsFollowingConfig())
    follower.synchronize("Das Lied beginnt\nJetzt wird alles heller", 0, 9)
    confirm_later_page(follower)

    assert follower.poll(0, [(0, 1)], 16.1) is None
    assert follower.line_id == 1


def test_wrapped_rows_keep_ids_across_pages() -> None:
    ids = []
    pages = paginate(
        "[Solo]\n\nabc def ghi\n", 5, 2, lambda text: (len(text), 1),
        1, 0, page_line_ids=ids,
    )
    assert pages == (("[Solo", "]"), ("", "abc "), ("def ", "ghi"))
    assert ids == [(0, 0), (1, 2), (2, 2)]


def test_renderer_marks_wrapped_line_and_retains_header_and_progress(monkeypatch) -> None:
    monkeypatch.setenv("SDL_VIDEODRIVER", "dummy")
    display = DisplayConfig(window_width=520, window_height=600, font_size=24)
    lyrics = "[Strophe 1]\nEine lange Songzeile " + "mit vielen Wörtern " * 3
    song = Song(1, "01_Demo.txt", Path(), "Ein Lied", lyrics)
    follower = LyricsFollower(LyricsFollowingConfig())
    state = app.AppState(24, True, setlist=Setlist((song,)), follower=follower)
    try:
        renderer = Renderer(display)
        app._update_layout(state, renderer)
        assert len(state.page) >= 3
        assert state.page_line_ids[0] == (0,) + (1,) * (len(state.page) - 1)
        app._draw(state, renderer, None)
        baseline = renderer.screen.copy()
        state.follower.line_id = 1
        app._draw(state, renderer, None)
        font = renderer._font_for_size(24)
        header, rail, body = renderer._song_areas(font, song)
        for bounds in (header, rail):
            assert pygame.image.tobytes(renderer.screen.subsurface(bounds), "RGB") == (
                pygame.image.tobytes(baseline.subsurface(bounds), "RGB")
            )
        top = body.top
        for row, line in enumerate(state.page):
            assert renderer.screen.get_at((body.right - 1, top)) == (
                LYRIC_HIGHLIGHT if row else pygame.Color("black")
            )
            top += max(font.get_height(), font.size(line)[1]) + renderer.line_spacing
    finally:
        pygame.quit()


def test_app_applies_manual_navigation_before_a_queued_turn(monkeypatch) -> None:
    monkeypatch.setenv("SDL_VIDEODRIVER", "dummy")
    display = DisplayConfig(window_height=160, line_spacing=150)
    song = Song(1, "01_Demo.txt", Path(), "Ein Lied",
                "Das Lied beginnt\nJetzt wird alles heller\nDie letzte Zeile")
    other = Song(2, "02_Andere.txt", Path(), "Anderes Lied", "Zweiter Song")
    follower = LyricsFollower(LyricsFollowingConfig(mode="auto", auto_page_turn=True))
    state = app.AppState(48, True, setlist=Setlist((song, other)), follower=follower)
    monkeypatch.setattr(app, "monotonic", lambda: 12)
    try:
        renderer = Renderer(display)
        app._update_layout(state, renderer)
        follower.synchronize(song.content, 0, 9)
        confirm_later_page(follower, pause=800)
        assert app._poll_follower(state)
        assert state.navigation.page_index == 1
        assert state.song is song
        assert state.text_position == (1, 0)
        app._apply_keyboard_action(Action.PREVIOUS_PAGE, state, display, renderer)
        assert not app._poll_follower(state)
        assert state.navigation.page_index == 0
        assert follower.line_id is None
        app._apply_keyboard_action(Action.NEXT_SONG, state, display, renderer)
        assert state.song is other
    finally:
        pygame.quit()


@pytest.mark.parametrize("stage", ["model", "transcription"])
def test_blocked_audio_processing_does_not_stop_rendering(monkeypatch, stage) -> None:
    monkeypatch.setenv("SDL_VIDEODRIVER", "dummy")
    monkeypatch.setattr(app, "platform", "win32")
    entered, release = Event(), Event()

    def block(*args, **kwargs):
        entered.set()
        assert release.wait(2)
        return object()

    if stage == "model":
        monkeypatch.setattr(speech_recognition, "_load_model", block)
    else:
        @contextmanager
        def synthetic_source(_device, queue, _stopping):
            now = monotonic()
            block = b"\xff\x7f" * 16000
            for second in range(6):
                queue.put_nowait(AudioBlock(block, now + second - 5, second + 1))
            yield 16000, 1, lambda: True

        monkeypatch.setattr(speech_recognition, "_load_model", lambda _: object())
        monkeypatch.setattr(speech_recognition, "windows_loopback", synthetic_source)
        monkeypatch.setattr(speech_recognition, "_transcribe", block)
    close = RecognitionWorker.close

    def close_worker(worker):
        worker.stop()
        release.set()
        close(worker)

    monkeypatch.setattr(RecognitionWorker, "close", close_worker)
    calls = []
    draw = app._draw

    def record_draw(*args, **kwargs):
        calls.append(True)
        return draw(*args, **kwargs)

    def events():
        assert entered.wait(2)
        assert not release.is_set()
        if len(calls) == 1:
            return [pygame.event.Event(pygame.WINDOWEXPOSED)]
        return [pygame.event.Event(pygame.QUIT)]

    monkeypatch.setattr(app, "_draw", record_draw)
    monkeypatch.setattr(pygame.event, "get", events)
    app.run(Config(lyrics_following=LyricsFollowingConfig(enabled=True)))
    assert len(calls) == 2


def test_runtime_shortcuts_toggle_without_loading_audio_at_start(monkeypatch, caplog) -> None:
    monkeypatch.setenv("SDL_VIDEODRIVER", "dummy")
    monkeypatch.setattr(app, "platform", "win32")
    caplog.set_level("INFO", logger="lyricspi.app")
    started = []
    stopped = []
    monkeypatch.setattr(RecognitionWorker, "start", lambda worker: started.append(worker))
    monkeypatch.setattr(RecognitionWorker, "stop", lambda worker: stopped.append(worker))
    events = iter([
        [pygame.event.Event(pygame.KEYDOWN, key=pygame.K_F9)],
        [pygame.event.Event(pygame.KEYDOWN, key=pygame.K_F8)],
        [pygame.event.Event(pygame.KEYDOWN, key=pygame.K_F9)],
        [pygame.event.Event(pygame.KEYDOWN, key=pygame.K_F9)],
        [pygame.event.Event(pygame.KEYDOWN, key=pygame.K_F8)],
        [pygame.event.Event(pygame.QUIT)],
    ])
    monkeypatch.setattr(pygame.event, "get", lambda: next(events))

    app.run(Config())

    assert len(started) == 1
    assert stopped[0] is started[0]
    assert [message for message in caplog.messages if message.startswith("Textverfolgung")] == [
        "Textverfolgung aktiv (observe).",
        "Textverfolgung: auto.",
        "Textverfolgung: observe.",
        "Textverfolgung deaktiviert.",
    ]


@pytest.mark.parametrize(("platform", "enabled"), [("win32", False), ("linux", True)])
def test_disabled_or_nonwindows_run_never_imports_feature(monkeypatch, platform, enabled) -> None:
    monkeypatch.setattr(app, "platform", platform)
    monkeypatch.setenv("SDL_VIDEODRIVER", "dummy")
    monkeypatch.setitem(sys.modules, "lyricspi.lyrics_follower", None)
    monkeypatch.setitem(sys.modules, "pyaudiowpatch", None)
    monkeypatch.setitem(sys.modules, "faster_whisper", None)
    monkeypatch.setattr(pygame.event, "get", lambda: [pygame.event.Event(pygame.QUIT)])
    app.run(Config(lyrics_following=LyricsFollowingConfig(enabled=enabled)))


@pytest.mark.parametrize(("key", "value"), [
    ("mode", "manual"), ("audio_source", "microphone"), ("audio_device", ""),
    ("language", "fr"), ("model", ""), ("confidence_threshold", True),
    ("confidence_threshold", 1.1), ("pause_duration_ms", 0), ("min_turn_interval_ms", -1),
    ("beam_size", 0), ("window_seconds", 0), ("overlap_seconds", 6),
    ("use_initial_prompt", "yes"), ("hotwords", ["Sternenbrücke"]),
])
def test_invalid_lyrics_following_config(tmp_path, key, value) -> None:
    path = tmp_path / "config.json"
    path.write_text(json.dumps({"lyrics_following": {key: value}}), encoding="utf-8")
    with pytest.raises(ConfigError, match=rf"lyrics_following\.{key}"):
        load_config(path)


def test_lf4_defaults_keep_observe_and_enable_no_recognition_hints() -> None:
    config = LyricsFollowingConfig()
    assert (config.model, config.mode, config.beam_size) == ("small", "observe", 5)
    assert (config.window_seconds, config.overlap_seconds) == (6, 2)
    assert not config.use_initial_prompt and not config.hotwords


def test_benchmark_replays_a_local_wav_with_window_padding(tmp_path) -> None:
    path = tmp_path / "short.wav"
    with wave.open(str(path), "wb") as audio:
        audio.setparams((1, 2, 10, 0, "NONE", ""))
        audio.writeframes(b"\xff\xff" * 80)
    with wave.open(str(path), "rb") as audio:
        windows = list(audio_windows(audio, LyricsFollowingConfig()))

    assert windows == [
        AudioWindow(0, 6, b"\xff\xff" * 60),
        AudioWindow(4, 10, b"\xff\xff" * 40 + b"\0\0" * 20),
    ]


def test_benchmark_scores_source_line_occurrences_and_delay(tmp_path) -> None:
    path = tmp_path / "cues.json"
    path.write_text(
        '[{"line": 1, "start": 0, "end": 2}, {"line": 3, "start": 4, "end": 6}]',
        encoding="utf-8",
    )
    cues = load_cues(path, "Wir gehen weiter\n[Refrain]\nWir gehen weiter", 6.0)
    assert cues == (Cue(0, 0, 2), Cue(2, 4, 6))
    matches = [
        (Match(0, 0, 1, 0.4, 1.2, 3, 3), 2.5),
        (Match(1, 2, 1, 1.3, 1.9, 3, 3), 3),
    ]
    assert score(matches, cues) == (1, 1, 2.5)
