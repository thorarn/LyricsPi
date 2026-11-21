"""Wrap and paginate lyrics using measured text dimensions."""

from collections.abc import Callable, Iterator
from itertools import groupby


Page = tuple[str, ...]
MeasureText = Callable[[str], tuple[int, int]]


class LayoutTooSmall(ValueError):
    """At least one character or line does not fit the available area."""


def _wrap_line(line: str, width: int, measure: MeasureText) -> Iterator[str]:
    if not line.strip():
        yield line
        return

    start = 0
    while start < len(line):
        end = start
        limit = start + 1
        while measure(line[start:limit])[0] <= width:
            end = limit
            if end == len(line):
                break
            limit = min(len(line), start + 2 * (end - start))
        while limit - end > 1:
            middle = (end + limit) // 2
            if measure(line[start:middle])[0] <= width:
                end = middle
            else:
                limit = middle

        if end == start:
            raise LayoutTooSmall
        next_start = end
        # A word separator at the wrap must not indent the following word.
        if end < len(line):
            if line[end].isspace():
                if line[start:end].strip():
                    while next_start < len(line) and line[next_start].isspace():
                        next_start += 1
            else:
                for index in range(end - 1, start, -1):
                    if line[index].isspace():
                        if line[start:index].strip():
                            end = next_start = index + 1
                        break
        yield line[start:end]
        start = next_start


def paginate(
    content: str,
    width: int,
    height: int,
    measure: MeasureText,
    line_height: int,
    line_spacing: int,
) -> tuple[Page, ...]:
    """Return pages that fit, keeping short stanzas together."""
    if width < 1 or height < line_height:
        raise LayoutTooSmall

    # Spacing only separates rows. The final row needs no space after it.
    available = height + line_spacing
    pages: list[Page] = []
    page: list[str] = []
    used = 0
    has_text = False

    def finish_page() -> None:
        nonlocal used, has_text
        if has_text:
            pages.append(tuple(page))
        page.clear()
        used = 0
        has_text = False

    original_lines = groupby(
        content.splitlines(), lambda line: bool(line.strip())
    )
    for stanza, lines in original_lines:
        wrapped = (
            row
            for line in lines
            # Tabs use four-column stops. SDL_ttf cannot render embedded NULs.
            for row in _wrap_line(
                line.expandtabs(4).replace("\x00", "\ufffd"), width, measure
            )
        )
        rows = [
            (row, max(line_height, measure(row)[1]) + line_spacing)
            if row.strip()
            else (row, line_height + line_spacing)
            for row in wrapped
        ]
        stanza_height = sum(cost for _, cost in rows)
        if stanza and stanza_height <= available < used + stanza_height:
            finish_page()

        for row, cost in rows:
            if cost > available:
                raise LayoutTooSmall
            if used + cost > available:
                finish_page()
            page.append(row)
            used += cost
            has_text |= bool(row.strip())

    finish_page()
    return tuple(pages)
