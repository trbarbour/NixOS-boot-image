from typing import List, Sequence
import subprocess

import pytest

from pre_nixos import storage_cleanup


class RecordingRunner:
    def __init__(self) -> None:
        self.commands: List[Sequence[str]] = []

    def __call__(self, cmd: Sequence[str]) -> subprocess.CompletedProcess:
        self.commands.append(tuple(cmd))
        return subprocess.CompletedProcess(cmd, 0)


class SequenceRunner:
    def __init__(self, returncodes: Sequence[int]) -> None:
        self.returncodes = list(returncodes)
        self.commands: List[Sequence[str]] = []

    def __call__(self, cmd: Sequence[str]) -> subprocess.CompletedProcess:
        self.commands.append(tuple(cmd))
        index = len(self.commands) - 1
        code = self.returncodes[index] if index < len(self.returncodes) else 0
        return subprocess.CompletedProcess(cmd, code)


@pytest.fixture(autouse=True)
def patch_probes(monkeypatch) -> None:
    monkeypatch.setattr(storage_cleanup, "_list_block_devices", lambda: [])
    monkeypatch.setattr(storage_cleanup, "_list_pvs", lambda: [])
    monkeypatch.setattr(storage_cleanup, "_list_vgs", lambda: [])
    monkeypatch.setattr(storage_cleanup, "_list_lvs", lambda: [])
    monkeypatch.setattr(storage_cleanup, "_list_losetup", lambda: [])


def test_basic_root_cleanup_commands() -> None:
    runner = RecordingRunner()

    scheduled = storage_cleanup.perform_storage_cleanup(
        storage_cleanup.WIPE_SIGNATURES,
        ["/dev/sda"],
        execute=True,
        runner=runner,
    )

    assert runner.commands == [
        ("sgdisk", "--zap-all", "/dev/sda"),
        ("blockdev", "--rereadpt", "/dev/sda"),
        ("partprobe", "/dev/sda"),
        ("udevadm", "settle"),
        ("wipefs", "-a", "/dev/sda"),
    ]
    assert scheduled == [" ".join(cmd) for cmd in runner.commands]


def test_global_teardown_and_wipe_leaf_to_root(monkeypatch) -> None:
    def fake_lsblk() -> list[dict[str, object]]:
        return [
            {
                "name": "/dev/sda",
                "type": "disk",
                "children": [
                    {
                        "name": "/dev/sda1",
                        "type": "part",
                        "fstype": "linux_raid_member",
                        "children": [
                            {
                                "name": "/dev/md0",
                                "type": "raid1",
                                "children": [
                                    {
                                        "name": "/dev/main/slash",
                                        "type": "lvm",
                                        "fstype": "ext4",
                                        "mountpoint": "/target",
                                    }
                                ],
                            }
                        ],
                    }
                ],
            },
            {
                "name": "/dev/sdb",
                "type": "disk",
                "children": [
                    {
                        "name": "/dev/sdb1",
                        "type": "part",
                        "fstype": "linux_raid_member",
                        "children": [
                            {
                                "name": "/dev/md0",
                                "type": "raid1",
                            }
                        ],
                    }
                ],
            },
        ]

    monkeypatch.setattr(storage_cleanup, "_list_block_devices", fake_lsblk)
    monkeypatch.setattr(
        storage_cleanup,
        "_list_pvs",
        lambda: [{"pv_name": "/dev/md0", "vg_name": "main"}],
    )
    monkeypatch.setattr(storage_cleanup, "_list_vgs", lambda: [{"vg_name": "main"}])
    monkeypatch.setattr(
        storage_cleanup,
        "_list_lvs",
        lambda: [{"lv_path": "/dev/main/slash", "vg_name": "main"}],
    )

    runner = RecordingRunner()

    scheduled = storage_cleanup.perform_storage_cleanup(
        storage_cleanup.WIPE_SIGNATURES,
        ["/dev/sda", "/dev/sdb"],
        execute=True,
        runner=runner,
    )

    expected = [
        ("umount", "/target"),
        ("lvchange", "-an", "/dev/main/slash"),
        ("vgchange", "-an", "main"),
        ("mdadm", "--stop", "/dev/md0"),
        ("mdadm", "--stop", "/dev/sda1"),
        ("mdadm", "--stop", "/dev/sdb1"),
        ("wipefs", "-a", "/dev/main/slash"),
        ("lvremove", "-fy", "/dev/main/slash"),
        ("vgremove", "-ff", "-y", "main"),
        ("pvremove", "-ff", "-y", "/dev/md0"),
        ("mdadm", "--zero-superblock", "--force", "/dev/md0"),
        ("wipefs", "-a", "/dev/md0"),
        ("mdadm", "--zero-superblock", "--force", "/dev/sda1"),
        ("wipefs", "-a", "/dev/sda1"),
        ("mdadm", "--zero-superblock", "--force", "/dev/sdb1"),
        ("wipefs", "-a", "/dev/sdb1"),
        ("sgdisk", "--zap-all", "/dev/sda"),
        ("blockdev", "--rereadpt", "/dev/sda"),
        ("partprobe", "/dev/sda"),
        ("udevadm", "settle"),
        ("wipefs", "-a", "/dev/sda"),
        ("sgdisk", "--zap-all", "/dev/sdb"),
        ("blockdev", "--rereadpt", "/dev/sdb"),
        ("partprobe", "/dev/sdb"),
        ("udevadm", "settle"),
        ("wipefs", "-a", "/dev/sdb"),
    ]

    assert runner.commands == expected
    assert scheduled == [" ".join(cmd) for cmd in expected]


def test_refresh_partition_table_logs_diagnostics(monkeypatch) -> None:
    events: list[tuple[str, dict[str, object]]] = []

    def record_event(event: str, **fields: object) -> None:
        events.append((event, fields))

    def fake_execute_command(
        cmd: Sequence[str],
        *,
        action: str,
        device: str,
        execute: bool,
        runner,
        scheduled: list[str],
        tolerate_failure: bool = False,
    ) -> subprocess.CompletedProcess:
        return subprocess.CompletedProcess(cmd, 1)

    monkeypatch.setattr(storage_cleanup, "log_event", record_event)
    monkeypatch.setattr(storage_cleanup, "_execute_command", fake_execute_command)
    monkeypatch.setattr(
        storage_cleanup.storage_detection,
        "collect_boot_probe_data",
        lambda: {"boot_probe": {"ok": True}},
    )
    monkeypatch.setattr(
        storage_cleanup,
        "_collect_storage_stack_state",
        lambda: {"stack": "state"},
    )
    monkeypatch.setattr(storage_cleanup.time, "sleep", lambda *_args, **_kwargs: None)

    result = storage_cleanup._refresh_partition_table(
        storage_cleanup.WIPE_SIGNATURES,
        "/dev/test",
        execute=True,
        runner=lambda cmd: subprocess.CompletedProcess(cmd, 1),
        scheduled=[],
        attempts=1,
    )

    assert result is False
    assert events and events[0][0] == "pre_nixos.cleanup.partition_refresh_failed"
    fields = events[0][1]
    assert fields["device"] == "/dev/test"
    assert fields["boot_probe"] == {"ok": True}
    assert fields["stack"] == "state"


def test_teardown_failure_keeps_wiping(monkeypatch) -> None:
    monkeypatch.setattr(
        storage_cleanup,
        "_list_block_devices",
        lambda: [
            {
                "name": "/dev/sda",
                "type": "disk",
                "children": [
                    {
                        "name": "/dev/sda1",
                        "type": "part",
                        "mountpoint": "/target",
                        "fstype": "ext4",
                    }
                ],
            }
        ],
    )

    runner = SequenceRunner([1] + [0] * 10)
    scheduled = storage_cleanup.perform_storage_cleanup(
        storage_cleanup.WIPE_SIGNATURES,
        ["/dev/sda"],
        execute=True,
        runner=runner,
    )

    assert any(cmd.startswith("wipefs -a /dev/sda1") for cmd in scheduled)
    assert scheduled[-1] == "wipefs -a /dev/sda"


def test_skip_cleanup_records_no_commands() -> None:
    runner = RecordingRunner()
    scheduled = storage_cleanup.perform_storage_cleanup(
        storage_cleanup.SKIP_CLEANUP,
        ["/dev/sda"],
        execute=True,
        runner=runner,
    )
    assert runner.commands == []
    assert scheduled == []


def test_unknown_action_raises_value_error() -> None:
    runner = RecordingRunner()
    with pytest.raises(ValueError):
        storage_cleanup.perform_storage_cleanup(
            "unsupported", ["/dev/sda"], execute=True, runner=runner
        )
