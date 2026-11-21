import pytest

from lyricspi.layout import LayoutTooSmall, paginate


def measure(text: str) -> tuple[int, int]:
    return len(text), 1


def test_short_text_keeps_original_breaks_and_indentation() -> None:
    content = "  Am     C\r\nÜber den See\r\n\r\n  G  \rnoch eine Zeile\n"

    assert paginate(content, 40, 9, measure, 1, 1) == (
        ("  Am     C", "Über den See", "", "  G  ", "noch eine Zeile"),
    )


def test_prefers_word_breaks_and_preserves_spaces() -> None:
    assert paginate("abc def ghi", 6, 4, measure, 1, 0) == (
        ("abc ", "def ", "ghi"),
    )
    assert paginate("   abcdef", 5, 4, measure, 1, 0) == (
        ("   ab", "cdef"),
    )
    assert paginate("abc def", 3, 4, measure, 1, 0) == (("abc", "def"),)


def test_uses_measured_width_and_height_with_spacing() -> None:
    def dimensions(text: str) -> tuple[int, int]:
        return sum(3 if char == "W" else 1 for char in text), 3

    assert paginate("iiWW", 4, 7, dimensions, 2, 1) == (
        ("ii", "W"),
        ("W",),
    )


def test_page_fills_with_one_and_a_half_stanzas() -> None:
    assert paginate("A\nB\n\nC\nD", 20, 4, measure, 1, 0) == (
        ("A", "B", "", "C"),
        ("D",),
    )


def test_pages_fit_rows_of_different_measured_heights() -> None:
    heights = {"A": 3, "B": 2, "C": 4, "D": 1, "E": 1}

    def dimensions(text: str) -> tuple[int, int]:
        return len(text), heights[text]

    assert paginate("A\nB\nC\nD\nE", 20, 6, dimensions, 1, 1) == (
        ("A", "B"),
        ("C", "D"),
        ("E",),
    )


@pytest.mark.parametrize("rows_per_page", [2, 4])
def test_stanza_can_fit_or_continue_on_second_page(rows_per_page: int) -> None:
    lines = ("[Strophe 1]", "A", "B", "C")
    pages = paginate("\n".join(lines), 20, rows_per_page, measure, 1, 0)
    assert pages == tuple(
        lines[start : start + rows_per_page]
        for start in range(0, len(lines), rows_per_page)
    )


def test_section_marker_can_be_last_line_and_chorus_crosses_page_boundary() -> None:
    lines = ("Strophe", "", "[Refrain]", "R1", "R2", "R3", "R4", "[Solo]")
    pages = paginate("\n".join(lines), 20, 3, measure, 1, 0)

    assert pages == (lines[:3], lines[3:6], lines[6:])
    assert tuple(row for page in pages for row in page) == lines


def test_blank_rows_are_counted_even_across_page_boundaries() -> None:
    lines = ("A", "", "", "   ", "", "B", "C")
    pages = paginate("\n".join(lines), 20, 2, measure, 1, 0)

    assert pages == (("A", ""), ("", "   "), ("", "B"), ("C",))
    assert tuple(row for page in pages for row in page) == lines


def test_wrapped_rows_are_paginated_individually_in_order() -> None:
    pages = paginate("ABCDEFGHI\n\nJKL", 3, 2, measure, 1, 0)
    assert pages == (("ABC", "DEF"), ("GHI", ""), ("JKL",))


def test_page_start_tracks_source_line_and_wrapped_column() -> None:
    starts = []
    content = "ABCDEFGHI\n\nJKL\n\n\n"
    assert paginate(content, 3, 2, measure, 1, 0, page_starts=starts) == (
        ("ABC", "DEF"), ("GHI", ""), ("JKL", ""),
    )
    assert starts == [(0, 0), (0, 6), (2, 0)]
    paginate(content, 4, 1, measure, 1, 0, page_starts=starts)
    assert starts == [(0, 0), (0, 4), (0, 8), (1, 0), (2, 0)]


def test_splits_long_stanza_and_omits_blank_pages_at_end() -> None:
    content = "\n".join(f"Zeile {number}" for number in range(100))
    pages = paginate(content + "\n\n\n\n", 30, 7, measure, 1, 0)

    assert len(pages) == 15
    assert tuple(row for page in pages for row in page if row) == tuple(
        content.splitlines()
    )
    assert all(len(page) == 7 for page in pages[:-1])
    assert pages[-1] == (*content.splitlines()[-2:], "", "", "")
    assert paginate("A\n\n\n\n", 30, 1, measure, 1, 0) == (("A",),)


def test_extremely_long_word_retains_all_characters() -> None:
    content = "x" * 200_000
    pages = paginate(content, 37, 10, measure, 1, 0)

    assert all(len(row) <= 37 for page in pages for row in page)
    assert "".join(row for page in pages for row in page) == content


@pytest.mark.parametrize(("width", "height"), [(1, 5), (25, 1)])
def test_rejects_area_that_cannot_fit_a_character_or_row(
    width: int, height: int
) -> None:
    with pytest.raises(LayoutTooSmall):
        paginate("W", width, height, lambda text: (2, 2), 2, 1)
