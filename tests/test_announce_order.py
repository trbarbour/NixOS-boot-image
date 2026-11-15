"""Install messages reach the journal when they are announced (task queue item 21).

CM4 attempt 1 (docs/test-reports/2026-10-22T025029Z-cm4-item10-pre-nixos-journal.txt,
line 307): "Starting automatic NixOS installation at ... 02:50:29Z" was logged
at 02:53:25, after "Auto-install failed: nixos-install".  Not a second copy: the
journal has it once, three minutes late.  Under the boot service stdout is a
pipe, so Python block-buffers it, and the line waited in the buffer until the
process exited; stderr is unbuffered and came first.  The console broadcast
had already shown it at 02:50:29, so it looked repeated.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]

CHILD = """
import os, sys
from pre_nixos import install
install._announce("Starting automatic NixOS installation at T UTC.")
os.write(2, b"Auto-install failed: nixos-install\\n")  # unbuffered, like stderr
"""


def test_an_announcement_precedes_later_stderr_on_a_pipe() -> None:
    env = {k: v for k, v in os.environ.items() if k not in ("PYTHONUNBUFFERED", "PRE_NIXOS_EXEC")}
    result = subprocess.run(
        [sys.executable, "-c", CHILD],
        cwd=REPO,
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,  # one pipe, as the journal sees both
        text=True,
        check=True,
    )
    lines = [line for line in result.stdout.splitlines() if not line.startswith("{")]
    assert lines == [
        "Starting automatic NixOS installation at T UTC.",
        "Auto-install failed: nixos-install",
    ], result.stdout


def test_the_boot_service_runs_python_unbuffered() -> None:
    """Every other print of the boot service reaches the journal in order too."""

    module = (REPO / "modules" / "pre-nixos.nix").read_text()
    service_env = module[module.index("preNixosServiceEnv = ") :]
    service_env = service_env[: service_env.index("};")]
    assert 'PYTHONUNBUFFERED = "1";' in service_env, service_env
