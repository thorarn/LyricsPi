"""Measure and draw song pages and notices on the Pygame display."""

import logging
from pathlib import Path

import pygame

from .config import DisplayConfig
from .layout import LayoutTooSmall, Page, paginate


LOGGER = logging.getLogger(__name__)
FONT_NAMES = ("Consolas", "DejaVu Sans Mono", "Liberation Mono", "Courier New")


class Renderer:
    def __init__(
        self, config: DisplayConfig, *, resizable: bool = False
    ) -> None:
        pygame.display.init()
        pygame.font.init()
        LOGGER.info("SDL-Bildschirmtreiber: %s", pygame.display.get_driver())
        desktop_sizes = pygame.display.get_desktop_sizes()
        if not desktop_sizes or min(desktop_sizes[0]) < 1:
            raise RuntimeError("Kein Bildschirm mit gültiger Auflösung erkannt.")
        LOGGER.info("Bildschirmauflösung: %d × %d", *desktop_sizes[0])

        if config.fullscreen:
            self.screen = pygame.display.set_mode(
                desktop_sizes[0], pygame.FULLSCREEN
            )
            pygame.display.set_allow_screensaver(False)
            pygame.mouse.set_visible(False)
        else:
            self.screen = pygame.display.set_mode(
                (config.window_width, config.window_height),
                pygame.RESIZABLE if resizable else 0,
            )
        pygame.display.set_caption("LyricsPi")
        LOGGER.info("Fenster initialisiert: %d × %d", *self.screen.get_size())

        self.foreground = pygame.Color(config.foreground)
        self.background = pygame.Color(config.background)
        self.margin_percent = config.margin_percent
        self.line_spacing = config.line_spacing
        self.font: pygame.font.Font | None = None
        self.font_size = 0

    def load_splash_logo(self, path: Path) -> pygame.Surface | None:
        try:
            return pygame.image.load(path).convert_alpha()
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
        if self.font is None or self.font_size != size:
            self.font = pygame.font.SysFont(FONT_NAMES, size)
            self.font_size = size
        return self.font

    def _content_area(self) -> pygame.Rect:
        width, height = self.screen.get_size()
        x = width * self.margin_percent // 100
        y = height * self.margin_percent // 100
        return pygame.Rect(x, y, width - 2 * x, height - 2 * y)

    def layout(self, content: str, font_size: int) -> tuple[Page, ...]:
        area = self._content_area()
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
        self, font_size: int, page: Page, notice: str | None = None
    ) -> None:
        self.screen.fill(self.background)
        area = self._content_area()
        if notice is None:
            self._draw_lines(page, self._font_for_size(font_size), area)
        elif area.width > 0 and area.height > 0:
            notice_size = min(font_size, 32)
            try:
                pages = self.layout(notice, notice_size)
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
