"""Wrap and paginate lyrics using measured text dimensions."""

from collections.abc import Callable, Iterator


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
    """Fill each page with consecutive complete rows."""
    if width < 1 or height < line_height:
        raise LayoutTooSmall

    # Spacing only separates rows. The final row needs no space after it.
    available = height + line_spacing
    pages: list[Page] = []
    page: list[str] = []
    used = 0
    for line in content.splitlines():
        # Tabs use four-column stops. SDL_ttf cannot render embedded NULs.
        display_line = line.expandtabs(4).replace("\x00", "\ufffd")
        for row in _wrap_line(display_line, width, measure):
            row_height = line_height
            if row.strip():
                row_height = max(line_height, measure(row)[1])
            cost = row_height + line_spacing
            if cost > available:
                raise LayoutTooSmall
            if used + cost > available:
                pages.append(tuple(page))
                page.clear()
                used = 0
            page.append(row)
            used += cost

    if page:
        pages.append(tuple(page))
    # Keep blank rows inside the song, including across a page boundary.
    while pages and not any(row.strip() for row in pages[-1]):
        pages.pop()
    return tuple(pages)
