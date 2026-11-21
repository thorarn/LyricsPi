#!/usr/bin/env bash
set -Eeuo pipefail
umask 022

prefix=/opt/lyricspi
mountpoint=/media/lyricspi/USB
unit=/etc/systemd/system/lyricspi.service
usb_unit=/etc/systemd/system/lyricspi-usb.service
legacy_mount=/etc/systemd/system/media-lyricspi-USB.mount
policy=/etc/polkit-1/rules.d/49-lyricspi-poweroff.rules
system_files=("$unit" "$usb_unit" "$policy")
backup_files=("${system_files[@]}")
legacy_managed=0
source_dir=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd -P)

fail() {
    printf 'LyricsPi-Installation: %s\n' "$*" >&2
    exit 1
}

usage() {
    printf 'Aufruf: sudo bash deploy/install.sh\n'
    printf 'FAT32-/exFAT-USB-Sticks werden beim Dienststart automatisch erkannt.\n'
}

check_platform() {
    local model=$1 machine=$2 architecture=$3 bits=$4 release=$5
    local supported='^Raspberry[[:space:]]+Pi[[:space:]]+(2[[:space:]]+Model[[:space:]]+B|3[[:space:]]+Model[[:space:]]+(B\+?|A\+|A[[:space:]]+Plus))([[:space:]]|$)'
    [[ -n "${model//[[:space:]]/}" ]] ||
        fail "Keine Raspberry-Pi-Modellinformationen gefunden."
    [[ "$model" =~ $supported ]] ||
        fail "Nicht unterstütztes Modell: $model. Raspberry Pi 2 Model B oder Raspberry Pi 3 erwartet."
    case "$machine" in
        armv7*|armv8*|aarch64) ;;
        *) fail "ARMv7 oder neuer erforderlich (Kernelarchitektur: $machine)." ;;
    esac
    [[ "$architecture" == armhf && "$bits" == 32 ]] ||
        fail "Raspberry Pi OS Lite 32 Bit (armhf) erforderlich (gefunden: $architecture, $bits Bit)."
    case "$release" in
        trixie|bookworm) ;;
        *) fail "Raspberry Pi OS Lite auf Basis von Debian Trixie oder Bookworm erforderlich (gefunden: ${release:-unbekannt})." ;;
    esac
}

check_python_version() {
    local version=$1
    if [[ ! "$version" =~ ^3\.([0-9]+)(\.|$) ]] || (( 10#${BASH_REMATCH[1]} < 11 )); then
        fail "Python 3.11 oder neuer erforderlich (gefunden: $version)."
    fi
}

system_packages() {
    local font_package=fonts-dejavu-mono
    if [[ "$1" == bookworm ]]; then
        font_package=fonts-dejavu-core
    fi
    printf '%s\n' python3 python3-venv python3-pygame python3-setuptools \
        python3-wheel fontconfig "$font_package" kbd polkitd exfatprogs \
        util-linux mount udev \
        libdrm2 libgbm1 libegl1 libegl-mesa0 libgles2 libgl1-mesa-dri
}

missing_packages() {
    local package
    for package in "$@"; do
        if [[ $(dpkg-query -W -f='${db:Status-Status}' "$package" 2>/dev/null) != installed ]]; then
            printf '%s\n' "$package"
        fi
    done
}

deployment_matches() {
    local current=$1 staged=$2 target path
    shift 2
    for path in src assets demo_songs deploy/usb_mount.py tools/graphics_diagnostic.py config/config.example.json config/config.json README.md pyproject.toml; do
        diff -qr --exclude=__pycache__ --exclude='*.egg-info' \
            "$current/$path" "$staged/app/$path" >/dev/null 2>&1 || return 1
    done
    for target in "$@"; do
        cmp -s -- "$target" "$staged/${target##*/}" || return 1
    done
}

if [[ "${BASH_SOURCE[0]}" != "$0" ]]; then
    return
fi
trap 'printf "LyricsPi-Installation fehlgeschlagen in Zeile %s.\n" "$LINENO" >&2' ERR

case $# in
    0) ;;
    1) [[ $1 == --help || $1 == -h ]] || fail "Unbekannte Option: $1"
       usage; exit 0 ;;
    *) usage; exit 1 ;;
esac

[[ $(uname -s) == Linux ]] || fail "Linux erforderlich."
(( EUID == 0 )) || fail "Das Installationsskript mit sudo starten."
model=
if [[ -r /proc/device-tree/model ]]; then
    model=$(tr -d '\000' </proc/device-tree/model)
fi
machine=$(uname -m)
architecture=$(dpkg --print-architecture)
bits=$(getconf LONG_BIT)
[[ -r /etc/os-release ]] || fail "Betriebssysteminformationen fehlen (/etc/os-release)."
# shellcheck source=/dev/null
. /etc/os-release
release=${VERSION_CODENAME:-}
printf 'Modell: %s\nArchitektur: %s (Kernel %s, %s Bit)\nBetriebssystem: %s (%s)\n' \
    "${model:-unbekannt}" "$architecture" "$machine" "$bits" \
    "${PRETTY_NAME:-unbekannt}" "${release:-unbekannt}"
check_platform "$model" "$machine" "$architecture" "$bits" "$release"
[[ -d /run/systemd/system ]] || fail "systemd muss das laufende System verwalten."
exec 9>/run/lock/lyricspi-install.lock
flock -n 9 || fail "Eine LyricsPi-Installation läuft bereits."

for path in "$prefix" "${backup_files[@]}" "$prefix/config/config.json" /media/lyricspi "$mountpoint"; do
    [[ ! -L "$path" ]] || fail "Unerwarteter symbolischer Link: $path"
done
[[ ! -e "$prefix" || -d "$prefix" ]] || fail "$prefix ist kein Verzeichnis."
[[ "$source_dir" != "$prefix" && "$source_dir" != "$prefix/"* ]] ||
    fail "Das Skript aus einem separaten Git-Checkout ausführen."
[[ -f "$source_dir/pyproject.toml" ]] || fail "Projektdateien fehlen in $source_dir."
if [[ -f "$legacy_mount" && ! -L "$legacy_mount" ]] &&
    grep -qx '# Verwaltet durch LyricsPi deploy/install.sh' "$legacy_mount"; then
    backup_files+=("$legacy_mount")
    legacy_managed=1
fi
if findmnt --fstab --mountpoint "$mountpoint" >/dev/null; then
    printf 'Vorhandener fstab-Eintrag für %s bleibt erhalten.\n' "$mountpoint"
fi

mapfile -t packages < <(system_packages "$release")
mapfile -t missing < <(missing_packages "${packages[@]}")
if (( ${#missing[@]} )); then
    printf 'Fehlende Pakete: %s\n' "${missing[*]}"
    apt-get update || fail "APT-Paketlisten konnten nicht aktualisiert werden."
    apt-get install -y --no-install-recommends "${missing[@]}" ||
        fail "Benötigte Pakete konnten für $release/$architecture nicht installiert werden."
fi
python_version=$(/usr/bin/python3 -c 'import platform; print(platform.python_version())') ||
    fail "System-Python konnte nicht gestartet werden."
printf 'Python: %s\n' "$python_version"
check_python_version "$python_version"
if ! id lyricspi >/dev/null 2>&1; then
    useradd --system --user-group --home-dir "$prefix" --shell /usr/sbin/nologin lyricspi
fi
[[ $(id -gn lyricspi) == lyricspi ]] || fail "Benutzer lyricspi hat eine unerwartete primäre Gruppe."
account=$(getent passwd lyricspi)
[[ $(id -u lyricspi) != 0 && "$account" == *":$prefix:/usr/sbin/nologin" ]] ||
    fail "Benutzer lyricspi muss ein dediziertes Konto ohne Login sein."
for group in video render input; do
    getent group "$group" >/dev/null || fail "Erforderliche Gerätegruppe fehlt: $group."
done
if [[ ! -d "$mountpoint" ]]; then
    install -d -m 0755 /media/lyricspi "$mountpoint"
fi

stage=$(mktemp -d /opt/.lyricspi-stage.XXXXXXXX)
backup=
replacing=0
was_active=0
cleanup() {
    local status=$?
    trap - EXIT
    if (( status != 0 && replacing )); then
        printf 'Installation fehlgeschlagen. Stelle die vorherige Installation wieder her.\n' >&2
        set +e
        for path in "${backup_files[@]}"; do
            if [[ -f "$backup/${path##*/}" ]]; then
                cp -a -- "$backup/${path##*/}" "$path"
            else
                rm -f -- "$path"
            fi
        done
        if [[ ! -d "$stage/app" && -d "$prefix" ]]; then
            mv -T -- "$prefix" "$stage/app"
        fi
        if [[ -d "$backup/app" ]]; then
            mv -T -- "$backup/app" "$prefix"
        fi
        systemctl daemon-reload
        if (( was_active )); then
            systemctl start lyricspi.service
        fi
        printf 'Sicherungsverzeichnis: %s\n' "$backup" >&2
    fi
    rm -rf -- "$stage"
    exit "$status"
}
trap cleanup EXIT
trap 'exit 130' INT
trap 'exit 143' TERM

install -d -m 0755 "$stage/app" "$stage/app/config" "$stage/app/assets" "$stage/app/deploy" "$stage/app/tools"
cp -R -- "$source_dir"/{src,demo_songs} "$stage/app/"
if [[ -d "$source_dir/assets" ]]; then
    cp -R -- "$source_dir/assets/." "$stage/app/assets/"
fi
install -m 0644 "$source_dir/pyproject.toml" "$source_dir/README.md" "$stage/app/"
install -m 0644 "$source_dir/config/config.example.json" "$stage/app/config/"
install -m 0644 "$source_dir/deploy/usb_mount.py" "$stage/app/deploy/"
install -m 0644 "$source_dir/tools/graphics_diagnostic.py" "$stage/app/tools/"
local_config="$prefix/config/config.json"
if [[ -f "$local_config" ]]; then
    install -o root -g lyricspi -m 0640 "$local_config" "$stage/app/config/config.json"
else
    /usr/bin/python3 - "$stage/app/config" "$mountpoint" <<'PY'
import json
import sys
from pathlib import Path

config_dir = Path(sys.argv[1])
config = json.loads((config_dir / "config.example.json").read_text(encoding="utf-8"))
config["display"].update(fullscreen=True)
config["system"].update(development_mode=False, show_splash=True)
config["songs"].update(source_mode="usb", linux_mount_path=sys.argv[2])
(config_dir / "config.json").write_text(
    json.dumps(config, indent=2) + "\n", encoding="utf-8"
)
PY
    chown root:lyricspi "$stage/app/config/config.json"
    chmod 0640 "$stage/app/config/config.json"
fi

cat >"$stage/49-lyricspi-poweroff.rules" <<'POLKIT'
polkit.addRule(function(action, subject) {
    if (subject.user === "lyricspi" &&
        (action.id === "org.freedesktop.login1.power-off" ||
         action.id === "org.freedesktop.login1.power-off-multiple-sessions")) {
        return polkit.Result.YES;
    }
});
POLKIT

verify_installation() {
    runuser -u lyricspi -- env PYTHONDONTWRITEBYTECODE=1 PYGAME_HIDE_SUPPORT_PROMPT=1 \
        "$python" - "$prefix/config/config.json" <<'PY'
import ctypes
import ctypes.util
import sys
from pathlib import Path

import pygame
from lyricspi.config import load_config

if tuple(pygame.version.vernum) < (2, 1, 2):
    raise SystemExit(f"Pygame ab 2.1.2 erforderlich: {pygame.version.ver}")
if pygame.get_sdl_version()[0] != 2:
    raise SystemExit(f"SDL2 erforderlich: {pygame.get_sdl_version()}")

config = load_config(Path(sys.argv[1]))
if (
    not config.display.fullscreen
    or config.system.development_mode
    or not config.system.show_splash
    or config.songs.source_mode != "usb"
    or config.songs.linux_mount_path != "/media/lyricspi/USB"
):
    print("Lokale Konfiguration erhalten. Vollbild, Produktivmodus, Splash und USB-Pfad prüfen.")
library = ctypes.util.find_library("SDL2-2.0")
if not library:
    raise SystemExit("SDL2-Systembibliothek nicht gefunden.")
sdl = ctypes.CDLL(library)
sdl.SDL_GetVideoDriver.argtypes = [ctypes.c_int]
sdl.SDL_GetVideoDriver.restype = ctypes.c_char_p
drivers = [
    sdl.SDL_GetVideoDriver(index).decode("ascii").lower()
    for index in range(sdl.SDL_GetNumVideoDrivers())
]
if "kmsdrm" not in drivers:
    raise SystemExit(f"Die installierte SDL2-Bibliothek unterstützt kein KMSDRM: {drivers}")
for soname in ("libEGL.so.1", "libEGL_mesa.so.0", "libGLESv2.so.2", "libgbm.so.1", "libdrm.so.2"):
    try:
        ctypes.CDLL(soname)
    except OSError as error:
        raise SystemExit(f"KMSDRM-Systembibliothek nicht ladbar: {soname}: {error}") from error
print(f"Pygame {pygame.version.ver}, SDL {pygame.get_sdl_version()}, KMSDRM- und EGL-Bibliotheken vorhanden.")
PY
}

python="$prefix/.venv/bin/python"
install -m 0644 "$source_dir"/deploy/{lyricspi,lyricspi-usb}.service "$stage/"
if [[ -x "$python" ]] && (( ! legacy_managed )) &&
    deployment_matches "$prefix" "$stage" "${system_files[@]}" &&
    verify_installation; then
    if ! systemctl is-enabled --quiet lyricspi.service; then
        systemctl enable lyricspi.service
    fi
    printf 'LyricsPi ist bereits aktuell. Installation und laufender Dienst bleiben erhalten.\n'
    exit 0
fi

backup=$(mktemp -d /opt/.lyricspi-backup.XXXXXXXX)
for path in "${backup_files[@]}"; do
    if [[ -e "$path" ]]; then
        cp -a -- "$path" "$backup/"
    fi
done
if systemctl is-active --quiet lyricspi.service; then
    was_active=1
    systemctl stop lyricspi.service
fi
replacing=1
if (( legacy_managed )); then
    systemctl stop "${legacy_mount##*/}"
    rm -- "$legacy_mount"
fi
if [[ -d "$prefix" ]]; then
    mv -T -- "$prefix" "$backup/app"
fi
mv -T -- "$stage/app" "$prefix"
/usr/bin/python3 -m venv --system-site-packages "$prefix/.venv" ||
    fail "Die Python-venv konnte nicht erstellt werden."
"$python" -m pip --disable-pip-version-check install --no-index --no-build-isolation \
    --no-deps -e "$prefix" || fail "LyricsPi konnte nicht in der Python-venv installiert werden."
verify_installation || fail "Die Installation hat die Python-/Pygame-/SDL2-Prüfung nicht bestanden."
install -m 0644 "$stage/lyricspi.service" "$unit"
install -m 0644 "$stage/lyricspi-usb.service" "$usb_unit"
install -m 0644 "$stage/49-lyricspi-poweroff.rules" "$policy"
systemd-analyze verify "$unit" "$usb_unit"
systemctl daemon-reload
systemctl enable lyricspi.service
replacing=0

printf 'Installation abgeschlossen. Sicherung: %s\n' "$backup"
printf 'Dienst starten: sudo systemctl start lyricspi.service\n'
printf 'Journal verfolgen: journalctl -u lyricspi.service -u lyricspi-usb.service -f\n'
