"""Plug a disk into a booting VM once the boot service starts waiting for
the disks (task queue item 50; plans/2026-11-11T194943Z-disk-settle-design.md).

The VM is driven through pexpect, which logs everything it reads to the
serial log, and the controller logs in from its constructor.  So the trigger
is watched in that log from a thread, rather than with ``expect``, which
could consume the login prompt.
"""

from __future__ import annotations

import threading
import time
from pathlib import Path
from typing import Callable, Optional


class LateDiskPlugger(threading.Thread):
    """Wait for *trigger* in *serial_log*, then *delay* seconds, then *plug*."""

    def __init__(
        self,
        *,
        serial_log: Path,
        trigger: str,
        plug: Callable[[], None],
        delay: float,
        timeout: float = 900.0,
        poll: float = 0.2,
    ) -> None:
        super().__init__(name="late-disk-plugger", daemon=True)
        assert delay >= 0 and timeout > 0 and poll > 0
        self.serial_log = serial_log
        self.trigger = trigger
        self.plug = plug
        self.delay = delay
        self.timeout = timeout
        self.poll = poll
        self.triggered_at: Optional[float] = None
        self.plugged_at: Optional[float] = None
        self.error: Optional[BaseException] = None

    def _seen(self) -> bool:
        try:
            return self.trigger in self.serial_log.read_text(encoding="utf-8", errors="ignore")
        except FileNotFoundError:
            return False

    def run(self) -> None:
        try:
            deadline = time.monotonic() + self.timeout
            while not self._seen():
                if time.monotonic() > deadline:
                    raise TimeoutError(f"{self.trigger!r} not in {self.serial_log} within {self.timeout} s")
                time.sleep(self.poll)
            self.triggered_at = time.monotonic()
            time.sleep(self.delay)
            self.plug()
            self.plugged_at = time.monotonic()
        except BaseException as exc:  # reported to the test through check()
            self.error = exc

    def check(self) -> None:
        """Fail the test unless the disk was plugged."""

        if self.plugged_at is None:
            raise AssertionError(f"the late disk was not plugged: {self.error!r}")
