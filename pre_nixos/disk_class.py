"""Whether a disk is planned as an SSD or an HDD (reqs R-S3, R-S4).

Design: plans/2026-11-07T161535Z-ssd-model-name-design.md (task queue item 34).

The kernel's ``queue/rotational`` (``Disk.rotational``) is the default.  Some
SSDs report no rotation rate, and the kernel then calls them rotational (the
user's ``G.SKILL 128GB SSD``).  Such a disk, one whose model name says "SSD",
has an *unconfirmed* class: no unattended run plans it (R-S3).  The user
answers per disk, in the TUI or with ``pre-nixos --ssd``/``--hdd``; the user may
also set any other disk's class (R-S4).  The answers are applied to the
inventory before planning, so the planner itself is unchanged.
"""

from __future__ import annotations

import dataclasses
import enum
from typing import Any, Dict, Iterable, List, Mapping, Sequence

from .inventory import Disk


class DiskClass(enum.Enum):
    SSD = "ssd"
    HDD = "hdd"

    @property
    def label(self) -> str:
        return self.value.upper()


Answers = Mapping[str, DiskClass]

# Where the plan records the user's answers, for the log and the saved plan.
PLAN_KEY = "disk_classes"
# auto-install-status REASON and storage-status DETAIL for a refused run.
UNCONFIRMED_REASON = "disk-class-unconfirmed"


def current_class(disk: Disk) -> DiskClass:
    """The class ``disk`` is planned as: the kernel's ``rotational`` report,
    or the user's answer once :func:`apply_classes` has applied it."""

    return DiskClass.HDD if disk.rotational else DiskClass.SSD


def name_suggests_ssd(model: str) -> bool:
    """D1 (a): "ssd" anywhere in the model, ignoring case.

    Catches ``Samsung SSD 850 EVO`` and Intel's ``INTEL SSDSC2BB120G4``; a
    hybrid drive's "SSHD" does not match.
    """

    return "ssd" in model.lower()


def is_ambiguous(disk: Disk) -> bool:
    """The kernel says rotating, but the model name says SSD (R-S3)."""

    return not disk.nvme and disk.rotational and name_suggests_ssd(disk.model)


def unconfirmed(disks: Iterable[Disk], answers: Answers) -> List[Disk]:
    """The ambiguous disks the user has not answered for."""

    return [disk for disk in disks if is_ambiguous(disk) and disk.name not in answers]


def disk_name(device: str) -> str:
    """``/dev/sda`` or ``sda`` → ``sda``."""

    name = device.strip()
    return name[len("/dev/") :] if name.startswith("/dev/") else name


def parse_answers(ssd: Sequence[str], hdd: Sequence[str]) -> Dict[str, DiskClass]:
    """The answers given as ``--ssd``/``--hdd`` options.

    Raises ``ValueError`` when a disk is named as both.
    """

    answers: Dict[str, DiskClass] = {}
    for devices, cls in ((ssd, DiskClass.SSD), (hdd, DiskClass.HDD)):
        for device in devices:
            name = disk_name(device)
            if not name:
                raise ValueError("an empty disk name was given")
            if answers.get(name, cls) is not cls:
                raise ValueError(f"{name} is given as both SSD and HDD")
            answers[name] = cls
    return answers


def check_answers(disks: Iterable[Disk], answers: Answers) -> None:
    """Raise ``ValueError`` when an answer names a disk that is not planned."""

    names = {disk.name for disk in disks}
    unknown = sorted(set(answers) - names)
    if unknown:
        known = ", ".join(sorted(names)) or "none"
        raise ValueError(
            f"not a disk pre-nixos can plan: {', '.join(unknown)} (disks: {known})"
        )


def apply_classes(disks: Sequence[Disk], answers: Answers) -> List[Disk]:
    """``disks`` with each answered disk's class set as answered (pure)."""

    check_answers(disks, answers)
    result = [
        dataclasses.replace(disk, rotational=answers[disk.name] is DiskClass.HDD)
        if disk.name in answers
        else disk
        for disk in disks
    ]
    # Postcondition: every answer holds; nothing else changed.
    for before, after in zip(disks, result):
        assert current_class(after) is answers.get(before.name, current_class(before))
        assert dataclasses.replace(after, rotational=before.rotational) == before
    return result


def toggled(answers: Answers, disk: Disk) -> Dict[str, DiskClass]:
    """New answers with ``disk`` (as currently classed) switched SSD↔HDD."""

    current = answers.get(disk.name, current_class(disk))
    new = DiskClass.HDD if current is DiskClass.SSD else DiskClass.SSD
    return {**answers, disk.name: new}


def annotate_plan(plan: Dict[str, Any], answers: Answers) -> Dict[str, Any]:
    """``plan`` recording the user's answers (a new dict; ``plan`` is kept)."""

    if not answers:
        return plan
    return {**plan, PLAN_KEY: {name: answers[name].value for name in sorted(answers)}}


def describe(disk: Disk) -> str:
    return f"{disk.name} ({disk.model})" if disk.model else disk.name


def question(disk: Disk) -> str:
    """The question put to the user about an ambiguous disk."""

    return (
        f"{describe(disk)} reports itself as rotating, but its name says SSD. "
        "Treat it as an SSD or an HDD?"
    )


def refusal_message(disks: Sequence[Disk]) -> str:
    """Why an unattended run stops (R-S3), and how to answer."""

    assert disks, "a refusal needs at least one unconfirmed disk"
    names = " ".join(disk.name for disk in disks)
    listed = ", ".join(describe(disk) for disk in disks)
    return (
        f"Disk type unconfirmed: {listed} reported as rotating, but the model "
        "name says SSD. Storage is not provisioned and NixOS is not installed "
        "until you confirm: run pre-nixos-tui, or pre-nixos with "
        f"--ssd or --hdd for each of: {names}."
    )


__all__ = [
    "Answers",
    "DiskClass",
    "PLAN_KEY",
    "UNCONFIRMED_REASON",
    "annotate_plan",
    "apply_classes",
    "check_answers",
    "describe",
    "disk_name",
    "is_ambiguous",
    "current_class",
    "name_suggests_ssd",
    "parse_answers",
    "question",
    "refusal_message",
    "toggled",
    "unconfirmed",
]
