import json
import subprocess
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from deploy import usb_mount as usb
from lyricspi.config import Config, SongsConfig
from lyricspi.main import _managed_usb_config


TARGET = str(usb.TARGET)


def disk(name="/dev/sdb", transport="usb", partitions=None, number="8:16"):
    return {
        "name": name, "type": "disk", "tran": transport, "fstype": None,
        "maj:min": number, "children": partitions or [],
    }


def partition(name="/dev/sdb1", filesystem="vfat", number="8:17"):
    return {
        "name": name, "type": "part", "tran": None, "fstype": filesystem,
        "maj:min": number,
    }


def mounted(target=TARGET, readonly=True, filesystem="vfat", number="8:17"):
    return usb.Mount("41", number, "/", target, readonly, filesystem)


def mock_system(monkeypatch, tmp_path, disks, mounts, *, mount_error=None):
    monkeypatch.setattr(usb, "RUNTIME", tmp_path)
    monkeypatch.setattr(usb, "device_is_valid", lambda device: True)
    monkeypatch.setattr(usb, "protected_target", lambda: True)
    monkeypatch.setattr(usb, "is_sd_reader", lambda name: False)
    monkeypatch.setattr(usb, "read_mounts", lambda: mounts.copy())
    monkeypatch.setattr(usb, "time", SimpleNamespace(monotonic=Mock(side_effect=[0, 3, 3])))

    def command(program, *args, **kwargs):
        if program == "lsblk":
            return json.dumps({"blockdevices": disks})
        if program == "mount":
            if mount_error:
                raise mount_error
            mounts.append(mounted(filesystem=args[3]))
        return ""

    runner = Mock(side_effect=command)
    monkeypatch.setattr(usb, "command", runner)
    return runner


@pytest.mark.parametrize("filesystem", ["vfat", "exfat"])
def test_reads_and_mounts_usb_filesystem(monkeypatch, tmp_path, filesystem):
    nodes = [disk(partitions=[partition(filesystem=filesystem)])]
    mounts = []
    runner = mock_system(monkeypatch, tmp_path, nodes, mounts)
    usb.prepare()
    runner.assert_any_call(
        "mount", "-i", "-n", "-t", filesystem,
        "-o", "ro,nosuid,nodev,noexec,umask=0222", "--",
        "/dev/sdb1", TARGET, timeout=5,
    )
    assert (tmp_path / "ready.env").read_text() == "LYRICSPI_USB_READY=1\n"
    usb.release()
    runner.assert_any_call("umount", "-i", "-n", "--", TARGET)


def test_first_eligible_partition_and_disk_are_deterministic():
    nodes = [
        disk("/dev/sdc", partitions=[partition("/dev/sdc1", number="8:33")], number="8:32"),
        disk(partitions=[
            partition("/dev/sdb10", "exfat", "8:26"),
            partition("/dev/sdb2", "vfat", "8:18"),
            partition("/dev/sdb1", "ext4", "8:17"),
        ]),
    ]
    assert [item.path for item in usb.candidates(nodes, [])] == [
        "/dev/sdb2", "/dev/sdb10", "/dev/sdc1"
    ]


def test_whole_usb_disk_without_partitions_can_be_used():
    node = disk()
    node["fstype"] = "exfat"
    assert usb.candidates([node], []) == [
        usb.Device("/dev/sdb", "/dev/sdb", "8:16", "exfat")
    ]


def test_untrusted_device_names_do_not_become_mount_arguments():
    node = disk(partitions=[
        partition("/dev/sdc1"),
        partition("/dev/sdb1;touch /tmp/not-a-device"),
    ])
    assert usb.candidates([node], []) == []


def test_device_validation_rejects_regular_files(tmp_path):
    path = tmp_path / "sdb1"
    path.touch()
    assert not usb.device_is_valid(usb.Device(str(path), "/dev/sdb", "8:17", "vfat"))


@pytest.mark.parametrize("disks,mounts", [
    ([], []),
    ([disk(partitions=[partition(filesystem="ext4")])], []),
    ([disk("/dev/mmcblk0", "mmc", [partition("/dev/mmcblk0p1", number="179:1")], "179:0")], []),
    ([disk(partitions=[partition(), partition("/dev/sdb2", "ext4", "8:18")])],
     [mounted("/", False, "ext4", "8:18")]),
])
def test_missing_or_ineligible_devices_are_not_mounted(monkeypatch, tmp_path, disks, mounts):
    runner = mock_system(monkeypatch, tmp_path, disks, mounts)
    usb.prepare()
    assert [call.args[0] for call in runner.call_args_list] == ["lsblk"]
    assert not (tmp_path / "ready.env").exists()


def test_card_reader_reported_by_udev_is_ignored(monkeypatch, tmp_path):
    runner = mock_system(monkeypatch, tmp_path, [disk(partitions=[partition()])], [])
    monkeypatch.setattr(usb, "is_sd_reader", lambda name: True)
    usb.prepare()
    assert not (tmp_path / "ready.env").exists()
    runner.assert_called_once()


@pytest.mark.parametrize("mount,ready", [
    (mounted(), True),
    (mounted(readonly=False), False),
    (mounted("/media/other"), False),
    (mounted(filesystem="ext4", number="8:33"), False),
])
def test_existing_mounts_are_left_untouched(monkeypatch, tmp_path, mount, ready):
    runner = mock_system(monkeypatch, tmp_path, [disk(partitions=[partition()])], [mount])
    usb.prepare()
    assert (tmp_path / "ready.env").exists() == ready
    usb.release()
    assert (tmp_path / "owned").exists() is False
    assert [call.args[0] for call in runner.call_args_list] == ["lsblk"]


def test_mount_failure_leaves_no_ready_status(monkeypatch, tmp_path, caplog):
    error = subprocess.CalledProcessError(32, "mount", stderr="bad filesystem")
    runner = mock_system(
        monkeypatch, tmp_path, [disk(partitions=[partition()])], [], mount_error=error
    )
    monkeypatch.setattr(usb.sys, "argv", ["usb_mount.py", "start"])
    assert usb.main() == 1
    assert "bad filesystem" in caplog.text
    assert [call.args[0] for call in runner.call_args_list] == ["lsblk", "mount"]
    assert not (tmp_path / "ready.env").exists()


def test_release_does_not_unmount_replaced_mount(monkeypatch, tmp_path):
    mounts = [usb.Mount("42", "8:17", "/", TARGET, True, "vfat")]
    runner = mock_system(monkeypatch, tmp_path, [], mounts)
    (tmp_path / "owned").write_text("41 8:17\n", encoding="ascii")
    usb.release()
    runner.assert_not_called()


def test_mountinfo_requires_readonly_superblock(monkeypatch, tmp_path):
    info = tmp_path / "mountinfo"
    info.write_text(
        f"41 1 8:17 / {TARGET} ro,nosuid - vfat /dev/sdb1 rw\n"
        f"42 1 8:18 / {TARGET} ro,nosuid - exfat /dev/sdb2 ro\n",
        encoding="ascii",
    )
    monkeypatch.setattr(usb, "MOUNTINFO", info)
    assert [mount.readonly for mount in usb.read_mounts()] == [False, True]


def test_unconfirmed_managed_mount_disables_usb_source(monkeypatch):
    monkeypatch.setenv("LYRICSPI_USB_MOUNTPOINT", TARGET)
    monkeypatch.setenv("LYRICSPI_USB_READY", "0")
    config = Config(songs=SongsConfig(source_mode="usb", linux_mount_path="untrusted"))
    assert _managed_usb_config(config).songs.mount_path is None
    monkeypatch.setenv("LYRICSPI_USB_READY", "1")
    assert _managed_usb_config(config).songs.linux_mount_path == TARGET
    assert _managed_usb_config(Config()) == Config()
