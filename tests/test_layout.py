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


def test_keeps_short_stanza_together_at_page_boundary() -> None:
    assert paginate("A\nB\n\nC\nD", 20, 4, measure, 1, 0) == (
        ("A", "B", ""),
        ("C", "D"),
    )


def test_splits_long_stanza_and_omits_blank_pages_at_end() -> None:
    content = "\n".join(f"Zeile {number}" for number in range(100))
    pages = paginate(content + "\n\n\n\n", 30, 7, measure, 1, 0)

    assert len(pages) == 15
    assert tuple(row for page in pages for row in page if row) == tuple(
        content.splitlines()
    )
    assert all(1 <= len(page) <= 7 for page in pages)
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
