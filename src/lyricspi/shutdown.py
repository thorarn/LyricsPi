"""Request one regular Linux poweroff through systemd-logind."""

import logging
import subprocess
from sys import platform


LOGGER = logging.getLogger(__name__)
POWEROFF_COMMAND = (
    "busctl",
    "--system",
    "--timeout=5s",
    "call",
    "org.freedesktop.login1",
    "/org/freedesktop/login1",
    "org.freedesktop.login1.Manager",
    "PowerOff",
    "b",
    "false",
)


def request_shutdown() -> None:
    if not platform.startswith("linux"):
        return
    try:
        subprocess.run(
            POWEROFF_COMMAND, check=True, capture_output=True, text=True, timeout=6
        )
    except subprocess.CalledProcessError as error:
        LOGGER.error(
            "Linux-Shutdown fehlgeschlagen (Exit %d): %s",
            error.returncode,
            (error.stderr or "").strip(),
        )
    except (OSError, subprocess.TimeoutExpired) as error:
        LOGGER.error("Linux-Shutdown fehlgeschlagen: %s", error)
    else:
        LOGGER.info("Linux-Shutdown von logind angenommen.")
