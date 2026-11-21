"""Entry point for the LyricsPi simulator."""

import argparse
import logging
import platform
import signal
from importlib.metadata import version
from pathlib import Path
from types import FrameType

from .config import DEFAULT_CONFIG_PATH, ConfigError, load_config


LOGGER = logging.getLogger("lyricspi")


def _stop_service(_signal: int, _frame: FrameType | None) -> None:
    raise SystemExit(0)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="LyricsPi starten")
    parser.add_argument("--config", type=Path, help="Pfad zur JSON-Datei")
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

    try:
        LOGGER.info("LyricsPi %s startet", version("lyricspi"))
        os_name = platform.system()
        if os_name == "Linux":
            try:
                os_release = platform.freedesktop_os_release()
                os_name = os_release.get("PRETTY_NAME", os_name)
            except OSError:
                pass
        LOGGER.info(
            "Betriebssystem: %s, Python: %s", os_name, platform.python_version()
        )
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
    signal.signal(signal.SIGTERM, _stop_service)
    raise SystemExit(main())
