"""Entry point for the LyricsPi simulator."""

import argparse
import logging
from importlib.metadata import version
from pathlib import Path

from .config import DEFAULT_CONFIG_PATH, ConfigError, load_config


LOGGER = logging.getLogger("lyricspi")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="LyricsPi-Demo starten")
    parser.add_argument("--config", type=Path, help="Pfad zur JSON-Datei")
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

    try:
        LOGGER.info("LyricsPi %s startet", version("lyricspi"))
        config = load_config(args.config)
        LOGGER.setLevel(
            logging.DEBUG if config.system.development_mode else logging.INFO
        )
        LOGGER.info(
            "Konfiguration geladen (%s)", args.config or DEFAULT_CONFIG_PATH
        )
        LOGGER.debug("Aktive Konfiguration: %s", config)

        from .app import run

        run(config)
    except ConfigError as error:
        LOGGER.error("Konfigurationsfehler: %s", error)
        return 1
    except Exception:
        LOGGER.exception("Unerwarteter Programmfehler")
        return 1
    finally:
        LOGGER.info("LyricsPi beendet")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
