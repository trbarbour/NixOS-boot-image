import os
import subprocess
from pathlib import Path

from pre_nixos import __version__ as PRE_NIXOS_VERSION


def test_login_notice_prints_lan_ipv4(tmp_path):
    state_dir = tmp_path / "run/pre-nixos"
    state_dir.mkdir(parents=True)
    network_status = state_dir / "network-status"
    network_status.write_text("LAN_IPV4=203.0.113.5\n", encoding="utf-8")

    login_notice = Path(__file__).resolve().parents[1] / "modules" / "pre-nixos" / "login-notice.sh"

    env = os.environ.copy()
    env.update(
        {
            "PRE_NIXOS_VERSION": PRE_NIXOS_VERSION,
            "PRE_NIXOS_STATE_DIR": str(state_dir),
        }
    )

    result = subprocess.run(
        ["bash", str(login_notice)],
        check=True,
        capture_output=True,
        text=True,
        env=env,
    )

    assert "LAN IPv4 address: 203.0.113.5" in result.stdout


def test_login_notice_explains_an_unconfirmed_disk(tmp_path):
    """R-S3: the boot run stopped for the user's answer about a disk's type."""

    state_dir = tmp_path / "run/pre-nixos"
    state_dir.mkdir(parents=True)
    (state_dir / "storage-status").write_text(
        "STATE=plan-only\nDETAIL=disk-class-unconfirmed\nAUTO_INSTALL=skipped\n", encoding="utf-8"
    )
    login_notice = Path(__file__).resolve().parents[1] / "modules" / "pre-nixos" / "login-notice.sh"
    env = os.environ.copy()
    env["PRE_NIXOS_STATE_DIR"] = str(state_dir)

    result = subprocess.run(
        ["bash", str(login_notice)], check=True, capture_output=True, text=True, env=env
    )

    assert "A disk named SSD is reported as rotating" in result.stdout
    assert "pre-nixos-tui" in result.stdout and "--ssd DISK" in result.stdout
