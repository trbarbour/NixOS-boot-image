from __future__ import annotations

import subprocess
from typing import List, Sequence

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
        return subprocess.CompletedProcess(cmd, self.returncodes[index])


@pytest.fixture
def empty_lsblk(monkeypatch) -> None:
    monkeypatch.setattr(storage_cleanup, "_list_block_devices", lambda: [])


@pytest.mark.parametrize(
    "action,expected",
    [
        (
            storage_cleanup.WIPE_SIGNATURES,
            [
                ("sgdisk", "--zap-all", "/dev/sda"),
                ("blockdev", "--rereadpt", "/dev/sda"),
                ("partprobe", "/dev/sda"),
                ("udevadm", "settle"),
                ("wipefs", "-a", "/dev/sda"),
            ],
        ),
        (
            storage_cleanup.DISCARD_BLOCKS,
            [
                ("sgdisk", "--zap-all", "/dev/sda"),
                ("blockdev", "--rereadpt", "/dev/sda"),
                ("partprobe", "/dev/sda"),
                ("udevadm", "settle"),
                ("blkdiscard", "--force", "/dev/sda"),
                ("wipefs", "-a", "/dev/sda"),
            ],
        ),
        (
            storage_cleanup.OVERWRITE_RANDOM,
            [
                ("sgdisk", "--zap-all", "/dev/sda"),
                ("blockdev", "--rereadpt", "/dev/sda"),
                ("partprobe", "/dev/sda"),
                ("udevadm", "settle"),
                ("shred", "-n", "1", "-vz", "/dev/sda"),
                ("wipefs", "-a", "/dev/sda"),
            ],
        ),
    ],
)
def test_perform_storage_cleanup_executes_expected_commands(
    action: str, expected: List[Sequence[str]], empty_lsblk
) -> None:
    runner = RecordingRunner()
    scheduled = storage_cleanup.perform_storage_cleanup(
        action,
        ["/dev/sda"],
        execute=True,
        runner=runner,
    )
    assert runner.commands == expected
    assert scheduled == [" ".join(cmd) for cmd in expected]


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


def test_cleanup_does_not_execute_when_disabled(empty_lsblk) -> None:
    runner = RecordingRunner()
    scheduled = storage_cleanup.perform_storage_cleanup(
        storage_cleanup.WIPE_SIGNATURES,
        ["/dev/sda"],
        execute=False,
        runner=runner,
    )
    assert runner.commands == []
    assert scheduled == [
        "sgdisk --zap-all /dev/sda",
        "blockdev --rereadpt /dev/sda",
        "partprobe /dev/sda",
        "udevadm settle",
        "wipefs -a /dev/sda",
    ]


def test_unknown_action_raises_value_error() -> None:
    runner = RecordingRunner()
    with pytest.raises(ValueError):
        storage_cleanup.perform_storage_cleanup(
            "unsupported", ["/dev/sda"], execute=True, runner=runner
        )


def test_sgdisk_exit_code_two_is_allowed(empty_lsblk) -> None:
    runner = SequenceRunner([2, 0, 0, 0, 0])
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
    assert scheduled == [
        "sgdisk --zap-all /dev/sda",
        "blockdev --rereadpt /dev/sda",
        "partprobe /dev/sda",
        "udevadm settle",
        "wipefs -a /dev/sda",
    ]


def test_partprobe_exit_code_one_is_allowed(empty_lsblk) -> None:
    runner = SequenceRunner([0, 0, 1, 0, 0, 0, 0, 0])
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
        ("blockdev", "--rereadpt", "/dev/sda"),
        ("partprobe", "/dev/sda"),
        ("udevadm", "settle"),
        ("wipefs", "-a", "/dev/sda"),
    ]
    assert scheduled == [
        "sgdisk --zap-all /dev/sda",
        "blockdev --rereadpt /dev/sda",
        "partprobe /dev/sda",
        "udevadm settle",
        "blockdev --rereadpt /dev/sda",
        "partprobe /dev/sda",
        "udevadm settle",
        "wipefs -a /dev/sda",
    ]


def test_nonzero_exit_code_for_other_commands_fails(empty_lsblk) -> None:
    runner = SequenceRunner([0, 0, 0, 0, 1])
    with pytest.raises(subprocess.CalledProcessError):
        storage_cleanup.perform_storage_cleanup(
            storage_cleanup.WIPE_SIGNATURES,
            ["/dev/sda"],
            execute=True,
            runner=runner,
        )


def test_wipefs_failure_logs_diagnostics(monkeypatch, empty_lsblk) -> None:
    runner = SequenceRunner([0, 0, 0, 0, 1])
    events: list[tuple[str, dict[str, object]]] = []

    def record_event(event: str, **fields: object) -> None:
        events.append((event, fields))

    monkeypatch.setattr("pre_nixos.storage_cleanup.log_event", record_event)
    monkeypatch.setattr(
        "pre_nixos.storage_cleanup._collect_wipefs_diagnostics",
        lambda device: {"mounts": ["/target /dev/sda1"], "boot_disk": device, "probes": []},
    )

    with pytest.raises(subprocess.CalledProcessError):
        storage_cleanup.perform_storage_cleanup(
            storage_cleanup.WIPE_SIGNATURES,
            ["/dev/sda"],
            execute=True,
            runner=runner,
        )

    failure_events = [event for event in events if event[0] == "pre_nixos.cleanup.wipefs_failed"]
    assert failure_events
    fields = failure_events[0][1]
    assert fields["device"] == "/dev/sda"
    assert fields["mounts"] == ["/target /dev/sda1"]


def test_teardown_unmounts_before_wiping(monkeypatch) -> None:
    runner = RecordingRunner()
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

    scheduled = storage_cleanup.perform_storage_cleanup(
        storage_cleanup.WIPE_SIGNATURES,
        ["/dev/sda"],
        execute=True,
        runner=runner,
    )

    assert runner.commands[0] == ("umount", "/target")
    assert scheduled[0] == "umount /target"
    assert scheduled[-1] == "wipefs -a /dev/sda"


def test_teardown_failure_skips_wipe(monkeypatch) -> None:
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
    runner = SequenceRunner([1])
    scheduled = storage_cleanup.perform_storage_cleanup(
        storage_cleanup.WIPE_SIGNATURES,
        ["/dev/sda"],
        execute=True,
        runner=runner,
    )

    assert scheduled == ["umount /target"]


def test_descendant_raid_metadata_is_wiped(monkeypatch) -> None:
    runner = RecordingRunner()
    monkeypatch.setattr(
        storage_cleanup,
        "_list_block_devices",
        lambda: [
            {
                "name": "/dev/sda",
                "type": "disk",
                "children": [
                    {"name": "/dev/sda1", "type": "part", "fstype": "linux_raid_member"}
                ],
            }
        ],
    )

    scheduled = storage_cleanup.perform_storage_cleanup(
        storage_cleanup.WIPE_SIGNATURES,
        ["/dev/sda"],
        execute=True,
        runner=runner,
    )

    assert scheduled[0] == "wipefs -a /dev/sda1"
    assert ("mdadm", "--zero-superblock", "--force", "/dev/sda1") in runner.commands


def test_recursive_descendant_metadata_is_wiped(monkeypatch) -> None:
    runner = RecordingRunner()
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
                        "fstype": "linux_raid_member",
                        "children": [
                            {
                                "name": "/dev/md0",
                                "type": "raid1",
                                "children": [
                                    {
                                        "name": "/dev/main-slash",
                                        "type": "lvm",
                                        "fstype": "ext4",
                                    }
                                ],
                            }
                        ],
                    }
                ],
            }
        ],
    )

    scheduled = storage_cleanup.perform_storage_cleanup(
        storage_cleanup.WIPE_SIGNATURES,
        ["/dev/sda"],
        execute=True,
        runner=runner,
    )

    wipefs_commands = [cmd for cmd in scheduled if cmd.startswith("wipefs")]
    descendant_wipes = [cmd for cmd in wipefs_commands if not cmd.endswith("/dev/sda")]
    assert descendant_wipes == [
        "wipefs -a /dev/main-slash",
        "wipefs -a /dev/md0",
        "wipefs -a /dev/sda1",
    ]
    assert ("mdadm", "--zero-superblock", "--force", "/dev/sda1") in runner.commands
    assert ("mdadm", "--zero-superblock", "--force", "/dev/md0") in runner.commands


def test_partition_refresh_failure_aborts_wipe(empty_lsblk) -> None:
    runner = SequenceRunner([0, 1, 1, 0, 1, 1, 0, 1, 1, 0])
    scheduled = storage_cleanup.perform_storage_cleanup(
        storage_cleanup.WIPE_SIGNATURES,
        ["/dev/sda"],
        execute=True,
        runner=runner,
    )

    assert scheduled == [
        "sgdisk --zap-all /dev/sda",
        "blockdev --rereadpt /dev/sda",
        "partprobe /dev/sda",
        "udevadm settle",
        "blockdev --rereadpt /dev/sda",
        "partprobe /dev/sda",
        "udevadm settle",
        "blockdev --rereadpt /dev/sda",
        "partprobe /dev/sda",
        "udevadm settle",
    ]
