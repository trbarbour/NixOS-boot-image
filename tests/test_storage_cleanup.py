from __future__ import annotations

import subprocess
from typing import List, Sequence

import pytest

from pre_nixos import storage_cleanup


class RecordingRunner:
    def __init__(self) -> None:
        self.commands: List[Sequence[str]] = []

    def __call__(self, cmd: Sequence[str]) -> None:
        self.commands.append(tuple(cmd))


class SequenceRunner:
    def __init__(self, returncodes: Sequence[int]) -> None:
        self.returncodes = list(returncodes)
        self.commands: List[Sequence[str]] = []

    def __call__(self, cmd: Sequence[str]) -> subprocess.CompletedProcess:
        self.commands.append(tuple(cmd))
        index = len(self.commands) - 1
        return subprocess.CompletedProcess(cmd, self.returncodes[index])


@pytest.mark.parametrize(
    "action,expected",
    [
        (
            storage_cleanup.WIPE_SIGNATURES,
            [
                ("sgdisk", "--zap-all", "/dev/sda"),
                ("partprobe", "/dev/sda"),
                ("wipefs", "-a", "/dev/sda"),
            ],
        ),
        (
            storage_cleanup.DISCARD_BLOCKS,
            [
                ("sgdisk", "--zap-all", "/dev/sda"),
                ("partprobe", "/dev/sda"),
                ("blkdiscard", "--force", "/dev/sda"),
                ("wipefs", "-a", "/dev/sda"),
            ],
        ),
        (
            storage_cleanup.OVERWRITE_RANDOM,
            [
                ("sgdisk", "--zap-all", "/dev/sda"),
                ("partprobe", "/dev/sda"),
                ("shred", "-n", "1", "-vz", "/dev/sda"),
                ("wipefs", "-a", "/dev/sda"),
            ],
        ),
    ],
)
def test_perform_storage_cleanup_executes_expected_commands(
    action: str, expected: List[Sequence[str]]
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


def test_cleanup_does_not_execute_when_disabled() -> None:
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
        "partprobe /dev/sda",
        "wipefs -a /dev/sda",
    ]


def test_unknown_action_raises_value_error() -> None:
    runner = RecordingRunner()
    with pytest.raises(ValueError):
        storage_cleanup.perform_storage_cleanup(
            "unsupported", ["/dev/sda"], execute=True, runner=runner
        )


def test_sgdisk_exit_code_two_is_allowed() -> None:
    runner = SequenceRunner([2, 0, 0])
    scheduled = storage_cleanup.perform_storage_cleanup(
        storage_cleanup.WIPE_SIGNATURES,
        ["/dev/sda"],
        execute=True,
        runner=runner,
    )
    assert runner.commands == [
        ("sgdisk", "--zap-all", "/dev/sda"),
        ("partprobe", "/dev/sda"),
        ("wipefs", "-a", "/dev/sda"),
    ]
    assert scheduled == [
        "sgdisk --zap-all /dev/sda",
        "partprobe /dev/sda",
        "wipefs -a /dev/sda",
    ]


def test_partprobe_exit_code_one_is_allowed() -> None:
    runner = SequenceRunner([0, 1, 0])
    scheduled = storage_cleanup.perform_storage_cleanup(
        storage_cleanup.WIPE_SIGNATURES,
        ["/dev/sda"],
        execute=True,
        runner=runner,
    )
    assert runner.commands == [
        ("sgdisk", "--zap-all", "/dev/sda"),
        ("partprobe", "/dev/sda"),
        ("wipefs", "-a", "/dev/sda"),
    ]
    assert scheduled == [
        "sgdisk --zap-all /dev/sda",
        "partprobe /dev/sda",
        "wipefs -a /dev/sda",
    ]


def test_nonzero_exit_code_for_other_commands_fails() -> None:
    runner = SequenceRunner([0, 0, 1])
    with pytest.raises(subprocess.CalledProcessError):
        storage_cleanup.perform_storage_cleanup(
            storage_cleanup.WIPE_SIGNATURES,
            ["/dev/sda"],
            execute=True,
            runner=runner,
        )


def test_wipefs_failure_logs_diagnostics(monkeypatch) -> None:
    runner = SequenceRunner([0, 0, 1])
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
