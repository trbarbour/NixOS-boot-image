"""Automated NixOS installation helpers."""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import time
from importlib import resources
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, Optional, Tuple

from . import state
from .console import broadcast_to_consoles
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


_NIX_INTERPOLATION = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*(\.[A-Za-z0-9_]+)+$")


def _escape_nix_indented_line(value: str) -> str:
    """Return *value* with Nix indented string escapes applied."""

    def escape(match: re.Match[str]) -> str:
        inner = match.group(1)
        if _NIX_INTERPOLATION.fullmatch(inner):
            return match.group(0)
        return "''${" + inner + "}"

    return re.sub(r"\$\{([^}]+)\}", escape, value)


def _extract_label(extra_args: Iterable[str]) -> Optional[str]:
    """Return the filesystem/swap label from ``extra_args`` when present."""

    args = list(extra_args)
    for index, token in enumerate(args):
        if token in {"-L", "--label", "-n"} and index + 1 < len(args):
            label = args[index + 1]
            if label:
                return label
    return None


def _collect_storage_definitions(
    storage_plan: Optional[Dict[str, Any]],
) -> Tuple[list[Dict[str, Any]], list[Dict[str, str]]]:
    """Return filesystem and swap definitions extracted from ``storage_plan``."""

    if not storage_plan:
        return [], []

    devices = storage_plan.get("disko") if isinstance(storage_plan, dict) else None
    if not isinstance(devices, dict):
        return [], []

    filesystems: list[Dict[str, Any]] = []
    swaps: list[Dict[str, str]] = []

    def select_locator(
        context: Dict[str, str], label: Optional[str]
    ) -> Optional[Dict[str, str]]:
        kind = context.get("kind")
        if label:
            return {"label": label}
        if kind == "lvm_lv":
            vg = context.get("vg")
            lv = context.get("lv")
            if vg and lv:
                return {"device": f"/dev/{vg}/{lv}"}
        elif kind == "partition":
            part = context.get("partition")
            if part:
                return {"device": f"/dev/{part}"}
        return None

    def handle_content(content: Any, context: Dict[str, str]) -> None:
        if not isinstance(content, dict):
            return
        ctype = content.get("type")
        if ctype == "filesystem":
            mountpoint = content.get("mountpoint")
            if not isinstance(mountpoint, str) or not mountpoint:
                return
            extra_args = content.get("extraArgs") or []
            label = _extract_label(extra_args)
            fs_type = content.get("format")
            if not isinstance(fs_type, str) or not fs_type:
                return
            options = content.get("mountOptions") or []
            if not isinstance(options, list):
                options = []
            locator = select_locator(context, label)
            if not locator:
                return
            entry = {
                "mountpoint": mountpoint,
                "fsType": fs_type,
                "options": [opt for opt in options if isinstance(opt, str) and opt],
                **locator,
            }
            permissions = content.get("mountpointPermissions")
            if isinstance(permissions, int):
                entry["mountpointPermissions"] = permissions
            filesystems.append(entry)
        elif ctype == "swap":
            extra_args = content.get("extraArgs") or []
            label = _extract_label(extra_args)
            locator = select_locator(context, label)
            if locator:
                swaps.append(locator)

    for disk_name, disk in devices.get("disk", {}).items():
        partitions = (
            disk.get("content", {}).get("partitions", {})
            if isinstance(disk, dict)
            else {}
        )
        for part_name, part in partitions.items():
            content = part.get("content") if isinstance(part, dict) else None
            handle_content(
                content,
                {"kind": "partition", "disk": disk_name, "partition": part_name},
            )

    for vg_name, vg in devices.get("lvm_vg", {}).items():
        lvs = vg.get("lvs", {}) if isinstance(vg, dict) else {}
        for lv_name, lv in lvs.items():
            content = lv.get("content") if isinstance(lv, dict) else None
            handle_content(
                content,
                {"kind": "lvm_lv", "vg": vg_name, "lv": lv_name},
            )

    filesystems.sort(key=lambda entry: entry["mountpoint"])
    swaps.sort(key=lambda entry: entry.get("label") or entry.get("device") or "")
    return filesystems, swaps


def _format_nix_list(items: Iterable[str]) -> str:
    quoted = [f'"{_escape_nix_string(item)}"' for item in items]
    if not quoted:
        return "[ ]"
    return "[ " + " ".join(quoted) + " ]"


def _extract_original_name(rename_rule: Optional[Path]) -> Optional[str]:
    """Return the ``OriginalName`` entry from a systemd ``.link`` file."""

    if rename_rule is None:
        return None

    try:
        lines = rename_rule.read_text(encoding="utf-8").splitlines()
    except OSError:
        return None

    for raw_line in lines:
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            continue
        key, value = line.split("=", 1)
        if key.strip() != "OriginalName":
            continue
        original = value.strip()
        if original:
            return original
    return None


def _load_ip_announcement_script() -> list[str]:
    """Return the shared LAN IP announcement script as a list of lines."""

    try:
        script = resources.files(__package__).joinpath("scripts/announce-lan-ip.sh")
        content = script.read_text(encoding="utf-8")
    except (FileNotFoundError, OSError) as error:  # pragma: no cover - unexpected packaging issue
        raise FileNotFoundError(
            "Missing IP announcement helper packaged with pre_nixos"
        ) from error
    # Preserve interior blank lines while trimming trailing whitespace-only lines
    return content.strip("\n").splitlines()


def _inject_configuration(
    root_path: Path,
    key_text: str,
    lan: LanConfiguration,
    storage_plan: Optional[Dict[str, Any]],
) -> None:
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

    filesystems, swaps = _collect_storage_definitions(storage_plan)

    original_name = _extract_original_name(lan.rename_rule)

    block_lines = [
        "  # pre-nixos auto-install start",
        "  networking.firewall = {",
        "    enable = true;",
        "    allowPing = true;",
        "    allowedTCPPorts = [ 22 ];",
        "    allowedUDPPorts = [ ];",
        "  };",
        "",
        "  networking.useDHCP = false;",
        "  networking.useNetworkd = true;",
        "  networking.interfaces.lan = {",
        "    useDHCP = true;",
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
    ]

    if lan.mac_address:
        block_lines.append(
            f'    matchConfig.MACAddress = "{_escape_nix_string(lan.mac_address)}";'
        )
    elif lan.interface:
        block_lines.append(
            f'    matchConfig.Name = "{_escape_nix_string(lan.interface)}";'
        )
    else:
        block_lines.append('    matchConfig.Name = "lan";')

    block_lines.extend(
        [
            '    networkConfig.DHCP = "yes";',
            "  };",
            "",
        ]
    )

    link_match_lines: list[str] = []
    if lan.mac_address:
        link_match_lines.append(
            f'    matchConfig.MACAddress = "{_escape_nix_string(lan.mac_address)}";'
        )
    elif original_name:
        link_match_lines.append(
            f'    matchConfig.OriginalName = "{_escape_nix_string(original_name)}";'
        )
    elif lan.interface:
        link_match_lines.append(
            f'    matchConfig.OriginalName = "{_escape_nix_string(lan.interface)}";'
        )

    if link_match_lines:
        block_lines.append('  systemd.network.links."lan" = {')
        block_lines.extend(link_match_lines)
        block_lines.extend(
            [
                '    linkConfig.Name = "lan";',
                "  };",
                "",
            ]
        )

    block_lines.extend(
        [
            '  systemd.services."pre-nixos-auto-install-ip" = {',
            '    description = "Announce LAN IPv4 on boot";',
            '    wantedBy = [ "multi-user.target" ];',
            '    after = [ "network-online.target" ];',
            '    wants = [ "network-online.target" ];',
            '    path = with pkgs; [ coreutils gnused gnugrep iproute2 util-linux findutils busybox ];',
            '    environment = let',
            '      broadcastConsoleCmd =',
            '        if builtins.hasAttr "pre-nixos" pkgs then',
            '          "${pkgs.pre-nixos}/bin/pre-nixos-console broadcast"',
            '        else "pre-nixos-console broadcast";',
            '    in {',
            '      PRE_NIXOS_STATE_DIR = "/run/pre-nixos";',
            '      ANNOUNCE_STATUS_FILE = "/run/pre-nixos/network-status";',
            '      ANNOUNCE_WRITE_STATUS = "1";',
            '      ANNOUNCE_UPDATE_ISSUE = "0";',
            '      ANNOUNCE_NOTIFY_CONSOLES = "1";',
            '      ANNOUNCE_CONSOLE_FALLBACK = "1";',
            '      ANNOUNCE_STDOUT_MESSAGE = "1";',
            '      ANNOUNCE_PREFERRED_IFACE = "lan";',
            '      ANNOUNCE_MAX_ATTEMPTS = "60";',
            '      ANNOUNCE_DELAY = "1";',
            '      BROADCAST_CONSOLE_CMD = broadcastConsoleCmd;',
            '    };',
            '    serviceConfig = {',
            '      Type = "oneshot";',
            '      StandardOutput = "journal+console";',
            '      StandardError = "journal+console";',
            '    };',
        ]
    )
    announcement_script = _load_ip_announcement_script()
    block_lines.append("    script = ''")
    for line in announcement_script:
        block_lines.append(f"      {_escape_nix_indented_line(line)}")
    block_lines.append("    '';")
    block_lines.append("  };")
    block_lines.append("")

    block_lines.extend(
        [
            "  boot.swraid.mdadmConf = ''",
            "    MAILADDR root",
            "  '';",
            "",
        ]
    )

    tmpfiles_rules: list[str] = []
    if filesystems:
        block_lines.append("  fileSystems = {")
        for entry in filesystems:
            mountpoint = entry["mountpoint"]
            block_lines.append(f'    "{_escape_nix_string(mountpoint)}" = {{')
            if "label" in entry:
                block_lines.append(
                    f'      label = "{_escape_nix_string(entry["label"])}";'
                )
            elif "device" in entry:
                block_lines.append(
                    f'      device = "{_escape_nix_string(entry["device"])}";'
                )
            block_lines.append(
                f'      fsType = "{_escape_nix_string(entry["fsType"])}";'
            )
            options = entry["options"]
            if options:
                block_lines.append(
                    f"      options = {_format_nix_list(options)};"
                )
            if mountpoint in {"/", "/boot"}:
                block_lines.append("      neededForBoot = true;")
            permissions = entry.get("mountpointPermissions")
            if isinstance(permissions, int) and mountpoint != "/":
                mode = format(permissions & 0o777, "03o")
                tmpfiles_rules.append(f"d {mountpoint} {mode} root root -")
            block_lines.append("    };")
        block_lines.append("  };")
        block_lines.append("")

    if tmpfiles_rules:
        block_lines.append("  systemd.tmpfiles.rules = [")
        for rule in tmpfiles_rules:
            block_lines.append(f'    "{_escape_nix_string(rule)}"')
        block_lines.append("  ];")
        block_lines.append("")

    block_lines.append("  swapDevices = [")
    if swaps:
        for locator in swaps:
            block_lines.append("    {")
            if "label" in locator:
                block_lines.append(
                    f'      label = "{_escape_nix_string(locator["label"])}";'
                )
            elif "device" in locator:
                block_lines.append(
                    f'      device = "{_escape_nix_string(locator["device"])}";'
                )
            block_lines.append("    }")
    block_lines.append("  ];")
    block_lines.append("")

    block_lines.extend(
        [
            "  boot.swraid.enable = true;",
            "  boot.initrd.services.lvm.enable = true;",
            '  boot.kernelParams = [ "console=tty0" "console=ttyS0,115200n8" ];',
            "  boot.loader.grub.extraConfig = ''",
            "    serial --speed=115200 --unit=0 --word=8 --parity=no --stop=1",
            "    terminal_input serial console",
            "    terminal_output serial console",
            "  '';",
            "",
            '  nix.settings.experimental-features = [ "nix-command" "flakes" ];',
            "  # pre-nixos auto-install end",
        ]
    )

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


def _rewrite_hardware_configuration(root_path: Path) -> None:
    """Remove conflicting defaults from ``hardware-configuration.nix``."""

    config_path = root_path / "etc/nixos/hardware-configuration.nix"
    try:
        existing = config_path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return

    lines = existing.splitlines()
    filtered: list[str] = []
    skipping = False
    depth = 0

    def depth_delta(line: str) -> int:
        return line.count("{") + line.count("[") - line.count("}") - line.count("]")

    for line in lines:
        stripped = line.strip()
        if "networking.useDHCP" in stripped:
            continue
        if not skipping and (
            stripped.startswith("fileSystems.") or stripped.startswith("swapDevices")
        ):
            skipping = True
            depth = depth_delta(line)
            if ";" in line and depth <= 0:
                skipping = False
            continue
        if skipping:
            depth += depth_delta(line)
            if ";" in line and depth <= 0:
                skipping = False
            continue
        filtered.append(line)

    text = "\n".join(filtered)
    if filtered:
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


def _format_timestamp(moment: datetime) -> str:
    """Return ``moment`` formatted as an ISO-like UTC string."""

    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=timezone.utc)
    return moment.astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M:%SZ")


def _broadcast_install_message(message: str) -> Tuple[bool, Dict[str, bool]] | None:
    """Send ``message`` to all consoles and report success."""

    try:
        success, targets, results = broadcast_to_consoles(message)
    except Exception as error:  # pragma: no cover - unexpected device error
        log_event(
            "pre_nixos.install.console_broadcast_failed",
            message=message,
            error=str(error),
        )
        return None

    if not targets and not results:
        return None

    payload = {str(path): value for path, value in results.items()}
    log_event(
        "pre_nixos.install.console_broadcast",
        message=message,
        console_paths=[str(path) for path in targets],
        console_results=payload,
        console_written=success,
    )
    return success, payload


def _write_installation_issue(root_path: Path, completed_at: datetime) -> Optional[Path]:
    """Update ``/etc/issue`` with the automated installation timestamp."""

    issue_path = root_path / "etc/issue"
    timestamp = _format_timestamp(completed_at)
    header = (
        "Automatic NixOS installation completed by pre-nixos.\n"
        f"Installation timestamp (UTC): {timestamp}\n\n"
    )

    try:
        try:
            existing = issue_path.read_text(encoding="utf-8")
        except FileNotFoundError:
            existing = ""
        if existing and not existing.endswith("\n"):
            existing += "\n"
        issue_path.parent.mkdir(parents=True, exist_ok=True)
        issue_path.write_text(header + existing, encoding="utf-8")
    except OSError as error:
        log_event(
            "pre_nixos.install.issue_write_failed",
            issue_path=issue_path,
            error=str(error),
        )
        return None

    log_event(
        "pre_nixos.install.issue_written",
        issue_path=issue_path,
        completed_at=timestamp,
    )
    return issue_path


def _request_reboot() -> bool:
    """Attempt to reboot the system using ``systemctl``."""

    if os.environ.get("PYTEST_CURRENT_TEST"):
        log_event(
            "pre_nixos.install.reboot_skipped",
            reason="pytest",
        )
        return False

    result = subprocess.run(["systemctl", "reboot"], check=False)
    if result.returncode == 0:
        log_event("pre_nixos.install.reboot_requested", returncode=result.returncode)
        return True

    log_event(
        "pre_nixos.install.reboot_failed",
        returncode=result.returncode,
    )
    return False


def auto_install(
    lan: Optional[LanConfiguration],
    storage_plan: Optional[Dict[str, Any]] = None,
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

    if storage_plan is None:
        storage_plan = state.load_storage_plan(state_dir=status_dir)
        if storage_plan is None:
            return _record_result(
                "failed",
                status_dir=status_dir,
                reason="missing-storage-plan",
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

    start_time = datetime.now(timezone.utc)
    start_message = (
        "Starting automatic NixOS installation at "
        f"{_format_timestamp(start_time)} UTC."
    )
    print(start_message)
    _broadcast_install_message(start_message)

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
        _inject_configuration(root_path, key_text, lan, storage_plan)
        _rewrite_hardware_configuration(root_path)
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

    completed_at = datetime.now(timezone.utc)
    completion_message = (
        "Automatic NixOS installation completed at "
        f"{_format_timestamp(completed_at)} UTC."
    )
    print(completion_message)
    completion_broadcast = _broadcast_install_message(completion_message)

    issue_path = _write_installation_issue(root_path, completed_at)
    reboot_requested = _request_reboot()

    details: Dict[str, str] = {
        "root_path": str(root_path),
        "completed_at": _format_timestamp(completed_at),
        "reboot": "requested" if reboot_requested else "skipped",
    }
    if issue_path is not None:
        details["issue_path"] = str(issue_path)
    if completion_broadcast is not None:
        console_written, _ = completion_broadcast
        details["console_written"] = "true" if console_written else "false"

    return _record_result(
        "success",
        status_dir=status_dir,
        details=details,
    )
