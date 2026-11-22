import json
from pathlib import Path, PurePosixPath

import pytest

from lyricspi import config as config_module
from lyricspi.config import (
    DEFAULT_CONFIG_PATH,
    PROJECT_ROOT,
    Config,
    ConfigError,
    DisplayConfig,
    DisplaySettings,
    InputConfig,
    SongsConfig,
    display_settings_path,
    load_config,
    load_display_settings,
    save_display_settings,
)


def test_missing_local_file_uses_defaults(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)

    config = load_config()

    assert config.display.window_width == 1280
    assert config.display.font_size == 32
    assert not config.display.fullscreen
    assert config.system.development_mode
    assert not DEFAULT_CONFIG_PATH.exists()


def test_missing_display_settings_use_32_px_and_zero_degrees(tmp_path: Path) -> None:
    path = tmp_path / "settings.json"
    assert load_display_settings(path, DisplayConfig()) == DisplaySettings(32, 0)
    assert not path.exists()


@pytest.mark.parametrize(("raw", "expected"), [
    ('{"font_size": 33, "rotation": 45}', DisplaySettings(32, 0)),
    ('{"font_size": true, "rotation": 90}', DisplaySettings(32, 90)),
    ('{"font_size": 40, "rotation": "90"}', DisplaySettings(40, 0)),
    ('{"font_size": 36, "rotation": 180.0}', DisplaySettings(36, 0)),
    ('{"rotation": 270}', DisplaySettings(32, 270)),
    ('{"font_size": 33, "legacy_font_size": 52, "rotation": 0}', DisplaySettings()),
    ('{"font_size":', DisplaySettings()),
    ('[]', DisplaySettings()),
])
def test_invalid_display_settings_fall_back_per_field(tmp_path, raw, expected) -> None:
    path = tmp_path / "settings.json"
    path.write_text(raw, encoding="utf-8")
    assert load_display_settings(path, DisplayConfig(font_size=48)) == expected


def test_migration_adopts_existing_display_values_and_update_keeps_saved_settings(
    tmp_path: Path,
) -> None:
    path = tmp_path / "state" / "settings.json"
    config_path = tmp_path / "config.json"
    config_path.write_text('{"display": {"font_size": 52, "rotation": 270}}')
    legacy = load_config(config_path).display

    assert load_display_settings(path, legacy) == DisplaySettings(52, 270)
    assert json.loads(path.read_text(encoding="utf-8")) == {
        "font_size": 52, "rotation": 270, "legacy_font_size": 52,
    }
    assert load_display_settings(path, legacy) == DisplaySettings(52, 270)
    assert load_display_settings(path, DisplayConfig()) == DisplaySettings(52, 270)

    save_display_settings(path, DisplaySettings(36, 90))
    saved = path.read_bytes()
    assert load_display_settings(path, DisplayConfig()) == DisplaySettings(36, 90)
    assert load_display_settings(path, legacy) == DisplaySettings(36, 90)
    assert path.read_bytes() == saved


def test_failed_atomic_replace_keeps_previous_document(tmp_path, monkeypatch, caplog) -> None:
    path = tmp_path / "settings.json"
    save_display_settings(path, DisplaySettings(40, 90))

    def fail_replace(temporary: Path, target: Path) -> None:
        assert temporary.parent == target.parent
        assert json.loads(temporary.read_text(encoding="utf-8")) == {
            "font_size": 44, "rotation": 180,
        }
        raise PermissionError("replace failed")

    monkeypatch.setattr(Path, "replace", fail_replace)
    save_display_settings(path, DisplaySettings(44, 180))
    assert load_display_settings(path, DisplayConfig()) == DisplaySettings(40, 90)
    assert list(tmp_path.iterdir()) == [path]
    assert "replace failed" in caplog.text


@pytest.mark.parametrize(("platform", "variable", "parts"), [
    ("win32", "LOCALAPPDATA", ("LyricsPi", "settings.json")),
    ("linux", "STATE_DIRECTORY", ("settings.json",)),
    ("linux", "XDG_STATE_HOME", ("lyricspi", "settings.json")),
])
def test_settings_path_respects_platform_state_directory(
    tmp_path, monkeypatch, platform, variable, parts,
) -> None:
    monkeypatch.setattr(config_module, "platform", platform)
    monkeypatch.delenv("STATE_DIRECTORY", raising=False)
    monkeypatch.setenv(variable, str(tmp_path))
    assert display_settings_path() == tmp_path.joinpath(*parts)


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
        ("system", "splash_duration_ms", 0),
        ("system", "splash_duration_ms", True),
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


def test_existing_config_uses_hid_defaults(tmp_path: Path) -> None:
    path = tmp_path / "existing.json"
    path.write_text('{"display": {"font_size": 52}}', encoding="utf-8")

    assert load_config(path).input == InputConfig("down", 15000)


@pytest.mark.parametrize(
    ("key", "value"),
    [
        ("shutdown_key", "left"),
        ("shutdown_key", 2),
        ("shutdown_hold_ms", 14999),
        ("shutdown_hold_ms", True),
    ],
)
def test_invalid_hid_config_is_rejected(
    tmp_path: Path, key: str, value: object
) -> None:
    path = tmp_path / "input.json"
    path.write_text(json.dumps({"input": {key: value}}), encoding="utf-8")

    with pytest.raises(ConfigError, match=rf"input\.{key}"):
        load_config(path)


def test_configures_longer_shutdown_hold(tmp_path: Path) -> None:
    path = tmp_path / "input.json"
    path.write_text(
        '{"input": {"shutdown_key": "down", "shutdown_hold_ms": 18000}}',
        encoding="utf-8",
    )
    assert load_config(path).input == InputConfig("down", 18000)


def test_absolute_linux_mount_path_ignores_checkout_root(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = tmp_path / "config.json"
    path.write_text(
        '{"songs": {"source_mode": "usb", "linux_mount_path": "/media/lyricspi/USB"}}',
        encoding="utf-8",
    )
    monkeypatch.setattr(config_module, "PROJECT_ROOT", PurePosixPath("/opt/lyricspi"))
    monkeypatch.setattr(config_module, "Path", PurePosixPath)

    assert load_config(path).songs.mount_path == PurePosixPath("/media/lyricspi/USB")
