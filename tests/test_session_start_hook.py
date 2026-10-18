"""The Claude Code SessionStart hook must do nothing outside cloud sessions."""
from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
HOOK = REPO_ROOT / ".claude" / "hooks" / "session-start.sh"


@pytest.mark.parametrize("remote", [None, "false", ""])
def test_hook_is_a_silent_no_op_outside_the_cloud(remote: str | None, tmp_path: Path) -> None:
    env = {k: v for k, v in os.environ.items() if k != "CLAUDE_CODE_REMOTE"}
    if remote is not None:
        env["CLAUDE_CODE_REMOTE"] = remote
    env_file = tmp_path / "env"
    env_file.write_text("")
    env["CLAUDE_ENV_FILE"] = str(env_file)
    env["CLAUDE_PROJECT_DIR"] = str(tmp_path)  # no repo here: any real work would fail

    result = subprocess.run([str(HOOK)], env=env, capture_output=True, text=True)

    assert (result.returncode, result.stdout, result.stderr) == (0, "", "")
    assert env_file.read_text() == ""
