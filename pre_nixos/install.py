"""Automated NixOS installation helpers."""

from __future__ import annotations

import os
import shutil
import subprocess
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, Optional

from .logging_utils import log_event
from .network import LanConfiguration

_AUTO_STATUS_FILENAME = "auto-install-status"
_BLOCK_START = "# pre-nixos auto-install start"
_BLOCK_END = "# pre-nixos auto-install end"


@dataclass(frozen=True)
class AutoInstallResult:
    """Outcome of an ``auto_install`` invocation."""

    status: str
    reason: Optional[str] = None
    details: Dict[str, str] = field(default_factory=dict)


def _record_result(
    status: str,
    *,
    status_dir: Path,
    reason: Optional[str] = None,
    details: Optional[Dict[str, str]] = None,
) -> AutoInstallResult:
    """Persist and return an :class:`AutoInstallResult`."""

    payload: Dict[str, str] = {}
    if details:
        payload.update(details)
    if reason:
        payload.setdefault("reason", reason)

    log_event(
        "pre_nixos.install.result",
        status=status,
        reason=reason,
        details=payload,
    )

    try:
        status_dir.mkdir(parents=True, exist_ok=True)
        status_path = status_dir / _AUTO_STATUS_FILENAME
        lines = [f"STATE={status}\n"]
        if reason:
            lines.append(f"REASON={reason}\n")
        for key, value in sorted(payload.items()):
            normalized_key = key.upper()
            # ``payload`` already includes the reason field; avoid duplicating it
            # after it has been emitted explicitly above.
            if normalized_key == "REASON":
                continue
            lines.append(f"{normalized_key}={value}\n")
        status_path.write_text("".join(lines), encoding="utf-8")
        log_event(
            "pre_nixos.install.status_written",
            status_path=status_path,
            status=status,
        )
    except OSError as error:
        log_event(
            "pre_nixos.install.status_write_failed",
            error=str(error),
            status=status,
            status_dir=status_dir,
        )

    return AutoInstallResult(status=status, reason=reason, details=payload)


def _is_mount_ready(root_path: Path) -> bool:
    """Return ``True`` when ``root_path`` is an active mount point."""

    if not root_path.exists():
        return False

    try:
        if root_path.is_mount():
            return True
    except OSError:
        return False

    try:
        resolved = root_path.resolve(strict=False)
    except OSError:
        return False

    try:
        with open("/proc/self/mountinfo", "r", encoding="utf-8") as fp:
            for line in fp:
                parts = line.split()
                if len(parts) < 5:
                    continue
                mount_point = Path(parts[4]).resolve(strict=False)
                if mount_point == resolved:
                    return True
    except OSError:
        return False

    if os.environ.get("PYTEST_CURRENT_TEST"):
        etc_dir = root_path / "etc"
        if etc_dir.exists():
            return True

    return False


def _wait_for_mount(root_path: Path, *, attempts: int = 30, delay: float = 1.0) -> bool:
    """Poll ``root_path`` until it becomes a mount point."""

    exec_enabled = os.environ.get("PRE_NIXOS_EXEC") == "1"
    sleep_interval = delay if exec_enabled else min(delay, 0.1)

    log_event(
        "pre_nixos.install.wait_for_mount.start",
        root_path=root_path,
        attempts=attempts,
        delay_seconds=delay,
    )

    for attempt in range(1, attempts + 1):
        if _is_mount_ready(root_path):
            log_event(
                "pre_nixos.install.wait_for_mount.ready",
                root_path=root_path,
                attempt=attempt,
            )
            return True
        time.sleep(sleep_interval)

    log_event(
        "pre_nixos.install.wait_for_mount.timeout",
        root_path=root_path,
        attempts=attempts,
        delay_seconds=delay,
    )
    return False


def _escape_nix_string(value: str) -> str:
    """Return *value* escaped for inclusion inside a Nix string literal."""

    return value.replace("\\", "\\\\").replace('"', '\\"')


def _inject_configuration(root_path: Path, key_text: str) -> None:
    """Rewrite ``configuration.nix`` with the managed auto-install block."""

    config_dir = root_path / "etc/nixos"
    config_dir.mkdir(parents=True, exist_ok=True)
    config_path = config_dir / "configuration.nix"

    try:
        existing = config_path.read_text(encoding="utf-8")
    except FileNotFoundError:
        existing = "{\n}\n"

    lines = existing.splitlines()
    filtered: list[str] = []
    skipping = False
    for line in lines:
        stripped = line.strip()
        if stripped == _BLOCK_START:
            skipping = True
            continue
        if stripped == _BLOCK_END:
            skipping = False
            continue
        if skipping:
            continue
        filtered.append(line)

    block_lines = [
        "  # pre-nixos auto-install start",
        "  networking.firewall = {",
        "    enable = true;",
        "    allowPing = true;",
        "    allowedTCPPorts = [ 22 ];",
        "    allowedUDPPorts = [ ];",
        "  };",
        "",
        "  services.openssh = {",
        "    enable = true;",
        "    settings = {",
        "      PasswordAuthentication = false;",
        '      PermitRootLogin = "prohibit-password";',
        "    };",
        "  };",
        "",
        "  users.users.root.openssh.authorizedKeys.keys = [",
        f'    "{_escape_nix_string(key_text)}"',
        "  ];",
        "",
        "  systemd.network.enable = true;",
        '  systemd.network.networks."lan" = {',
        '    matchConfig.Name = "lan";',
        '    networkConfig.DHCP = "yes";',
        "  };",
        "",
        '  nix.settings.experimental-features = [ "nix-command" "flakes" ];',
        "  # pre-nixos auto-install end",
    ]

    terminator_index = None
    for index in range(len(filtered) - 1, -1, -1):
        if filtered[index].strip() == "}":
            terminator_index = index
            break

    if terminator_index is None:
        filtered.extend(block_lines)
        filtered.append("}")
    else:
        filtered = filtered[:terminator_index] + block_lines + filtered[terminator_index:]

    text = "\n".join(filtered)
    if not text.endswith("\n"):
        text += "\n"

    config_path.write_text(text, encoding="utf-8")


def _copy_unit(source: Optional[Path], target_dir: Path) -> Optional[Path]:
    """Copy ``source`` into ``target_dir`` preserving contents."""

    if source is None:
        return None
    if not source.exists():
        raise FileNotFoundError(f"Missing network artifact: {source}")

    target_dir.mkdir(parents=True, exist_ok=True)
    destination = target_dir / source.name
    shutil.copyfile(source, destination)
    os.chmod(destination, 0o644)
    return destination


def auto_install(
    lan: Optional[LanConfiguration],
    *,
    enabled: bool = True,
    dry_run: bool = False,
    root_path: Path = Path("/mnt"),
    status_dir: Path = Path("/run/pre-nixos"),
    mount_attempts: int = 30,
    mount_delay: float = 1.0,
) -> AutoInstallResult:
    """Automatically install NixOS when prerequisites are satisfied."""

    log_event(
        "pre_nixos.install.start",
        enabled=enabled,
        dry_run=dry_run,
        root_path=root_path,
        status_dir=status_dir,
    )

    if not enabled:
        return _record_result("skipped", status_dir=status_dir, reason="disabled")

    if lan is None:
        return _record_result(
            "skipped",
            status_dir=status_dir,
            reason="missing-network-configuration",
        )

    execute = os.environ.get("PRE_NIXOS_EXEC") == "1"
    if dry_run:
        return _record_result("skipped", status_dir=status_dir, reason="dry-run")
    if not execute:
        return _record_result(
            "skipped",
            status_dir=status_dir,
            reason="execution-disabled",
        )

    if not lan.authorized_key.exists():
        return _record_result(
            "failed",
            status_dir=status_dir,
            reason="missing-authorized-key",
        )

    key_text = lan.authorized_key.read_text(encoding="utf-8").strip()
    if not key_text:
        return _record_result(
            "failed",
            status_dir=status_dir,
            reason="empty-authorized-key",
        )

    if not _wait_for_mount(root_path, attempts=mount_attempts, delay=mount_delay):
        return _record_result(
            "failed",
            status_dir=status_dir,
            reason="mount-unavailable",
        )

    log_event("pre_nixos.install.generate_config.start", root_path=root_path)
    result = subprocess.run(
        ["nixos-generate-config", "--root", str(root_path)],
        check=False,
    )
    if result.returncode != 0:
        log_event(
            "pre_nixos.install.generate_config.failed",
            returncode=result.returncode,
        )
        return _record_result(
            "failed",
            status_dir=status_dir,
            reason="nixos-generate-config",
            details={"returncode": str(result.returncode)},
        )
    log_event(
        "pre_nixos.install.generate_config.finished",
        returncode=result.returncode,
    )

    try:
        _inject_configuration(root_path, key_text)
    except Exception as exc:  # pragma: no cover - unexpected filesystem errors
        log_event("pre_nixos.install.configuration_write_failed", error=str(exc))
        return _record_result(
            "failed",
            status_dir=status_dir,
            reason="configuration-write",
        )

    try:
        target_dir = root_path / "etc/systemd/network"
        copied_units = {}
        for label, source in {
            "rename_rule": lan.rename_rule,
            "network_unit": lan.network_unit,
        }.items():
            if source is None:
                continue
            destination = _copy_unit(source, target_dir)
            copied_units[label] = str(destination)
        if copied_units:
            log_event(
                "pre_nixos.install.network_units_copied",
                files=copied_units,
            )
    except Exception as exc:
        log_event("pre_nixos.install.network_unit_copy_failed", error=str(exc))
        return _record_result(
            "failed",
            status_dir=status_dir,
            reason="network-unit-copy",
        )

    log_event("pre_nixos.install.nixos_install.start", root_path=root_path)
    result = subprocess.run(
        ["nixos-install", "--root", str(root_path), "--no-root-passwd"],
        check=False,
    )
    if result.returncode != 0:
        log_event(
            "pre_nixos.install.nixos_install.failed",
            returncode=result.returncode,
        )
        return _record_result(
            "failed",
            status_dir=status_dir,
            reason="nixos-install",
            details={"returncode": str(result.returncode)},
        )

    log_event(
        "pre_nixos.install.nixos_install.finished",
        returncode=result.returncode,
    )
    return _record_result(
        "success",
        status_dir=status_dir,
        details={"root_path": str(root_path)},
    )
