from collections.abc import Iterator
from pathlib import Path
from unittest.mock import Mock, call, patch

import pygame
import pytest

from lyricspi.app import run
from lyricspi.config import Config, DisplayConfig, SongsConfig
from lyricspi.layout import Page
from lyricspi.renderer import Renderer, TRACK_COLOR, progress_position
from lyricspi.setlist import Setlist, Song
from lyricspi.song_loader import load_songs


@pytest.fixture
def renderer(monkeypatch: pytest.MonkeyPatch) -> Iterator[Renderer]:
    monkeypatch.setenv("SDL_VIDEODRIVER", "dummy")
    try:
        yield Renderer(DisplayConfig())
    finally:
        pygame.quit()


@pytest.mark.parametrize("selected", [0, 5000, 9999])
def test_song_list_draws_only_visible_entries(
    renderer: Renderer, monkeypatch: pytest.MonkeyPatch, selected: int
) -> None:
    pygame.display.set_mode((450, 185))
    setlist = Setlist(tuple(
        Song(index, f"{index:05}_Lied.txt", Path(), "Lied", "")
        for index in range(10_000)
    ))
    blocks = []
    draw_block = renderer._draw_menu_block

    def capture(
        page: Page, font: pygame.font.Font, area: pygame.Rect, *,
        selected: bool = False,
    ) -> None:
        height = renderer._page_height(page, font)
        bounds = pygame.Rect(area.left, area.top, area.width, height)
        blocks.append((page, bounds, selected))
        draw_block(page, font, area, selected=selected)

    monkeypatch.setattr(renderer, "_draw_menu_block", capture)
    assert renderer.draw_song_list(setlist, selected, 24) == 1

    area = renderer._content_area()
    assert blocks[0][0] == ("Songliste",)
    assert all(area.contains(bounds) for _, bounds, _ in blocks)
    assert 1 < len(blocks) - 1 < 10
    displayed = [int(page[0].split()[0]) for page, _, _ in blocks[1:]]
    assert displayed == list(range(displayed[0], displayed[-1] + 1))
    highlights = [index for index, (_, _, active) in enumerate(blocks) if active]
    assert len(highlights) == 1
    assert displayed[highlights[0] - 1] == selected
    x, y = blocks[highlights[0]][1].bottomright
    assert renderer.screen.get_at((x - 1, y - 1)) == pygame.Color("white")
    assert renderer.screen.get_at((0, 0)) == pygame.Color("black")


@pytest.mark.parametrize("width", [400, 1280])
def test_menu_shows_four_options_without_shrinking_at_maximum_font_size(
    renderer: Renderer, monkeypatch: pytest.MonkeyPatch, width: int,
) -> None:
    pygame.display.set_mode((width, 260))
    renderer.rotation = 180
    size = 48
    font = renderer._font_for_size(size)
    font_for_size = Mock(wraps=renderer._font_for_size)
    monkeypatch.setattr(renderer, "_font_for_size", font_for_size)
    blocks = []
    draw_block = renderer._draw_menu_block

    def capture(
        page: Page, used_font: pygame.font.Font, area: pygame.Rect, *,
        selected: bool = False,
    ) -> None:
        assert used_font is font
        assert all(font.size(line)[0] <= area.width for line in page)
        assert renderer._page_height(page, font) <= area.height
        blocks.extend(page)
        draw_block(page, used_font, area, selected=selected)

    monkeypatch.setattr(renderer, "_draw_menu_block", capture)
    renderer.draw_main_menu(size)
    assert [line[:1] for line in blocks] == ["A", "B", "C", "D"]
    assert blocks[0].endswith("48 px")
    assert blocks[1].endswith("180°")
    if width == 1280:
        assert blocks == [
            "A – Schriftgröße: 48 px", "B – Rotation: 180°",
            "C – Alle Songs", "D – Zurück zum Song",
        ]
    font_for_size.assert_called_once_with(size)


@pytest.mark.parametrize("rotation", [0, 90, 180, 270])
@pytest.mark.parametrize("view", ["song", "menu", "list", "splash"])
def test_frame_is_rotated_as_a_unit(renderer: Renderer, rotation: int, view: str) -> None:
    display = pygame.display.set_mode((720, 380))
    renderer.rotation = rotation
    song = Song(1, "01_Demo.txt", Path(), "Erster Song", "Text für die Anzeige")
    if view == "song":
        renderer.draw(40, renderer.layout(song.content, 40, song=song)[0], song=song)
    elif view == "menu":
        renderer.draw_main_menu(40)
    elif view == "list":
        renderer.draw_song_list(Setlist((song,)), 0, 40)
    else:
        renderer.draw_splash(None)

    logical_size = (380, 720) if rotation in (90, 270) else (720, 380)
    assert renderer.screen.get_size() == logical_size
    assert display.get_size() == (720, 380)
    expected = pygame.transform.rotate(renderer.screen, -rotation)
    pixels = pygame.image.tostring(display, "RGB")
    assert pixels == pygame.image.tostring(expected, "RGB")
    assert any(pixels)


def test_clockwise_rotation_and_canvas_resize(renderer: Renderer) -> None:
    display = pygame.display.set_mode((500, 300))
    renderer.rotation = 90
    renderer.screen.fill("black")
    renderer.screen.set_at((0, 0), pygame.Color("red"))
    renderer._present()
    assert display.get_at((499, 0)) == pygame.Color("red")
    pygame.display.set_mode((800, 450))
    assert renderer.screen.get_size() == (450, 800)


def test_empty_song_list_shows_notice_with_global_font(
    renderer: Renderer, monkeypatch: pytest.MonkeyPatch,
) -> None:
    draw_block = Mock(wraps=renderer._draw_menu_block)
    monkeypatch.setattr(renderer, "_draw_menu_block", draw_block)
    assert renderer.draw_song_list(Setlist(), 0, 48) == 1
    assert draw_block.call_args.args[0] == ("Songliste", "Keine Songs geladen")
    assert draw_block.call_args.args[1] is renderer._font_for_size(48)


def test_song_list_rewraps_long_title_with_the_global_font(
    renderer: Renderer, monkeypatch: pytest.MonkeyPatch,
) -> None:
    pygame.display.set_mode((480, 260))
    title = "Ein besonders langer Titel mit vielen gut lesbaren Wörtern"
    songs = Setlist((Song(1, "01_Lied.txt", Path(), title, "Text"),))
    draw_block = Mock(wraps=renderer._draw_menu_block)
    monkeypatch.setattr(renderer, "_draw_menu_block", draw_block)

    assert renderer.draw_song_list(songs, 0, 24) == 1
    small_rows = draw_block.call_args.args[0]
    assert draw_block.call_args.args[1] is renderer._font_for_size(24)
    draw_block.reset_mock()

    count = renderer.draw_song_list(songs, 0, 96)
    assert count > 1
    for page_index in range(1, count):
        renderer.draw_song_list(songs, 0, 96, page_index)
    rows = []
    for args, kwargs in draw_block.call_args_list:
        page, font, area = args
        assert kwargs["selected"]
        assert font is renderer._font_for_size(96)
        assert renderer._page_height(page, font) <= area.height
        assert all(font.size(line)[0] <= area.width for line in page)
        rows.extend(page)
    assert len(rows) > len(small_rows)
    assert "".join(" ".join(rows).split()) == "".join(f"01{title}".split())


def test_song_fixtures_have_distinct_lengths_and_fill_multiple_pages(
    renderer: Renderer, tmp_path: Path,
) -> None:
    for index in range(1, 6):
        lyrics = ("Eine Textzeile",) * (30 + index)
        lines = ("Titel", "", "[Strophe 1]", *lyrics, "[Refrain]", "[Solo]")
        (tmp_path / f"{index}_Demo.txt").write_text("\n".join(lines), encoding="utf-8")
    songs = load_songs(tmp_path).setlist
    assert len(songs) == 5
    lengths = {len(song.content.splitlines()) for song in songs}
    assert min(lengths) >= 30
    assert len(lengths) >= 4
    for song in songs:
        for marker in ("[Strophe 1]", "[Refrain]", "[Solo]"):
            assert marker in song.content.splitlines()
        pages = renderer.layout(song.content, 48)
        assert len(pages) > 1
        assert pages[0][0] == "[Strophe 1]"
        assert "[Refrain]" in [line for page in pages for line in page]


@pytest.mark.parametrize("separator", ["_", " - "])
@pytest.mark.parametrize("number", ["1", "01", "001"])
def test_display_number_keeps_filename_padding(
    tmp_path: Path, separator: str, number: str,
) -> None:
    path = tmp_path / f"{number}{separator}Mein Song.txt"
    path.write_text("Mein Song\n\nText", encoding="utf-8")
    song = load_songs(tmp_path).setlist.first
    assert song is not None
    assert song.number == 1
    assert song.display_number == number
    assert song.title == "Mein Song"


def test_page_layout_reserves_header_and_progress_gutter(
    renderer: Renderer, monkeypatch: pytest.MonkeyPatch,
) -> None:
    outer = renderer._content_area()
    header, rail, lyrics = renderer._song_areas(renderer._font_for_size(48))
    assert header.top == outer.top
    assert header.bottom < lyrics.top
    assert rail.right < lyrics.left
    assert lyrics.right == outer.right
    assert lyrics.bottom == outer.bottom
    assert rail.height == lyrics.height
    paginate = Mock(wraps=renderer._paginate)
    monkeypatch.setattr(renderer, "_paginate", paginate)
    renderer.layout("Text", 48)
    paginate.assert_called_once_with("Text", 48, lyrics, page_starts=None)


@pytest.mark.parametrize(
    ("index", "count", "position"),
    [(0, 3, 0.0), (1, 3, 0.5), (2, 3, 1.0), (0, 1, 0.5)],
)
def test_progress_indicator_matches_page_and_stays_inside_rail(
    renderer: Renderer, index: int, count: int, position: float
) -> None:
    assert progress_position(index, count) == position
    _, rail, _ = renderer._song_areas(renderer._font_for_size(48))
    path = Path("01 - Mein Song.txt")
    song = Song(1, path.name, path, "Mein Song", "Text")
    renderer.draw(48, ("Text",), song=song, page_index=index, page_count=count)
    marker_height = min(rail.height, max(12, rail.height // 12))
    top = rail.top + round((rail.height - marker_height) * position)
    assert renderer.screen.get_at((rail.centerx, top)) == renderer.foreground
    assert renderer.screen.get_at((rail.centerx, top + marker_height - 1)) == renderer.foreground
    outside_marker = top - 1 if top > rail.top else top + marker_height
    assert renderer.screen.get_at((rail.centerx, outside_marker)) == TRACK_COLOR


def test_header_renders_title_and_number_and_stays_fixed_between_pages(
    renderer: Renderer, monkeypatch: pytest.MonkeyPatch,
) -> None:
    path = Path("01 - Mein Song.txt")
    song = Song(1, path.name, path, "Mein Song", "Text")
    header, _, lyrics = renderer._song_areas(renderer._font_for_size(48), song)
    text_font = Mock(wraps=renderer._font_for_size(48))
    font_for_size = Mock(return_value=text_font)
    monkeypatch.setattr(renderer, "_font_for_size", font_for_size)
    renderer.draw(48, ("Erste Zeile",), song=song, page_index=0, page_count=2)
    first_header = pygame.image.tostring(renderer.screen.subsurface(header), "RGB")
    first_lyrics = pygame.image.tostring(renderer.screen.subsurface(lyrics), "RGB")
    font_for_size.assert_called_once_with(48)
    assert text_font.render.call_args_list == [
        call(text, True, renderer.foreground)
        for text in ("01", "Mein Song", "Erste Zeile")
    ]

    renderer.draw(48, ("Andere Zeile",), song=song, page_index=1, page_count=2)
    assert pygame.image.tostring(renderer.screen.subsurface(header), "RGB") == first_header
    assert pygame.image.tostring(renderer.screen.subsurface(lyrics), "RGB") != first_lyrics


def test_taller_font_increases_header_and_leaves_lyrics_room(
    renderer: Renderer,
) -> None:
    path = Path("01 - Mein Song.txt")
    song = Song(1, path.name, path, "Mein Song", "\n".join(["Lied"] * 20))
    standard_header, _, _ = renderer._song_areas(
        renderer._font_for_size(48), song
    )
    font_size = 160
    font = renderer._font_for_size(font_size)
    header, _, lyrics = renderer._song_areas(font, song)

    assert header.height > standard_header.height
    assert header.height >= max(font.size(song.title)[1], font.size("01")[1])
    assert header.bottom < lyrics.top
    pages = renderer.layout(song.content, font_size, song=song)
    assert len(pages) > 1
    for page in pages:
        height = sum(max(font.size(line)[1], font.get_height()) for line in page)
        height += renderer.line_spacing * (len(page) - 1)
        assert height <= lyrics.height


def test_plus_and_minus_resize_every_song_text_element(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    (tmp_path / "01 - Dateiname.txt").write_text(
        "Mein Song\nPlatzhalter für Zeile 2\n[Strophe 1]\nErste Zeile", encoding="utf-8"
    )
    monkeypatch.setenv("SDL_VIDEODRIVER", "dummy")
    monkeypatch.setattr("lyricspi.app.display_settings_path", lambda: tmp_path / "settings.json")
    batches = iter([
        [pygame.event.Event(pygame.KEYDOWN, key=pygame.K_PLUS)],
        [pygame.event.Event(pygame.KEYDOWN, key=pygame.K_MINUS)],
        [pygame.event.Event(pygame.QUIT)],
    ])
    monkeypatch.setattr(pygame.event, "get", lambda: next(batches))
    draw = Renderer.draw
    drawn_sizes = []

    def capture(
        renderer: Renderer, font_size: int, page: Page, notice: str | None,
        **song_view,
    ) -> None:
        font = Mock(wraps=renderer._font_for_size(font_size))
        with patch.object(renderer, "_font_for_size", return_value=font) as select:
            draw(renderer, font_size, page, notice, **song_view)
        select.assert_called_once_with(font_size)
        assert font.render.call_args_list == [
            call(text, True, renderer.foreground)
            for text in ("01", "Mein Song", "[Strophe 1]", "Erste Zeile")
        ]
        drawn_sizes.append(font_size)

    monkeypatch.setattr(Renderer, "draw", capture)
    run(Config(
        display=DisplayConfig(font_size=40),
        songs=SongsConfig(directory=str(tmp_path)),
    ))
    assert drawn_sizes == [40, 44, 40]
