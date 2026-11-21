"""Probe the local SDL display without changing system configuration."""

import argparse
import ctypes
import logging
import os
import re
import stat
import subprocess
import sys
import time
from pathlib import Path
from types import ModuleType


LOGGER = logging.getLogger("lyricspi.graphics")
LIBRARIES = (
    "libEGL.so.1", "libEGL_mesa.so.0", "libGLESv2.so.2", "libgbm.so.1",
    "libdrm.so.2",
)
ENV_PREFIXES = ("SDL_", "EGL_", "GBM_", "MESA_", "LIBGL_", "__EGL_")
ENV_NAMES = {
    "DISPLAY", "LD_LIBRARY_PATH", "LD_PRELOAD", "TERM", "WAYLAND_DISPLAY",
    "XDG_RUNTIME_DIR", "XDG_SESSION_TYPE",
}
SDL_LIBRARY = re.compile(r"libSDL2(?:-2[^/]*|\.so[^/]*)$")


def log_environment() -> None:
    for name, value in sorted(os.environ.items()):
        if name.startswith(ENV_PREFIXES) or name in ENV_NAMES:
            LOGGER.info("%s=%s", name, value)


def mapped_sdl() -> Path | None:
    """Find the SDL2 actually loaded by pygame, including vendored copies."""
    maps = Path("/proc/self/maps").read_text(encoding="utf-8", errors="replace")
    for line in maps.splitlines():
        columns = line.split(maxsplit=5)
        if len(columns) == 6:
            path = Path(columns[5])
            if path.is_absolute() and SDL_LIBRARY.fullmatch(path.name):
                return path
    return None


def log_video_drivers(pygame: ModuleType) -> None:
    try:
        if sys.platform.startswith("linux"):
            library = mapped_sdl()
        elif sys.platform == "win32":
            library = Path(pygame.__file__).with_name("SDL2.dll")
        else:
            library = None
        if library is None:
            LOGGER.warning("Die von Pygame geladene SDL2-Bibliothek wurde nicht gefunden.")
            return
        sdl = ctypes.CDLL(str(library))
        sdl.SDL_GetNumVideoDrivers.argtypes = []
        sdl.SDL_GetNumVideoDrivers.restype = ctypes.c_int
        get_driver = sdl.SDL_GetVideoDriver
        get_driver.argtypes = [ctypes.c_int]
        get_driver.restype = ctypes.c_char_p
        drivers = [
            name.decode("ascii", errors="replace")
            for index in range(sdl.SDL_GetNumVideoDrivers())
            if (name := get_driver(index))
        ]
        LOGGER.info("SDL2-Bibliothek: %s", library)
        LOGGER.info("SDL-Videotreiber: %s", ", ".join(drivers))
    except (AttributeError, OSError) as error:
        LOGGER.warning("SDL-Videotreiber konnten nicht abgefragt werden: %s", error)


def log_linux_resources() -> None:
    import grp
    import pwd

    members = []
    for gid in sorted({os.getegid(), *os.getgroups()}):
        try:
            members.append(grp.getgrgid(gid).gr_name)
        except KeyError:
            members.append(str(gid))
    uid = os.geteuid()
    try:
        account = pwd.getpwuid(uid).pw_name
    except KeyError:
        account = str(uid)
    LOGGER.info("Konto: %s (UID %d), Gruppen: %s", account, uid, ", ".join(members))
    try:
        tty = os.ttyname(sys.stdin.fileno())
    except (OSError, ValueError):
        tty = "keine"
    try:
        active = Path("/sys/class/tty/tty0/active").read_text().strip()
    except OSError as error:
        active = str(error)
    LOGGER.info("Eingabekonsole: %s, aktive VT: %s", tty, active)

    drm = None
    for name in LIBRARIES:
        try:
            library = ctypes.CDLL(name)
            LOGGER.info("%s geladen", name)
            if name == "libdrm.so.2":
                drm = library.drmIsMaster
                drm.argtypes = [ctypes.c_int]
                drm.restype = ctypes.c_int
        except (AttributeError, OSError) as error:
            LOGGER.warning("%s: %s", name, error)
    dri = Path("/dev/dri")
    nodes = {dri / "card0", dri / "renderD128"}
    nodes.update(dri.glob("card[0-9]*"))
    nodes.update(dri.glob("renderD[0-9]*"))
    for node in sorted(nodes):
        try:
            info = node.stat()
            if not stat.S_ISCHR(info.st_mode):
                LOGGER.warning("%s ist kein Zeichengerät.", node)
                continue
            LOGGER.info(
                "%s %s UID=%d GID=%d",
                node, stat.filemode(info.st_mode), info.st_uid, info.st_gid,
            )
            fd = os.open(node, os.O_RDWR | os.O_CLOEXEC)
            try:
                master = "nicht abgefragt"
                if drm is not None and node.name.startswith("card"):
                    master = "ja" if drm(fd) == 1 else "nein"
                LOGGER.info("%s O_RDWR erfolgreich, DRM-Master: %s", node, master)
            finally:
                os.close(fd)
        except OSError as error:
            LOGGER.warning("%s: %s", node, error)
    for connector in sorted(Path("/sys/class/drm").glob("card*-*/status")):
        try:
            LOGGER.info("%s: %s", connector.parent.name, connector.read_text().strip())
        except OSError as error:
            LOGGER.warning("%s: %s", connector, error)

    packages = (
        "python3-pygame", "libsdl2-2.0-0", "libsdl2-classic", "libsdl2-compat",
        "libsdl3-0", "libegl1", "libegl-mesa0", "libgles2", "libgbm1", "libdrm2",
        "libgl1-mesa-dri",
    )
    try:
        result = subprocess.run(
            ["dpkg-query", "-W", "-f=${Package} ${Version}\n", *packages],
            capture_output=True, text=True, timeout=4,
        )
        for line in result.stdout.splitlines():
            LOGGER.info("APT-Paket: %s", line)
    except (OSError, subprocess.SubprocessError) as error:
        LOGGER.warning("Paketstand nicht verfügbar: %s", error)


def show_test_image(pygame: ModuleType, seconds: float, windowed: bool) -> None:
    pygame.display.init()
    driver = pygame.display.get_driver()
    desktop = pygame.display.get_desktop_sizes()
    LOGGER.info("Aktiver SDL-Treiber: %s, gemeldete Auflösungen: %s", driver, desktop)
    if not desktop or min(desktop[0]) < 1:
        raise RuntimeError("Keine gültige Bildschirmauflösung.")
    size = (640, 360) if windowed else desktop[0]
    flags = 0 if windowed else pygame.FULLSCREEN
    LOGGER.info("Teste set_mode(%s, Vollbild=%s)", size, not windowed)
    screen = pygame.display.set_mode(size, flags)
    screen.fill((0, 0, 0))
    width, height = screen.get_size()
    for index, color in enumerate(((255, 255, 255), (255, 0, 0), (0, 255, 0), (0, 0, 255))):
        screen.fill(color, (index * width // 4, height // 3, width // 4, height // 3))
    pygame.display.flip()
    LOGGER.info("Testbild ausgegeben: %d × %d", width, height)
    deadline = time.monotonic() + seconds
    clock = pygame.time.Clock()
    while time.monotonic() < deadline:
        for event in pygame.event.get():
            if event.type == pygame.QUIT or (
                event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE
            ):
                return
        clock.tick(20)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="LyricsPi SDL-/HDMI-Diagnose")
    parser.add_argument("--driver", help="SDL-Treiber für diesen Testlauf")
    parser.add_argument("--card", type=int, choices=range(100), metavar="0–99",
                        help="DRM-Kartennummer für diesen KMSDRM-Testlauf")
    parser.add_argument("--seconds", type=float, default=8)
    parser.add_argument("--windowed", action="store_true")
    parser.add_argument("--report-only", action="store_true")
    args = parser.parse_args(argv)
    if not 0 <= args.seconds <= 60:
        parser.error("--seconds muss zwischen 0 und 60 liegen.")
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    if args.driver:
        os.environ["SDL_VIDEODRIVER"] = args.driver
    if args.card is not None:
        os.environ["SDL_KMSDRM_DEVICE_INDEX"] = str(args.card)

    try:
        import pygame

        try:
            LOGGER.info("Python %s (%s), Pygame %s (%s), SDL %s",
                        sys.version.split()[0], sys.executable, pygame.version.ver,
                        pygame.__file__, pygame.get_sdl_version())
            log_environment()
            log_video_drivers(pygame)
            if sys.platform.startswith("linux"):
                log_linux_resources()
            if not args.report_only:
                show_test_image(pygame, args.seconds, args.windowed)
        finally:
            pygame.quit()
    except Exception:
        LOGGER.exception("Grafikdiagnose fehlgeschlagen.")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
