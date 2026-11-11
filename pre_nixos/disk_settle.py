"""Wait at boot until the disk set has settled (task queue item 50, R-D1, R-D2).

Design: plans/2026-11-11T194943Z-disk-settle-design.md (D1, D3, D4).

``pre-nixos.service`` starts once ``multi-user.target`` is reached, which can
be before a slow controller has finished finding its disks (the user's PC:
an HBA disk at 67.8 s).  The service runs ``pre-nixos-wait-disks`` first, so
that storage detection and the plan see every disk.
"""

from __future__ import annotations

import argparse
import re
import sys
import time
from dataclasses import dataclass
from typing import Callable, FrozenSet, List, Optional, Sequence, Tuple

from . import console, inventory, kernel_cmdline
from .inventory import Disk, DiskIdentity
from .logging_utils import log_event

QUIET_PARAM = "pre-nixos-disk-quiet"
LIMIT_PARAM = "pre-nixos-disk-wait-max"
DEFAULT_QUIET = 15
DEFAULT_LIMIT = 120

EXIT_SETTLED = 0
EXIT_ERROR = 1
EXIT_UNSETTLED = 2
# Shown on the consoles when the wait starts.  From here, not the service
# script: Python started slowly (34 s in the test VM, which runs without KVM), so a
# notice from the script came well before the wait began.
CONSOLE_NOTICE = "pre-nixos: waiting for the disks to settle"
# storage-status DETAIL values the boot service writes for those exits.
UNSETTLED_DETAIL = "disks-unsettled"
ERROR_DETAIL = "disk-wait-error"

_SECONDS = re.compile(r"[0-9]+")


@dataclass(frozen=True)
class Settings:
    quiet: int = DEFAULT_QUIET
    limit: int = DEFAULT_LIMIT


@dataclass(frozen=True)
class SettleResult:
    settled: bool
    elapsed: float
    identities: FrozenSet[DiskIdentity]
    changes: List[str]


def settings_from_cmdline(tokens: Sequence[str]) -> Tuple[Settings, List[str]]:
    """The settings, and a warning for each value ignored (D3: a typo must
    not stop the boot, so a bad value falls back to the default)."""

    values = {QUIET_PARAM: DEFAULT_QUIET, LIMIT_PARAM: DEFAULT_LIMIT}
    warnings: List[str] = []
    for token in tokens:
        key, sep, value = token.partition("=")
        if not sep or key not in values:
            continue
        if _SECONDS.fullmatch(value):
            values[key] = int(value)
        else:
            warnings.append(
                f"ignoring {key}={value!r}: not a whole number of seconds; using {values[key]}"
            )
    return Settings(quiet=values[QUIET_PARAM], limit=values[LIMIT_PARAM]), warnings


def wait_for_stable(
    read: Callable[[], Sequence[Disk]],
    *,
    quiet: float,
    limit: float,
    clock: Callable[[], float],
    sleep: Callable[[float], None],
    poll: float = 1.0,
    on_change: Optional[Callable[[List[str]], None]] = None,
) -> SettleResult:
    """Poll *read* until its disks have been unchanged for *quiet* seconds,
    or *limit* seconds have passed since the start (D3)."""

    assert quiet >= 0 and limit >= 0 and poll > 0, (quiet, limit, poll)
    start = clock()
    current = inventory.disk_identities(read())
    last_change = start
    changes: List[str] = []
    while True:
        now = clock()
        if now - last_change >= quiet:
            return SettleResult(True, now - start, current, changes)
        if now - start >= limit:
            return SettleResult(False, now - start, current, changes)
        next_deadline = min(last_change + quiet, start + limit)
        sleep(min(poll, next_deadline - now))
        found = inventory.disk_identities(read())
        if found != current:
            new_changes = inventory.describe_changes(current, found)
            changes.extend(new_changes)
            if on_change is not None:
                on_change(new_changes)
            current = found
            last_change = clock()


def _read_cmdline() -> List[str]:
    return list(kernel_cmdline.tokens())


def _names(identities: FrozenSet[DiskIdentity]) -> str:
    return ", ".join(sorted(i.name for i in identities)) or "none"


def main(argv: Optional[Sequence[str]] = None) -> int:
    """``pre-nixos-wait-disks``: exit 0 settled, 2 still changing at the
    bound, 1 on an error (D4)."""

    argparse.ArgumentParser(
        description="Wait until the set of disks has settled (pre-nixos boot service).",
        epilog=f"Kernel parameters: {QUIET_PARAM}=SECONDS (default {DEFAULT_QUIET}; 0 skips the wait), "
        f"{LIMIT_PARAM}=SECONDS (default {DEFAULT_LIMIT}).",
    ).parse_args(argv)
    try:
        settings, warnings = settings_from_cmdline(_read_cmdline())
        for warning in warnings:
            print(f"pre-nixos: {warning}", file=sys.stderr)
        notice = f"{CONSOLE_NOTICE} (quiet {settings.quiet} s, at most {settings.limit} s)"
        print(notice, flush=True)
        console.broadcast_to_consoles(notice)

        def report(changes: List[str]) -> None:
            for change in changes:
                print(f"pre-nixos: disk change: {change}", flush=True)

        result = wait_for_stable(
            inventory.enumerate_disks,
            quiet=settings.quiet,
            limit=settings.limit,
            clock=time.monotonic,
            sleep=time.sleep,
            on_change=report,
        )
    except Exception as exc:  # the service falls back to plan-only (D4)
        print(f"pre-nixos: could not wait for the disks: {type(exc).__name__}: {exc}", file=sys.stderr)
        log_event("pre_nixos.disk_settle.error", error=str(exc))
        return EXIT_ERROR

    log_event(
        "pre_nixos.disk_settle.finished",
        settled=result.settled,
        elapsed_seconds=result.elapsed,
        disks=sorted(i.name for i in result.identities),
        changes=result.changes,
    )
    if result.settled:
        print(f"pre-nixos: disks settled after {result.elapsed:g} s: {_names(result.identities)}")
        return EXIT_SETTLED
    print(
        f"pre-nixos: the disks were still changing after {result.elapsed:g} s "
        f"(now: {_names(result.identities)}); the boot run will only plan",
        file=sys.stderr,
    )
    return EXIT_UNSETTLED


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
