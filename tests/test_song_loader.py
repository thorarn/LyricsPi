import logging
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from lyricspi import song_loader
from lyricspi.config import SongsConfig
from lyricspi.setlist import Setlist, Song
from lyricspi.song_loader import SongLoadIssue, load_setlist, load_songs


def test_preserves_utf8_bom_whitespace_and_line_endings(tmp_path: Path) -> None:
    content = "  Grüße\r\n\r\n    Über den See  \nLetzte Zeile\r"
    path = tmp_path / "002_Am_See.TXT"
    path.write_bytes(content.encode("utf-8-sig"))
    unmarked = tmp_path / "3_Lied.txt"
    unmarked.write_bytes("Für dich".encode("utf-8"))

    result = load_songs(tmp_path)

    assert result.issue is None
    assert result.setlist[0] == Song(2, path.name, path, "Am_See", content)
    assert result.setlist[1].content == "Für dich"


def test_loads_ten_songs_in_numeric_order(tmp_path: Path) -> None:
    expected = [
        "001_Anfang.txt",
        "02_Wiese.txt",
        "2_Abend.txt",
        "2_Morgen.txt",
        "3_Wasser.txt",
        "09_Regen.txt",
        "10_Sonne.txt",
        "12_Wind.txt",
        "125_Strand.txt",
        "123456789012345678901234567890_Licht.txt",
    ]
    for name in reversed(expected):
        (tmp_path / name).write_text("Lied", encoding="utf-8")

    songs = load_songs(tmp_path).setlist

    assert len(songs) == 10
    assert [song.filename for song in songs] == expected
    assert songs.first is songs[0]
    assert songs.last is songs[9]


def test_empty_setlist() -> None:
    songs = Setlist()
    assert len(songs) == 0
    assert songs.first is None
    assert songs.last is None
    with pytest.raises(IndexError):
        songs[0]


def test_load_skips_invalid_files_and_subdirectories(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    bad_names = (
        "Song.txt", "A1_Song.txt", "01-Song.txt", "01_.txt", "_Song.txt",
        "07_   .txt",
    )
    for name in bad_names:
        (tmp_path / name).write_text("Inhalt", encoding="utf-8")
    (tmp_path / "2_Leer.txt").touch()
    (tmp_path / "3_Nur_Leerraum.txt").write_bytes(b"  \r\n\t")
    (tmp_path / "4_Ungueltig.txt").write_bytes(b"\xff")
    (tmp_path / "5_Cover.jpg").write_bytes(b"image")
    subdirectory = tmp_path / "6_Ordner.txt"
    subdirectory.mkdir()
    (subdirectory / "1_Verschachtelt.txt").write_text("Lied", encoding="utf-8")
    (tmp_path / "8_Gueltig.txt").write_text("Lied", encoding="utf-8")

    result = load_songs(tmp_path)

    assert result.issue is None
    assert [song.filename for song in result.setlist] == ["8_Gueltig.txt"]
    assert {f"Ungültiger Songdateiname: {name}" for name in bad_names} <= {
        record.getMessage() for record in caplog.records
    }
    assert "ungültiges UTF-8" in caplog.text
    assert caplog.text.count("Leere Songdatei") == 2


def test_read_error_on_one_file_preserves_other_songs(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    inaccessible = tmp_path / "1_Fehler.txt"
    inaccessible.touch()
    (tmp_path / "2_Lied.txt").write_text("Lied", encoding="utf-8")
    open_file = Path.open

    def denied_for_first_file(path: Path, *args, **kwargs):
        if path == inaccessible:
            raise OSError("Datenträgerfehler")
        return open_file(path, *args, **kwargs)

    monkeypatch.setattr(Path, "open", denied_for_first_file)

    result = load_songs(tmp_path)

    assert len(result.setlist) == 1
    assert "Datenträgerfehler" in caplog.text


def test_reports_missing_directory(tmp_path: Path) -> None:
    result = load_songs(tmp_path / "missing")
    assert result.issue is SongLoadIssue.DIRECTORY_MISSING
    assert not result.setlist


def test_reports_unreadable_directory(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def denied(path: Path) -> None:
        raise PermissionError(path)

    monkeypatch.setattr(Path, "iterdir", denied)

    result = load_songs(tmp_path)
    assert result.issue is SongLoadIssue.SOURCE_UNREADABLE
    assert not result.setlist


@pytest.mark.parametrize(
    ("name", "log"),
    [
        ("Cover.jpg", "Keine TXT-Dateien"),
        ("01_Leer.txt", "Keine gültigen Songtexte"),
    ],
)
def test_reports_no_valid_songs(
    tmp_path: Path, caplog: pytest.LogCaptureFixture, name: str, log: str
) -> None:
    (tmp_path / name).touch()
    with caplog.at_level(logging.WARNING):
        result = load_songs(tmp_path)
    assert result.issue is SongLoadIssue.NO_SONGS
    assert not result.setlist
    assert log in caplog.text


def test_local_directory_and_usb_use_the_same_loader(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    (tmp_path / "1_Lied.txt").write_text("Das Lied", encoding="utf-8")
    monkeypatch.setattr(song_loader, "sys", SimpleNamespace(platform="win32"))
    monkeypatch.setattr(song_loader, "_windows_removable_roots", lambda: [tmp_path])
    directory = load_setlist(SongsConfig(directory=str(tmp_path)))
    usb = load_setlist(SongsConfig(source_mode="usb"))
    assert usb == directory
    assert len(usb.setlist) == 1


@pytest.mark.parametrize(
    ("candidates", "issue"),
    [
        ([], SongLoadIssue.USB_MISSING),
        (["E:\\", "F:\\"], SongLoadIssue.USB_AMBIGUOUS),
    ],
)
def test_does_not_load_without_one_usb_candidate(
    monkeypatch: pytest.MonkeyPatch, candidates: list[str], issue: SongLoadIssue
) -> None:
    monkeypatch.setattr(song_loader, "sys", SimpleNamespace(platform="win32"))
    monkeypatch.setattr(
        song_loader, "_windows_removable_roots", lambda: list(map(Path, candidates))
    )
    read = Mock()
    monkeypatch.setattr(song_loader, "load_songs", read)

    assert load_setlist(SongsConfig(source_mode="usb")).issue is issue
    read.assert_not_called()


def test_windows_filters_fixed_network_and_empty_drives(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    drives = {"C:\\": 3, "E:\\": 2, "F:\\": 2, "G:\\": 4, "H:\\": 5}
    kernel = Mock()
    kernel.GetLogicalDrives.return_value = sum(
        1 << (ord(root[0]) - ord("A")) for root in drives
    )
    kernel.GetDriveTypeW.side_effect = drives.__getitem__
    monkeypatch.setattr(
        song_loader.ctypes, "WinDLL", lambda *args, **kwargs: kernel, raising=False
    )

    stat_path = Path.stat

    def probe(path: Path, *, follow_symlinks: bool = True):
        if path == Path("F:\\"):
            error = OSError("Nicht bereit")
            error.winerror = 21
            raise error
        if path != Path("E:\\"):
            return stat_path(path, follow_symlinks=follow_symlinks)

    monkeypatch.setattr(Path, "stat", probe)

    assert song_loader._windows_removable_roots() == [Path("E:\\")]


@pytest.mark.parametrize("mounted", [True, False])
def test_linux_uses_only_mounted_configured_path(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, mounted: bool
) -> None:
    monkeypatch.setattr(song_loader, "sys", SimpleNamespace(platform="linux"))
    monkeypatch.setattr(Path, "is_mount", lambda path: path == tmp_path and mounted)
    (tmp_path / "1_Lied.txt").write_text("Das Lied", encoding="utf-8")

    result = load_setlist(SongsConfig(source_mode="usb", linux_mount_path=str(tmp_path)))

    if mounted:
        assert result.issue is None
        assert len(result.setlist) == 1
    else:
        assert result.issue is SongLoadIssue.USB_MISSING
