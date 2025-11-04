from __future__ import annotations

from typing import List, Sequence

import pytest

from pre_nixos import storage_cleanup


class RecordingRunner:
    def __init__(self) -> None:
        self.commands: List[Sequence[str]] = []

    def __call__(self, cmd: Sequence[str]) -> None:
        self.commands.append(tuple(cmd))


@pytest.mark.parametrize(
    "action,expected",
    [
        (
            storage_cleanup.WIPE_SIGNATURES,
            [
                ("sgdisk", "--zap-all", "/dev/sda"),
                ("wipefs", "-a", "/dev/sda"),
            ],
        ),
        (
            storage_cleanup.DISCARD_BLOCKS,
            [
                ("sgdisk", "--zap-all", "/dev/sda"),
                ("blkdiscard", "--force", "/dev/sda"),
                ("wipefs", "-a", "/dev/sda"),
            ],
        ),
        (
            storage_cleanup.OVERWRITE_RANDOM,
            [
                ("sgdisk", "--zap-all", "/dev/sda"),
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
        "wipefs -a /dev/sda",
    ]


def test_unknown_action_raises_value_error() -> None:
    runner = RecordingRunner()
    with pytest.raises(ValueError):
        storage_cleanup.perform_storage_cleanup(
            "unsupported", ["/dev/sda"], execute=True, runner=runner
        )
