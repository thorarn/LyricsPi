import json
from pathlib import Path

import pytest

from lyricspi.config import (
    DEFAULT_CONFIG_PATH,
    PROJECT_ROOT,
    Config,
    ConfigError,
    SongsConfig,
    load_config,
)


def test_missing_local_file_uses_defaults(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)

    config = load_config()

    assert config.display.window_width == 1280
    assert config.display.font_size == 48
    assert not config.display.fullscreen
    assert config.system.development_mode
    assert not DEFAULT_CONFIG_PATH.exists()


def test_existing_local_file_overrides_defaults(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    DEFAULT_CONFIG_PATH.parent.mkdir()
    DEFAULT_CONFIG_PATH.write_text(
        json.dumps(
            {
                "display": {
                    "fullscreen": True,
                    "font_size": 36,
                    "background": "#101010",
                },
                "system": {"allow_keyboard": False},
            }
        ),
        encoding="utf-8",
    )

    config = load_config()

    assert config.display.fullscreen
    assert config.display.font_size == 36
    assert config.display.background == "#101010"
    assert config.display.window_width == Config().display.window_width
    assert not config.system.allow_keyboard


def test_example_file_matches_defaults() -> None:
    root = Path(__file__).resolve().parents[1]
    assert load_config(root / "config" / "config.example.json") == Config()


def test_invalid_json_reports_location(tmp_path: Path) -> None:
    path = tmp_path / "invalid.json"
    path.write_text('{"display": }', encoding="utf-8")
    with pytest.raises(ConfigError, match="Ungültiges JSON.*Zeile 1"):
        load_config(path)


def test_explicit_missing_file_reports_path(tmp_path: Path) -> None:
    with pytest.raises(ConfigError, match=r"fehlt: .*missing\.json"):
        load_config(tmp_path / "missing.json")


@pytest.mark.parametrize(
    ("section", "key", "value"),
    [
        ("display", "font_size", 0),
        ("display", "font_size", 97),
        ("display", "font_size", True),
        ("display", "font_max", 20),
        ("display", "font_step", 0),
        ("display", "foreground", "#XYZ123"),
        ("display", "background", "white"),
        ("display", "window_width", 0),
        ("display", "margin_percent", 50),
        ("display", "line_spacing", -1),
        ("display", "line_spacing", True),
        ("display", "fullscreen", "false"),
        ("system", "show_splash", 1),
        ("system", "unknown", True),
    ],
)
def test_invalid_settings_are_rejected(
    tmp_path: Path, section: str, key: str, value: object
) -> None:
    path = tmp_path / "invalid.json"
    path.write_text(json.dumps({section: {key: value}}), encoding="utf-8")

    with pytest.raises(ConfigError, match=rf"{section}\.{key}"):
        load_config(path)


def test_m1_config_uses_song_defaults(tmp_path: Path) -> None:
    path = tmp_path / "legacy.json"
    path.write_text('{"display": {"font_size": 52}}', encoding="utf-8")

    songs = load_config(path).songs

    assert songs == SongsConfig()
    assert songs.directory_path == PROJECT_ROOT / "demo_songs"
    assert songs.mount_path is None


def test_song_paths_are_relative_to_project_root(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    path = tmp_path / "config.json"
    path.write_text(
        '{"songs": {"source_mode": "usb", "directory": "lyrics", '
        '"linux_mount_path": "mount/USB"}}',
        encoding="utf-8",
    )

    songs = load_config(path).songs

    assert songs.source_mode == "usb"
    assert songs.directory_path == PROJECT_ROOT / "lyrics"
    assert songs.mount_path == PROJECT_ROOT / "mount" / "USB"


@pytest.mark.parametrize(
    ("key", "value"),
    [
        ("source_mode", "auto"),
        ("extension", ".md"),
        ("encoding", "latin-1"),
        ("sort_mode", "alphabetic"),
        ("recursive", True),
        ("recursive", "false"),
        ("directory", "  "),
        ("linux_mount_path", "mount\x00USB"),
    ],
)
def test_invalid_song_config_is_rejected(
    tmp_path: Path, key: str, value: object
) -> None:
    path = tmp_path / "invalid.json"
    path.write_text(json.dumps({"songs": {key: value}}), encoding="utf-8")

    with pytest.raises(ConfigError, match=rf"songs\.{key}"):
        load_config(path)


@pytest.mark.parametrize("spacing", [0, 12])
def test_configures_line_spacing(tmp_path: Path, spacing: int) -> None:
    path = tmp_path / "display.json"
    path.write_text(
        json.dumps({"display": {"line_spacing": spacing}}), encoding="utf-8"
    )
    assert load_config(path).display.line_spacing == spacing
