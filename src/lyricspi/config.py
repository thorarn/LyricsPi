"""Load and validate the local JSON configuration."""

import json
import re
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import TypeVar


DEFAULT_CONFIG_PATH = Path("config") / "config.json"
PROJECT_ROOT = Path(__file__).resolve().parents[2]


class ConfigError(ValueError):
    """The configuration could not be read or contains invalid settings."""


@dataclass(frozen=True)
class DisplayConfig:
    fullscreen: bool = False
    window_width: int = 1280
    window_height: int = 720
    font_size: int = 48
    font_min: int = 24
    font_max: int = 96
    font_step: int = 4
    foreground: str = "#FFFFFF"
    background: str = "#000000"
    margin_percent: int = 5
    line_spacing: int = 4


@dataclass(frozen=True)
class SystemConfig:
    development_mode: bool = True
    allow_keyboard: bool = True
    show_splash: bool = False
    splash_duration_ms: int = 1500


@dataclass(frozen=True)
class SongsConfig:
    source_mode: str = "directory"
    directory: str = "demo_songs"
    linux_mount_path: str = ""
    encoding: str = "utf-8-sig"
    extension: str = ".txt"
    sort_mode: str = "numeric_prefix"
    recursive: bool = False

    @property
    def directory_path(self) -> Path:
        return PROJECT_ROOT / self.directory

    @property
    def mount_path(self) -> Path | None:
        if not self.linux_mount_path:
            return None
        return PROJECT_ROOT / self.linux_mount_path


@dataclass(frozen=True)
class InputConfig:
    shutdown_key: str = "down"
    shutdown_hold_ms: int = 15000

    def __post_init__(self) -> None:
        if self.shutdown_key != "down":
            raise ConfigError("input.shutdown_key muss down sein.")
        if self.shutdown_hold_ms < 15000:
            raise ConfigError("input.shutdown_hold_ms muss mindestens 15000 sein.")


@dataclass(frozen=True)
class LyricsFollowingConfig:
    enabled: bool = False
    mode: str = "observe"
    audio_source: str = "windows_loopback"
    audio_device: str = "default"
    language: str = "de"
    model: str = "small"
    beam_size: int = 5
    window_seconds: int = 6
    overlap_seconds: int = 2
    use_initial_prompt: bool = False
    hotwords: str = ""
    confidence_threshold: float = 0.75
    pause_duration_ms: int = 800
    prefer_pause: bool = True
    min_turn_interval_ms: int = 5000
    highlight_current_line: bool = True
    auto_page_turn: bool = False

    def __post_init__(self) -> None:
        choices = {
            "mode": ("observe", "auto"),
            "audio_source": ("windows_loopback",),
            "language": ("de", "en"),
        }
        for key, allowed in choices.items():
            if getattr(self, key) not in allowed:
                raise ConfigError(
                    f"lyrics_following.{key} muss einen dieser Werte haben "
                    f"({', '.join(allowed)})."
                )
        for key in ("audio_device", "model"):
            value = getattr(self, key)
            if not value.strip() or "\x00" in value:
                raise ConfigError(
                    f"lyrics_following.{key} benötigt einen gültigen Namen."
                )
        if not 0 < self.confidence_threshold <= 1:
            raise ConfigError(
                "lyrics_following.confidence_threshold muss in (0, 1] liegen."
            )
        for key in ("beam_size", "pause_duration_ms", "min_turn_interval_ms"):
            if getattr(self, key) < 1:
                raise ConfigError(f"lyrics_following.{key} muss größer als 0 sein.")
        if not 2 <= self.window_seconds <= 15:
            raise ConfigError("lyrics_following.window_seconds muss zwischen 2 und 15 liegen.")
        if not 0 <= self.overlap_seconds < self.window_seconds:
            raise ConfigError(
                "lyrics_following.overlap_seconds muss kleiner als das Fenster "
                "und mindestens 0 sein."
            )


@dataclass(frozen=True)
class Config:
    display: DisplayConfig = DisplayConfig()
    system: SystemConfig = SystemConfig()
    songs: SongsConfig = SongsConfig()
    input: InputConfig = InputConfig()
    lyrics_following: LyricsFollowingConfig = LyricsFollowingConfig()


Section = TypeVar(
    "Section", DisplayConfig, SystemConfig, SongsConfig, InputConfig,
    LyricsFollowingConfig,
)


def _load_section(name: str, values: object, defaults: Section) -> Section:
    if not isinstance(values, dict):
        raise ConfigError(f"{name} muss ein JSON-Objekt sein.")

    settings = asdict(defaults)
    type_names = {
        bool: "ein Wahrheitswert", int: "eine Ganzzahl", str: "Text",
        float: "eine Zahl",
    }
    for key, value in values.items():
        if key not in settings:
            raise ConfigError(f"Unbekannte Einstellung {name}.{key}.")
        expected_type = type(settings[key])
        allowed_types = (int, float) if expected_type is float else (expected_type,)
        if type(value) not in allowed_types:
            raise ConfigError(
                f"{name}.{key} muss {type_names[expected_type]} sein."
            )
        settings[key] = value
    return type(defaults)(**settings)


def _validate_display(display: DisplayConfig) -> None:
    for key in ("window_width", "window_height", "font_min", "font_step"):
        if getattr(display, key) < 1:
            raise ConfigError(f"display.{key} muss größer als 0 sein.")
    if display.font_max < display.font_min:
        raise ConfigError("display.font_max muss mindestens font_min sein.")
    if not display.font_min <= display.font_size <= display.font_max:
        raise ConfigError(
            "display.font_size muss zwischen font_min und font_max liegen."
        )
    for key in ("foreground", "background"):
        if re.fullmatch(r"#[0-9a-fA-F]{6}", getattr(display, key)) is None:
            raise ConfigError(f"display.{key} muss das Format #RRGGBB haben.")
    if not 0 <= display.margin_percent < 50:
        raise ConfigError("display.margin_percent muss zwischen 0 und 49 sein.")
    if display.line_spacing < 0:
        raise ConfigError("display.line_spacing darf nicht negativ sein.")


def _validate_songs(songs: SongsConfig) -> None:
    if songs.source_mode not in ("directory", "usb"):
        raise ConfigError("songs.source_mode muss directory oder usb sein.")
    if not songs.directory.strip():
        raise ConfigError("songs.directory darf nicht leer sein.")
    for key in ("directory", "linux_mount_path"):
        value = getattr(songs, key)
        path = Path(value)
        if value and (
            not value.strip()
            or "\x00" in value
            or (path.anchor and not path.is_absolute())
        ):
            raise ConfigError(
                f"songs.{key} muss ein gültiger Verzeichnispfad sein."
            )
    if songs.encoding != "utf-8-sig":
        raise ConfigError("songs.encoding muss utf-8-sig sein.")
    if songs.extension != ".txt":
        raise ConfigError("songs.extension muss .txt sein.")
    if songs.sort_mode != "numeric_prefix":
        raise ConfigError("songs.sort_mode muss numeric_prefix sein.")
    if songs.recursive:
        raise ConfigError("songs.recursive muss false sein.")


def load_config(path: Path | None = None) -> Config:
    """Use defaults for a missing local file or missing individual settings."""
    config_path = DEFAULT_CONFIG_PATH if path is None else path
    try:
        data = json.loads(config_path.read_text(encoding="utf-8-sig"))
    except FileNotFoundError as error:
        if path is None:
            return Config()
        raise ConfigError(
            f"Konfigurationsdatei fehlt: {config_path}"
        ) from error
    except json.JSONDecodeError as error:
        raise ConfigError(
            f"Ungültiges JSON in {config_path} (Zeile {error.lineno}, "
            f"Spalte {error.colno})."
        ) from error
    except UnicodeDecodeError as error:
        raise ConfigError(f"{config_path} muss UTF-8-kodiert sein.") from error
    except OSError as error:
        raise ConfigError(
            f"Konfiguration {config_path} nicht lesbar: {error}"
        ) from error

    if not isinstance(data, dict):
        raise ConfigError("Die Konfiguration muss ein JSON-Objekt sein.")
    for section in data:
        if section not in ("display", "system", "songs", "input", "lyrics_following"):
            raise ConfigError(f"Unbekannter Abschnitt {section}.")

    display = _load_section(
        "display", data.get("display", {}), DisplayConfig()
    )
    system = _load_section("system", data.get("system", {}), SystemConfig())
    songs = _load_section("songs", data.get("songs", {}), SongsConfig())
    keyboard = _load_section("input", data.get("input", {}), InputConfig())
    following = _load_section(
        "lyrics_following", data.get("lyrics_following", {}), LyricsFollowingConfig()
    )
    _validate_display(display)
    _validate_songs(songs)
    if system.splash_duration_ms < 1:
        raise ConfigError("system.splash_duration_ms muss größer als 0 sein.")
    return Config(
        display=display, system=system, songs=songs, input=keyboard,
        lyrics_following=following,
    )
