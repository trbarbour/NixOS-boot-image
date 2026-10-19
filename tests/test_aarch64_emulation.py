"""scripts/lib/aarch64_emulation.sh: binfmt + Nix setup for AArch64 builds (R-T1).

AArch64 plan §3.3 and experiment E2.  The functions run against temporary
stand-ins for /proc/sys/fs/binfmt_misc and /etc/nix/nix.custom.conf.
"""
from __future__ import annotations

import os
import subprocess
from pathlib import Path

LIB = Path(__file__).resolve().parents[1] / "scripts" / "lib" / "aarch64_emulation.sh"
# /usr/lib/binfmt.d/qemu-aarch64.conf from Ubuntu's qemu-user-static (2026-10-19).
PACKAGED_RULE = (
    r":qemu-aarch64:M::\x7f\x45\x4c\x46\x02\x01\x01\x00\x00\x00\x00\x00\x00\x00\x00\x00"
    r"\x02\x00\xb7\x00:\xff\xff\xff\xff\xff\xff\xff\x00\xff\xff\xff\xff\xff\xff\xff\xff"
    r"\xfe\xff\xff\xff:/usr/libexec/qemu-binfmt/aarch64-binfmt-P:OPF"
)


def _env(tmp_path: Path) -> dict[str, str]:
    binfmt = tmp_path / "binfmt"
    binfmt.mkdir(exist_ok=True)
    (binfmt / "register").touch()  # "mounted"
    conf = tmp_path / "qemu-aarch64.conf"
    conf.write_text(PACKAGED_RULE + "\n")
    qemu = tmp_path / "qemu-aarch64-static"
    qemu.write_text("#!/bin/sh\n")
    qemu.chmod(0o755)
    return {
        **os.environ,
        "BINFMT_DIR": str(binfmt),
        "QEMU_BINFMT_CONF": str(conf),
        "QEMU_AARCH64_STATIC": str(qemu),
        "NIX_CUSTOM_CONF": str(tmp_path / "nix.custom.conf"),
    }


def _run(function: str, env: dict[str, str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["bash", "-c", f'source "{LIB}" && {function}'], env=env, capture_output=True, text=True
    )


def test_rule_keeps_magic_and_mask_and_uses_static_qemu_with_f(tmp_path: Path) -> None:
    env = _env(tmp_path)
    rule = _run("aarch64_binfmt_rule", env).stdout.strip()
    assert rule == PACKAGED_RULE.rsplit(":", 2)[0] + f":{env['QEMU_AARCH64_STATIC']}:F"


def test_registers_once_then_is_idempotent(tmp_path: Path) -> None:
    env = _env(tmp_path)
    register = Path(env["BINFMT_DIR"]) / "register"
    assert _run("ensure_aarch64_emulation", env).returncode == 0
    assert register.read_text().endswith(f":{env['QEMU_AARCH64_STATIC']}:F")

    # The kernel now reports the rule; a second run must not register again.
    (Path(env["BINFMT_DIR"]) / "qemu-aarch64").write_text(
        f"enabled\ninterpreter {env['QEMU_AARCH64_STATIC']}\nflags: F\noffset 0\n"
    )
    register.write_text("")
    assert _run("ensure_aarch64_emulation", env).returncode == 0
    assert register.read_text() == ""
    assert Path(env["NIX_CUSTOM_CONF"]).read_text().splitlines() == ["extra-extra-platforms = aarch64-linux"]


def test_replaces_a_rule_with_another_interpreter(tmp_path: Path) -> None:
    env = _env(tmp_path)
    entry = Path(env["BINFMT_DIR"]) / "qemu-aarch64"
    entry.write_text("enabled\ninterpreter /usr/libexec/qemu-binfmt/aarch64-binfmt-P\nflags: OCF\n")
    assert _run("ensure_aarch64_binfmt", env).returncode == 0
    assert entry.read_text() == "-1"  # removal written before re-registering
    assert (Path(env["BINFMT_DIR"]) / "register").read_text().endswith(":F")


def test_missing_qemu_is_reported_and_nix_is_left_alone(tmp_path: Path) -> None:
    env = _env(tmp_path)
    env["QEMU_AARCH64_STATIC"] = str(tmp_path / "absent")
    result = _run("ensure_aarch64_emulation", env)
    assert result.returncode != 0
    assert "qemu-user-static" in result.stderr
    assert not Path(env["NIX_CUSTOM_CONF"]).exists()
