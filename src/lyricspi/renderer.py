"""Initialize the Pygame display and draw the demo and startup notices."""

import logging

import pygame

from .config import DisplayConfig


LOGGER = logging.getLogger(__name__)
DEMO_LINES = (
    "LyricsPi – Demo Mode",
    "",
    "Dies ist ein Beispiel-Songtext.",
    "Hier erscheint später der eigentliche Song.",
)


class Renderer:
    def __init__(self, config: DisplayConfig) -> None:
        pygame.display.init()
        pygame.font.init()
        desktop_sizes = pygame.display.get_desktop_sizes()
        if not desktop_sizes:
            raise RuntimeError("Bildschirmauflösung konnte nicht ermittelt werden")
        LOGGER.info("Bildschirmauflösung: %d × %d", *desktop_sizes[0])

        if config.fullscreen:
            self.screen = pygame.display.set_mode(
                desktop_sizes[0], pygame.FULLSCREEN
            )
        else:
            self.screen = pygame.display.set_mode(
                (config.window_width, config.window_height)
            )
        pygame.display.set_caption("LyricsPi")
        LOGGER.info("Fenster initialisiert: %d × %d", *self.screen.get_size())

        self.foreground = pygame.Color(config.foreground)
        self.background = pygame.Color(config.background)
        width, height = self.screen.get_size()
        self.margin_x = width * config.margin_percent // 100
        self.margin_y = height * config.margin_percent // 100
        self.text_width = width - 2 * self.margin_x

    def draw(self, font_size: int, notice: str | None = None) -> None:
        font = pygame.font.Font(None, font_size)
        self.screen.fill(self.background)
        y = self.margin_y
        lines = DEMO_LINES if notice is None else (*DEMO_LINES, "", notice)
        for line in lines:
            if line:
                text = font.render(line, True, self.foreground)
                if text.get_width() > self.text_width:
                    text = pygame.transform.smoothscale(
                        text, (self.text_width, text.get_height())
                    )
                self.screen.blit(text, (self.margin_x, y))
            y += font.get_linesize()
        pygame.display.flip()
