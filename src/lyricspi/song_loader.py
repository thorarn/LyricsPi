"""Resolve the configured source and read its song files once."""

import ctypes
import logging
import re
import stat
import sys
from ctypes import wintypes
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from string import ascii_uppercase

from .config import SongsConfig
from .setlist import Setlist, Song


LOGGER = logging.getLogger(__name__)
SONG_STEM = re.compile(r"([0-9]+)_(.+)", re.DOTALL)
DRIVE_REMOVABLE = 2
ERROR_NOT_READY = 21


class SongLoadIssue(Enum):
    USB_MISSING = "USB-Stick einstecken."
    USB_AMBIGUOUS = (
        "Mehrere Wechseldatenträger erkannt. Nur einen anschließen."
    )
    DIRECTORY_MISSING = "Songordner fehlt. Bitte Konfiguration prüfen."
    SOURCE_UNREADABLE = "Songquelle kann nicht gelesen werden."
    NO_SONGS = "Keine gültigen Songtexte gefunden."


@dataclass(frozen=True)
class SongLoadResult:
    setlist: Setlist = Setlist()
    issue: SongLoadIssue | None = None


def _windows_removable_roots() -> list[Path]:
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    drive_mask = kernel.GetLogicalDrives
    drive_mask.argtypes = []
    drive_mask.restype = wintypes.DWORD
    drive_type = kernel.GetDriveTypeW
    drive_type.argtypes = [wintypes.LPCWSTR]
    drive_type.restype = wintypes.UINT

    mask = drive_mask()
    if not mask:
        raise ctypes.WinError(ctypes.get_last_error())

    roots = []
    for index, letter in enumerate(ascii_uppercase):
        if not mask & (1 << index):
            continue
        root = f"{letter}:\\"
        if drive_type(root) != DRIVE_REMOVABLE:
            continue
        path = Path(root)
        try:
            path.stat()
        except FileNotFoundError:
            continue
        except OSError as error:
            if getattr(error, "winerror", None) == ERROR_NOT_READY:
                continue
            LOGGER.warning("Wechseldatenträger %s nicht lesbar: %s", path, error)
        roots.append(path)
    return roots


def _usb_roots(config: SongsConfig) -> list[Path]:
    if sys.platform == "win32":
        return _windows_removable_roots()
    if sys.platform.startswith("linux"):
        mount = config.mount_path
        if mount is not None and mount.is_mount():
            return [mount]
    return []


def load_setlist(config: SongsConfig) -> SongLoadResult:
    """Select the source without choosing between multiple removable drives."""
    if config.source_mode == "directory":
        directory = config.directory_path
    else:
        try:
            roots = _usb_roots(config)
        except OSError as error:
            LOGGER.warning("USB-Erkennung fehlgeschlagen: %s", error)
            return SongLoadResult(issue=SongLoadIssue.SOURCE_UNREADABLE)
        if not roots:
            LOGGER.warning("Kein nutzbarer Wechseldatenträger erkannt.")
            return SongLoadResult(issue=SongLoadIssue.USB_MISSING)
        if len(roots) > 1:
            LOGGER.warning("Mehrere Wechseldatenträger erkannt: %s", roots)
            return SongLoadResult(issue=SongLoadIssue.USB_AMBIGUOUS)
        directory = roots[0]
    LOGGER.info("Songquelle (%s): %s", config.source_mode, directory)
    return load_songs(directory, config)


def load_songs(
    directory: Path, config: SongsConfig = SongsConfig()
) -> SongLoadResult:
    """Read regular TXT files in numeric order and preserve line endings."""
    try:
        files = list(directory.iterdir())
    except (FileNotFoundError, NotADirectoryError):
        LOGGER.warning("Songordner fehlt: %s", directory)
        return SongLoadResult(issue=SongLoadIssue.DIRECTORY_MISSING)
    except OSError as error:
        LOGGER.warning("Songordner %s nicht lesbar: %s", directory, error)
        return SongLoadResult(issue=SongLoadIssue.SOURCE_UNREADABLE)

    candidates = []
    has_text_files = False
    for path in files:
        if path.suffix.lower() != config.extension:
            continue
        try:
            if not stat.S_ISREG(path.lstat().st_mode):
                continue
        except OSError as error:
            LOGGER.warning("Datei %s nicht zugänglich: %s", path, error)
            continue
        has_text_files = True
        match = SONG_STEM.fullmatch(path.stem)
        if match is None or not match[2].strip():
            LOGGER.warning("Ungültiger Songdateiname: %s", path.name)
            continue
        candidates.append((int(match[1]), path.name, path, match[2]))

    songs = []
    for number, filename, path, title in sorted(candidates):
        try:
            with path.open(encoding=config.encoding, newline="") as file:
                content = file.read()
        except UnicodeDecodeError:
            LOGGER.warning("Songdatei %s enthält ungültiges UTF-8.", path)
            continue
        except OSError as error:
            LOGGER.warning("Songdatei %s nicht lesbar: %s", path, error)
            continue
        if not content.strip():
            LOGGER.warning("Leere Songdatei übersprungen: %s", path)
            continue
        songs.append(Song(number, filename, path, title, content))

    if songs:
        return SongLoadResult(setlist=Setlist(tuple(songs)))
    if not has_text_files:
        LOGGER.warning("Keine TXT-Dateien in %s gefunden.", directory)
    else:
        LOGGER.warning("Keine gültigen Songtexte in %s gefunden.", directory)
    return SongLoadResult(issue=SongLoadIssue.NO_SONGS)
