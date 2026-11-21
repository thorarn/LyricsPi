"""Measure and draw song pages and notices on the Pygame display."""

import logging
from functools import lru_cache
from pathlib import Path
from sys import platform

import pygame

from .config import DisplayConfig
from .layout import LayoutTooSmall, Page, paginate
from .setlist import Song


LOGGER = logging.getLogger(__name__)
FONT_NAMES = ("Consolas", "DejaVu Sans Mono", "Liberation Mono", "Courier New")
TRACK_COLOR = pygame.Color("#555555")


def progress_position(page_index: int, page_count: int) -> float:
    if page_count <= 1:
        return 0.5
    return max(0.0, min(1.0, page_index / (page_count - 1)))


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
            self.screen = pygame.display.set_mode(size, flags)
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
        LOGGER.info("Fenster initialisiert: %d × %d", *self.screen.get_size())

        self.foreground = pygame.Color(config.foreground)
        self.background = pygame.Color(config.background)
        self.margin_percent = config.margin_percent
        self.line_spacing = config.line_spacing
        self._fonts = lru_cache(maxsize=8)(pygame.font.SysFont)

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
        pygame.display.flip()

    def _font_for_size(self, size: int) -> pygame.font.Font:
        return self._fonts(FONT_NAMES, size)

    def _content_area(self) -> pygame.Rect:
        width, height = self.screen.get_size()
        x = width * self.margin_percent // 100
        y = height * self.margin_percent // 100
        return pygame.Rect(x, y, width - 2 * x, height - 2 * y)

    def layout(
        self, content: str, font_size: int, *, song: Song | None = None
    ) -> tuple[Page, ...]:
        _, _, lyrics = self._song_areas(self._font_for_size(font_size), song)
        return self._paginate(content, font_size, lyrics)

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
        self, content: str, font_size: int, area: pygame.Rect
    ) -> tuple[Page, ...]:
        font = self._font_for_size(font_size)
        return paginate(
            content,
            area.width,
            area.height,
            font.size,
            font.get_height(),
            self.line_spacing,
        )

    def draw(
        self,
        font_size: int,
        page: Page,
        notice: str | None = None,
        *,
        song: Song | None = None,
        page_index: int = 0,
        page_count: int = 1,
    ) -> None:
        self.screen.fill(self.background)
        area = self._content_area()
        if notice is None:
            font = self._font_for_size(font_size)
            header, rail, lyrics = self._song_areas(font, song)
            if song is not None:
                self._draw_header(song, font, header)
                self._draw_progress(rail, page_index, page_count)
            self._draw_lines(page, font, lyrics)
        elif area.width > 0 and area.height > 0:
            notice_size = min(font_size, 32)
            try:
                pages = self._paginate(notice, notice_size, area)
            except LayoutTooSmall:
                pages = ()
            font = self._font_for_size(notice_size)
            if len(pages) == 1:
                self._draw_lines(pages[0], font, area)
            else:
                # A notice must remain visible even if lyrics no longer fit.
                text = font.render(notice, True, self.foreground)
                bounds = text.get_rect().fit(area)
                size = max(1, bounds.width), max(1, bounds.height)
                self.screen.blit(
                    pygame.transform.smoothscale(text, size), area
                )
        pygame.display.flip()

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

    def _draw_progress(
        self, track: pygame.Rect, page_index: int, page_count: int
    ) -> None:
        pygame.draw.rect(self.screen, TRACK_COLOR, track)
        marker_height = min(track.height, max(12, track.height // 12))
        position = progress_position(page_index, page_count)
        offset = round((track.height - marker_height) * position)
        marker = pygame.Rect(
            track.left, track.top + offset, track.width, marker_height
        )
        pygame.draw.rect(self.screen, self.foreground, marker)

    def _draw_lines(
        self, page: Page, font: pygame.font.Font, area: pygame.Rect
    ) -> None:
        y = area.top
        for line in page:
            height = font.get_height()
            if line.strip():
                text = font.render(line, True, self.foreground)
                self.screen.blit(text, (area.left, y))
                height = max(height, text.get_height())
            y += height + self.line_spacing
