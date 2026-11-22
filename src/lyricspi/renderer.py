"""Measure and draw song pages and notices on the Pygame display."""

import logging
from functools import lru_cache
from pathlib import Path
from sys import platform

import pygame

from .config import DisplayConfig
from .layout import LayoutTooSmall, Page, TextPosition, paginate
from .setlist import Setlist, Song


LOGGER = logging.getLogger(__name__)
FONT_NAMES = ("Consolas", "DejaVu Sans Mono", "Liberation Mono", "Courier New")
TRACK_COLOR = pygame.Color("#555555")
MIN_THUMB_HEIGHT = 2
SINGLE_LINE_TRANSLATION = str.maketrans(
    {char: " " for char in "\t\r\n\v\f\x1c\x1d\x1e\x85\u2028\u2029"}
    | {"\x00": "\ufffd"}
)


def scroll_thumb(
    track: pygame.Rect, start_line: int, visible_lines: int, total_lines: int,
) -> pygame.Rect:
    """Map the visible range of layout rows onto the track."""
    if min(track.height, visible_lines, total_lines) <= 0:
        return pygame.Rect(track.left, track.top, track.width, 0)

    visible_lines = min(visible_lines, total_lines)
    hidden_lines = total_lines - visible_lines
    start_line = max(0, min(start_line, hidden_lines))
    minimum = min(MIN_THUMB_HEIGHT, track.height)
    if track.height * visible_lines < minimum * total_lines:
        # Scale the start over the travel left by the enlarged thumb.
        height = minimum
        offset = round((track.height - height) * start_line / hidden_lines)
    else:
        offset = round(track.height * start_line / total_lines)
        end = round(track.height * (start_line + visible_lines) / total_lines)
        height = end - offset
    return pygame.Rect(track.left, track.top + offset, track.width, height)


def truncate_song_list_line(
    text: str, font: pygame.font.Font, width: int, *, ellipsis: bool = True,
) -> str:
    """Fit a single line without measuring the full text of oversized titles."""
    if width <= 0:
        return ""
    text = text.translate(SINGLE_LINE_TRANSLATION)
    low, high = 0, min(1, len(text))
    while font.size(text[:high])[0] <= width:
        if high == len(text):
            return text
        low, high = high, min(2 * high, len(text))

    suffix = "…" if ellipsis and font.size("…")[0] <= width else ""
    if suffix:
        low = 0
    while high - low > 1:
        middle = (low + high) // 2
        if font.size(text[:middle] + suffix)[0] <= width:
            low = middle
        else:
            high = middle
    return text[:low].rstrip() + suffix


class Renderer:
    def __init__(
        self, config: DisplayConfig, *, resizable: bool = False
    ) -> None:
        pygame.display.init()
        pygame.font.init()
        driver = pygame.display.get_driver()
        LOGGER.info("SDL-Bildschirmtreiber: %s", driver)
        desktop_sizes = pygame.display.get_desktop_sizes()
        if not desktop_sizes or min(desktop_sizes[0]) < 1:
            raise RuntimeError("Kein Bildschirm mit gültiger Auflösung erkannt.")
        LOGGER.info("Bildschirmauflösung: %d × %d", *desktop_sizes[0])

        size = desktop_sizes[0] if config.fullscreen else (
            config.window_width, config.window_height,
        )
        flags = pygame.FULLSCREEN if config.fullscreen else (
            pygame.RESIZABLE if resizable else 0
        )
        try:
            display = pygame.display.set_mode(size, flags)
        except pygame.error as error:
            if platform.startswith("linux") and driver.lower() == "kmsdrm":
                raise RuntimeError(
                    f"KMSDRM konnte den Grafikmodus {size[0]} × {size[1]} "
                    f"nicht öffnen: {error}. Diagnose: tools/graphics_diagnostic.py"
                ) from error
            raise
        if config.fullscreen:
            pygame.display.set_allow_screensaver(False)
            pygame.mouse.set_visible(False)
        pygame.display.set_caption("LyricsPi")
        LOGGER.info("Fenster initialisiert: %d × %d", *display.get_size())

        self.rotation = config.rotation
        self._canvas: pygame.Surface | None = None
        self.foreground = pygame.Color(config.foreground)
        self.background = pygame.Color(config.background)
        self.margin_percent = config.margin_percent
        self.line_spacing = config.line_spacing
        self._fonts = lru_cache(maxsize=8)(pygame.font.SysFont)

    @property
    def display_size(self) -> tuple[int, int]:
        return pygame.display.get_surface().get_size()

    @property
    def screen(self) -> pygame.Surface:
        display = pygame.display.get_surface()
        if self.rotation == 0:
            return display
        width, height = display.get_size()
        size = (height, width) if self.rotation in (90, 270) else (width, height)
        if self._canvas is None or self._canvas.get_size() != size:
            self._canvas = pygame.Surface(size).convert(display)
        return self._canvas

    def _present(self) -> None:
        if self.rotation:
            frame = pygame.transform.rotate(self.screen, -self.rotation)
            pygame.display.get_surface().blit(frame, (0, 0))
        pygame.display.flip()

    def load_splash_logo(self, path: Path) -> pygame.Surface | None:
        try:
            return pygame.image.load(str(path)).convert_alpha()
        except (OSError, pygame.error) as error:
            LOGGER.info("Startlogo %s nicht verfügbar: %s", path, error)
            return None

    def draw_splash(self, logo: pygame.Surface | None) -> None:
        self.screen.fill((0, 0, 0))
        width, height = self.screen.get_size()
        area = pygame.Rect(0, 0, max(1, width * 3 // 4), max(1, height // 2))
        area.center = self.screen.get_rect().center
        image = logo
        if image is None:
            font = self._font_for_size(max(1, min(128, height // 5)))
            image = font.render("LyricsPi", True, (255, 255, 255))
        if not area.contains(image.get_rect(center=area.center)):
            bounds = image.get_rect().fit(area)
            size = max(1, bounds.width), max(1, bounds.height)
            image = pygame.transform.smoothscale(image, size)
        self.screen.blit(image, image.get_rect(center=area.center))
        self._present()

    def _font_for_size(self, size: int) -> pygame.font.Font:
        return self._fonts(FONT_NAMES, size)

    def _content_area(self) -> pygame.Rect:
        width, height = self.screen.get_size()
        x = width * self.margin_percent // 100
        y = height * self.margin_percent // 100
        return pygame.Rect(x, y, width - 2 * x, height - 2 * y)

    def layout(
        self, content: str, font_size: int, *, song: Song | None = None,
        page_starts: list[TextPosition] | None = None,
    ) -> tuple[Page, ...]:
        _, _, lyrics = self._song_areas(self._font_for_size(font_size), song)
        return self._paginate(content, font_size, lyrics, page_starts=page_starts)

    def _song_areas(
        self, font: pygame.font.Font, song: Song | None = None
    ) -> tuple[pygame.Rect, pygame.Rect, pygame.Rect]:
        area = self._content_area()
        text_height = font.get_height()
        if song is not None:
            text_height = max(
                text_height, font.size(song.title)[1],
                font.size(song.display_number)[1],
            )
        base_height = min(108, area.height // 6)
        height = min(area.height, max(28, base_height, text_height))
        gap = max(4, min(12, area.height // 30))
        rail_width = max(2, min(8, area.width // 40))
        gutter = rail_width + max(4, min(16, area.width // 30))
        header = pygame.Rect(area.left, area.top, area.width, height)
        body_top = min(area.bottom, header.bottom + gap)
        rail = pygame.Rect(
            area.left, body_top, rail_width, area.bottom - body_top
        )
        lyrics = pygame.Rect(
            area.left + gutter, body_top, max(0, area.width - gutter), rail.height
        )
        return header, rail, lyrics

    def _paginate(
        self, content: str, font_size: int, area: pygame.Rect, *,
        page_starts: list[TextPosition] | None = None,
    ) -> tuple[Page, ...]:
        font = self._font_for_size(font_size)
        return paginate(
            content,
            area.width,
            area.height,
            font.size,
            font.get_height(),
            self.line_spacing,
            page_starts=page_starts,
        )

    def _fitting_pages(
        self, content: str, font: pygame.font.Font, area: pygame.Rect
    ) -> tuple[Page, ...]:
        try:
            return paginate(
                content, area.width, area.height, font.size, font.get_height(),
                self.line_spacing,
            )
        except LayoutTooSmall:
            return ()

    def _page_height(self, page: Page, font: pygame.font.Font) -> int:
        return sum(max(font.get_height(), font.size(line)[1]) for line in page) + (
            len(page) - 1
        ) * self.line_spacing

    def draw_main_menu(self, font_size: int) -> None:
        self.screen.fill("black")
        area = self._content_area()
        font = self._font_for_size(font_size)
        options = (
            f"A – Schriftgröße: {font_size} px",
            f"B – Rotation: {self.rotation}°",
            "C – Alle Songs",
            "D – Zurück zum Song",
        )
        pages = self._fitting_pages("\n".join(options), font, area)
        if len(pages) != 1:
            compact = (f"A – {font_size} px", f"B – {self.rotation}°")
            if all(font.size(option)[0] <= area.width for option in compact):
                compact += tuple(self._ellipsize(option, font, area.width) for option in options[2:])
                if self._page_height(compact, font) <= area.height:
                    pages = (compact,)
        self._draw_menu_pages(pages if len(pages) == 1 else (), 0, font, area)

    def _draw_menu_pages(
        self, pages: tuple[Page, ...], page_index: int, font: pygame.font.Font,
        area: pygame.Rect, *, selected: bool = False,
    ) -> int:
        if pages:
            self._draw_menu_block(
                pages[page_index % len(pages)], font, area, selected=selected
            )
        else:
            self._draw_small_window_notice(font, area, "white")
        self._present()
        return len(pages)

    def _draw_menu_block(
        self, page: Page, font: pygame.font.Font, area: pygame.Rect, *,
        selected: bool = False,
    ) -> None:
        if selected:
            bounds = pygame.Rect(
                area.left, area.top, area.width, self._page_height(page, font)
            )
            self.screen.fill("white", bounds)
        self._draw_lines(page, font, area, color="black" if selected else "white")

    def draw_song_list(
        self, setlist: Setlist, selected: int, font_size: int, page_index: int = 0
    ) -> int:
        self.screen.fill("black")
        area = self._content_area()
        font = self._font_for_size(font_size)
        title = "Songliste"
        if not setlist:
            empty = "Keine Songs geladen"
            pages = self._fitting_pages(f"{title}\n{empty}", font, area)
            if len(pages) != 1:
                pages = self._fitting_pages(empty, font, area)
            return self._draw_menu_pages(pages, page_index, font, area)

        def song_row(index: int) -> Page:
            song = setlist[index]
            prefix = f"{song.display_number}  "
            line = truncate_song_list_line(
                prefix + song.title, font, area.width,
                ellipsis=font.size(prefix + "…")[0] <= area.width,
            )
            return (line,)

        current = song_row(selected)
        current_height = self._page_height(current, font)
        if current_height > area.height:
            return self._draw_menu_pages((), 0, font, area)
        heading = (title,)
        heading_height = self._page_height(heading, font) + self.line_spacing
        if (
            font.size(title)[0] <= area.width
            and heading_height + current_height <= area.height
        ):
            self._draw_menu_block(heading, font, area)
            area.top += heading_height
            area.height -= heading_height

        remaining = area.height - current_height
        below: list[Page] = []
        above: list[Page] = []
        for indices, visible in (
            (range(selected + 1, len(setlist)), below),
            (range(selected - 1, -1, -1), above),
        ):
            for index in indices:
                if remaining < font.get_height() + self.line_spacing:
                    break
                row = song_row(index)
                height = self._page_height(row, font) + self.line_spacing
                if height > remaining:
                    break
                visible.append(row)
                remaining -= height

        for index, page in enumerate((*reversed(above), current, *below)):
            self._draw_menu_block(page, font, area, selected=index == len(above))
            area.top += self._page_height(page, font) + self.line_spacing
        self._present()
        return 1

    def _draw_small_window_notice(
        self, font: pygame.font.Font, area: pygame.Rect, color: pygame.Color | str,
        notice: str = "Fenster zu klein.",
    ) -> None:
        # The diagnostic must stay visible when even a line cannot fit.
        text = font.render(notice, True, color)
        bounds = text.get_rect().fit(area)
        size = max(1, bounds.width), max(1, bounds.height)
        self.screen.blit(pygame.transform.smoothscale(text, size), area)

    def draw(
        self,
        font_size: int,
        page: Page,
        notice: str | None = None,
        *,
        song: Song | None = None,
        start_line: int = 0,
        total_lines: int | None = None,
    ) -> None:
        self.screen.fill(self.background)
        area = self._content_area()
        if notice is None:
            font = self._font_for_size(font_size)
            header, rail, lyrics = self._song_areas(font, song)
            if song is not None:
                self._draw_header(song, font, header)
                self._draw_scrollbar(
                    rail, start_line, len(page),
                    len(page) if total_lines is None else total_lines,
                )
            self._draw_lines(page, font, lyrics)
        elif area.width > 0 and area.height > 0:
            font = self._font_for_size(font_size)
            pages = self._fitting_pages(notice, font, area)
            if len(pages) == 1:
                self._draw_lines(pages[0], font, area)
            else:
                self._draw_small_window_notice(font, area, self.foreground, notice)
        self._present()

    def _draw_header(
        self, song: Song, font: pygame.font.Font, header: pygame.Rect
    ) -> None:
        gap = 8
        number_width = header.width - font.size("…")[0] - gap
        number_text = self._ellipsize(song.display_number, font, number_width)
        number = font.render(number_text, True, self.foreground)
        self.screen.blit(number, number.get_rect(midright=header.midright))

        title_width = header.width - number.get_width() - gap
        title = self._ellipsize(song.title, font, title_width)
        text = font.render(title, True, self.foreground)
        self.screen.blit(text, text.get_rect(midleft=header.midleft))

    @staticmethod
    def _ellipsize(text: str, font: pygame.font.Font, width: int) -> str:
        if font.size(text)[0] <= width:
            return text
        ellipsis = "…"
        if font.size(ellipsis)[0] > width:
            return ""
        while font.size(text + ellipsis)[0] > width:
            text = text[:-1]
        return text.rstrip() + ellipsis

    def _draw_scrollbar(
        self, track: pygame.Rect, start_line: int, visible_lines: int, total_lines: int,
    ) -> None:
        pygame.draw.rect(self.screen, TRACK_COLOR, track)
        thumb = scroll_thumb(track, start_line, visible_lines, total_lines)
        pygame.draw.rect(self.screen, "white", thumb)

    def _draw_lines(
        self, page: Page, font: pygame.font.Font, area: pygame.Rect, *,
        color: pygame.Color | str | None = None,
    ) -> None:
        if color is None:
            color = self.foreground
        y = area.top
        for line in page:
            height = font.get_height()
            if line.strip():
                text = font.render(line, True, color)
                self.screen.blit(text, (area.left, y))
                height = max(height, text.get_height())
            y += height + self.line_spacing
