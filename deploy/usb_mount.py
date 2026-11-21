"""Find and mount a song stick for the Linux system service."""

import json
import logging
import os
import re
import stat
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path


LOGGER = logging.getLogger(__name__)
TARGET = Path("/media/lyricspi/USB")
RUNTIME = Path("/run/lyricspi-usb")
MOUNTINFO = Path("/proc/self/mountinfo")
FILESYSTEMS = {"vfat", "exfat"}
DEVICE_NAME = re.compile(r"/dev/sd[a-z]+([0-9]+)?")
OPTIONS = "ro,nosuid,nodev,noexec,umask=0222"


@dataclass(frozen=True)
class Device:
    path: str
    disk: str
    number: str
    filesystem: str


@dataclass(frozen=True)
class Mount:
    identifier: str
    number: str
    root: str
    target: str
    readonly: bool
    filesystem: str


def read_mounts() -> list[Mount]:
    mounts = []
    for line in MOUNTINFO.read_text(encoding="utf-8", errors="replace").splitlines():
        left, right = line.split(" - ", 1)
        identifier, _, number, root, target, options, *_ = left.split()
        filesystem, _, super_options = right.split(maxsplit=2)
        readonly = "ro" in options.split(",") and "ro" in super_options.split(",")
        mounts.append(Mount(identifier, number, root, target, readonly, filesystem))
    return mounts


def descendants(node: dict) -> set[str]:
    return {node["maj:min"]}.union(
        *(descendants(child) for child in node.get("children", []))
    )


def has_swap(node: dict) -> bool:
    return "[SWAP]" in (node.get("mountpoints") or []) or any(
        has_swap(child) for child in node.get("children", [])
    )


def candidates(disks: list[dict], mounts: list[Mount]) -> list[Device]:
    system_targets = {"/", "/boot", "/boot/firmware", "/usr", "/var", "/home", "/opt"}
    system_devices = {entry.number for entry in mounts if entry.target in system_targets}
    devices = []
    for disk in sorted(disks, key=lambda node: node["name"]):
        disk_name = disk["name"]
        match = DEVICE_NAME.fullmatch(disk_name)
        if (
            disk["type"] != "disk" or disk["tran"] != "usb"
            or match is None or match[1] is not None
            or descendants(disk) & system_devices or has_swap(disk)
        ):
            continue
        partitions = [
            node for node in disk.get("children", []) if node["type"] == "part"
        ]
        for node in sorted(partitions or [disk], key=lambda entry: tuple(
            int(part) for part in entry["maj:min"].split(":")
        )):
            name = node["name"]
            if node["fstype"] not in FILESYSTEMS or (
                node is not disk and not re.fullmatch(re.escape(disk_name) + r"[0-9]+", name)
            ):
                continue
            devices.append(Device(name, disk_name, node["maj:min"], node["fstype"]))
    return devices


def command(*args: str, timeout: float = 3) -> str:
    return subprocess.run(
        args, check=True, capture_output=True, encoding="utf-8",
        errors="replace", timeout=timeout,
    ).stdout


def device_is_valid(device: Device) -> bool:
    try:
        info = Path(device.path).lstat()
    except FileNotFoundError:
        return False
    return (
        stat.S_ISBLK(info.st_mode)
        and device.number == f"{os.major(info.st_rdev)}:{os.minor(info.st_rdev)}"
    )


def is_sd_reader(disk: str) -> bool:
    properties = command("udevadm", "info", "--query=property", "--name", disk)
    return bool(
        {"ID_DRIVE_FLASH_SD=1", "ID_DRIVE_MEDIA_FLASH_SD=1"}
        & set(properties.splitlines())
    )


def usable_mount(mount: Mount, device: Device) -> bool:
    return (
        mount.number == device.number and mount.root == "/"
        and mount.readonly and mount.filesystem == device.filesystem
    )


def protected_target() -> bool:
    for path in (TARGET.parent, TARGET):
        info = path.lstat()
        if not stat.S_ISDIR(info.st_mode) or info.st_uid != 0 or info.st_mode & 0o022:
            return False
    return True


def prepare() -> None:
    (RUNTIME / "ready.env").unlink(missing_ok=True)
    deadline = time.monotonic() + 3
    while True:
        mounts = read_mounts()
        disks = json.loads(command(
            "lsblk", "--json", "--paths", "--tree",
            "--output", "NAME,TYPE,TRAN,FSTYPE,MAJ:MIN,MOUNTPOINTS",
        ))["blockdevices"]
        available = candidates(disks, mounts)
        if available or time.monotonic() >= deadline:
            break
        time.sleep(0.25)

    mounted_here = [entry for entry in mounts if entry.target == str(TARGET)]
    for device in available:
        if not device_is_valid(device) or is_sd_reader(device.disk):
            continue
        other_mounts = [
            entry for entry in mounts
            if entry.number == device.number and entry.target != str(TARGET)
        ]
        if other_mounts:
            LOGGER.warning("%s ist bereits anderweitig eingehängt.", device.path)
            continue
        if mounted_here:
            if len(mounted_here) == 1 and usable_mount(mounted_here[0], device):
                LOGGER.info("Verwende vorhandenen schreibgeschützten USB-Mount.")
                (RUNTIME / "ready.env").write_text("LYRICSPI_USB_READY=1\n", encoding="ascii")
                return
            continue
        if not protected_target():
            raise ValueError(f"Unsicherer Mountpunkt: {TARGET}")

        # Recheck the current mounts and the block node before invoking mount.
        if any(entry.target == str(TARGET) or entry.number == device.number
               for entry in read_mounts()) or not device_is_valid(device):
            LOGGER.warning("USB-Gerät oder Mountpunkt hat sich geändert.")
            return
        command("mount", "-i", "-n", "-t", device.filesystem,
                "-o", OPTIONS, "--", device.path, str(TARGET), timeout=5)
        mounted_here = [entry for entry in read_mounts() if entry.target == str(TARGET)]
        if len(mounted_here) != 1 or not usable_mount(mounted_here[0], device):
            raise ValueError("Der neue USB-Mount konnte nicht bestätigt werden.")
        (RUNTIME / "owned").write_text(
            f"{mounted_here[0].identifier} {device.number}\n", encoding="ascii"
        )
        (RUNTIME / "ready.env").write_text("LYRICSPI_USB_READY=1\n", encoding="ascii")
        LOGGER.info("%s (%s) schreibgeschützt eingehängt.", device.path, device.filesystem)
        return
    if mounted_here:
        LOGGER.warning("Mountpunkt %s belegt. Vorhandener Mount bleibt unberührt.", TARGET)
    else:
        LOGGER.info("Kein geeigneter USB-Stick gefunden.")


def release() -> None:
    (RUNTIME / "ready.env").unlink(missing_ok=True)
    ownership = RUNTIME / "owned"
    if not ownership.is_file():
        return
    identifier, number = ownership.read_text(encoding="ascii").split()
    mounted_here = [entry for entry in read_mounts() if entry.target == str(TARGET)]
    if not mounted_here:
        return
    if len(mounted_here) == 1 and (
        mounted_here[0].identifier, mounted_here[0].number
    ) == (identifier, number):
        command("umount", "-i", "-n", "--", str(TARGET))
        LOGGER.info("LyricsPi-USB-Mount ausgehängt.")


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    try:
        if sys.argv[1:] == ["start"]:
            prepare()
        elif sys.argv[1:] == ["stop"]:
            release()
        else:
            return 2
    except (OSError, ValueError, KeyError, subprocess.SubprocessError) as error:
        LOGGER.error("USB-Mount fehlgeschlagen: %s", error)
        if isinstance(error, subprocess.CalledProcessError) and error.stderr:
            LOGGER.error("%s", error.stderr.strip())
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
