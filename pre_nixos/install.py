"""Automated NixOS installation helpers."""

from __future__ import annotations

import ipaddress
import os
import re
import enum
import subprocess
import sys
import time
from importlib import resources
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, Optional, Sequence, Tuple

from . import boot_order, boot_platform, console, disk_class, network, root_password, state
from .console import broadcast_to_consoles
from .logging_utils import log_event
from .network import LanConfiguration

_AUTO_STATUS_FILENAME = "auto-install-status"
_BLOCK_START = "# pre-nixos auto-install start"
_BLOCK_END = "# pre-nixos auto-install end"
_AUTO_INSTALL_MODULE = "./pre-nixos-auto-install-ip.nix"
# Disables NetworkManager, which nixos-generate-config enables (#326).
_NETWORK_MODULE = "./pre-nixos-network.nix"
_NETWORK_MODULE_TEMPLATE = "network-networkd.nix"
# Item 49 (reqs R-S7): degraded-array reports; the module and its scripts are
# written under these names, which the module itself refers to.
_RAID_ALERTS_MODULE = "./pre-nixos-raid-alerts.nix"
_RAID_ALERTS_FILES = (
    "pre-nixos-raid-alerts.nix",
    "pre-nixos-md-status.sh",
    "pre-nixos-md-event.sh",
)
_SERIAL_CONSOLE_PARAM = "console=ttyS0,115200n8"
_VGA_CONSOLE_PARAM = "console=tty0"


@dataclass(frozen=True)
class AutoInstallResult:
    """Outcome of an ``auto_install`` invocation."""

    status: str
    reason: Optional[str] = None
    details: Dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class InstallNetworkConfig:
    """Static IPv4 settings for the installed system."""

    address: str
    netmask: str
    gateway: str
    prefix_length: int
    # Item 41 (R-N2): without DHCP nothing else supplies DNS servers.
    dns: Tuple[str, ...] = ()

    @property
    def cidr(self) -> str:
        """Return ``address/prefix`` for systemd.network configuration."""

        return f"{self.address}/{self.prefix_length}"

    def to_payload(self) -> Dict[str, Any]:
        """Return a JSON-serialisable representation of the configuration."""

        return {
            "address": self.address,
            "netmask": self.netmask,
            "gateway": self.gateway,
            "dns": list(self.dns),
        }


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


def build_install_network_config(
    address: str, netmask: str, gateway: str, dns: Optional[Sequence[str]] = None
) -> InstallNetworkConfig:
    """Return a validated :class:`InstallNetworkConfig`.

    ``dns`` defaults to the gateway (item 41, R-N2).  Raises ``ValueError``
    when any input is not a valid IPv4 element.
    """

    try:
        ip_address = ipaddress.IPv4Address(address)
    except ipaddress.AddressValueError as exc:
        raise ValueError(f"Invalid IPv4 address: {address}") from exc

    try:
        ipaddress.IPv4Address(gateway)
    except ipaddress.AddressValueError as exc:
        raise ValueError(f"Invalid IPv4 gateway: {gateway}") from exc

    try:
        ipv4_network = ipaddress.IPv4Network((address, netmask), strict=False)
    except (ipaddress.NetmaskValueError, ipaddress.AddressValueError) as exc:
        raise ValueError(f"Invalid IPv4 netmask: {netmask}") from exc

    servers = list(dns) if dns else [gateway]
    for server in servers:
        try:
            ipaddress.IPv4Address(server)
        except ipaddress.AddressValueError as exc:
            raise ValueError(f"Invalid IPv4 DNS server: {server}") from exc

    return InstallNetworkConfig(
        address=str(ip_address),
        netmask=str(ipv4_network.netmask),
        gateway=gateway,
        prefix_length=ipv4_network.prefixlen,
        dns=tuple(servers),
    )


def build_install_network_config_with_defaults(
    address: str,
    netmask: str | None = None,
    gateway: str | None = None,
    *,
    iface: str = "lan",
    dns: Optional[Sequence[str]] = None,
) -> InstallNetworkConfig:
    """Return a validated :class:`InstallNetworkConfig` using observed defaults.

    ``netmask`` and ``gateway`` may be omitted; when they are, the current IPv4
    configuration for ``iface`` is used to fill the missing values.  When no
    defaults can be derived, ``ValueError`` is raised describing the missing
    element(s).
    """

    resolved_netmask = netmask
    resolved_gateway = gateway

    if resolved_netmask is None or resolved_gateway is None:
        details = network.get_ipv4_details(iface)
        if details is not None:
            if resolved_netmask is None:
                resolved_netmask = details.netmask
            if resolved_gateway is None:
                resolved_gateway = details.gateway

    missing: list[str] = []
    if resolved_netmask is None:
        missing.append("netmask")
    if resolved_gateway is None:
        missing.append("gateway")
    if missing:
        missing_text = " and ".join(missing)
        raise ValueError(
            f"Unable to determine install {missing_text}; supply explicit values or ensure DHCP is active"
        )

    return build_install_network_config(address, resolved_netmask, resolved_gateway, dns)


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


def _read_kernel_cmdline_tokens() -> tuple[str, ...]:
    """Return kernel command-line tokens from ``/proc/cmdline``."""

    try:
        with open("/proc/cmdline", "r", encoding="utf-8") as fp:
            return tuple(fp.read().split())
    except OSError:
        return ()


_VIRTUAL_TERMINAL = re.compile(r"tty\d+")


def _is_virtual_terminal(console_value: str) -> bool:
    """``tty0``/``tty1``… are VGA/framebuffer terminals; anything else is serial."""

    return _VIRTUAL_TERMINAL.fullmatch(console_value.split(",", 1)[0]) is not None


def _select_console_kernel_params(
    cmdline_tokens: Optional[Sequence[str]] = None,
) -> list[str]:
    """Return installed-system console kernel params (reqs §3 R-C1).

    Keep every ``console=`` the booted system used (``ttyS*``, ``ttyAMA*``, …),
    each at the position of its last occurrence: the kernel's last console is
    the primary one, so the booted primary stays primary.  Always include both
    a serial and a VGA console; a missing kind is added in front, so it never
    becomes primary.
    """

    tokens = (
        list(cmdline_tokens)
        if cmdline_tokens is not None
        else list(_read_kernel_cmdline_tokens())
    )
    console_values = [
        token.split("=", 1)[1]
        for token in tokens
        if token.startswith("console=") and "=" in token
    ]
    ordered: list[str] = []
    for value in console_values:
        if value in ordered:
            ordered.remove(value)
        ordered.append(value)
    params = [f"console={value}" for value in ordered]
    if not any(_is_virtual_terminal(value) for value in ordered):
        params.insert(0, _VGA_CONSOLE_PARAM)
    if all(_is_virtual_terminal(value) for value in ordered):
        params.insert(0, _SERIAL_CONSOLE_PARAM)
    return params


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


def load_install_network_config(
    *, state_dir: Path = Path("/run/pre-nixos")
) -> Optional[InstallNetworkConfig]:
    """Return the persisted install-time network configuration when present."""

    data = state.load_install_network_config(state_dir=state_dir)
    if not data:
        return None
    try:
        # Payloads saved before item 41 have no "dns": the gateway is used.
        return build_install_network_config(
            data["address"], data["netmask"], data["gateway"], data.get("dns")
        )
    except ValueError as exc:
        log_event(
            "pre_nixos.install.install_network.invalid", reason=str(exc)
        )
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


def _load_template(name: str) -> str:
    """Return the NixOS module template ``name`` packaged under ``templates/``."""

    try:
        template_path = resources.files(__package__).joinpath(f"templates/{name}")
        return template_path.read_text(encoding="utf-8")
    except (FileNotFoundError, OSError) as error:  # pragma: no cover - packaging issue
        raise FileNotFoundError(
            f"Missing NixOS module template {name} packaged with pre_nixos"
        ) from error


def _load_auto_install_module_template() -> str:
    """Return the NixOS module used for IP announcement and diagnostics."""

    return _load_template("auto-install-ip.nix")


def _write_auto_install_module(root_path: Path) -> Path:
    """Write the auto-install helper module and script into ``/etc/nixos``."""

    module_text = _load_auto_install_module_template()
    script_lines = _load_ip_announcement_script()

    config_dir = root_path / "etc/nixos"
    config_dir.mkdir(parents=True, exist_ok=True)

    module_path = config_dir / Path(_AUTO_INSTALL_MODULE).name
    module_path.write_text(module_text, encoding="utf-8")

    script_path = config_dir / "pre-nixos-announce-lan-ip.sh"
    script_text = "\n".join(script_lines)
    if not script_text.endswith("\n"):
        script_text += "\n"
    script_path.write_text(script_text, encoding="utf-8")
    os.chmod(script_path, 0o755)

    return module_path


def _ensure_import(lines: list[str], target: str) -> list[str]:
    """Ensure ``configuration.nix`` imports the module ``target`` (``./name.nix``)."""

    in_imports = False
    open_index: int | None = None
    close_index: int | None = None

    for index, line in enumerate(lines):
        stripped = line.strip()
        if stripped.startswith("imports"):
            in_imports = True
        if not in_imports:
            continue
        if "[" in line and open_index is None:
            open_index = index
        if "]" in line:
            close_index = index
            break

    if open_index is not None and close_index is not None:
        block = "\n".join(lines[open_index: close_index + 1])
        if target in block:
            return lines
        indentation_match = re.match(r"(\s*)", lines[close_index])
        indent = indentation_match.group(1) if indentation_match else "  "
        insertion = f"{indent}  {target}"
        updated = lines[:close_index] + [insertion] + lines[close_index:]
        return updated

    insertion_block = [
        "  imports = [",
        f"    {target}",
        "  ];",
        "",
    ]
    insertion_point = 1 if lines else 0
    return lines[:insertion_point] + insertion_block + lines[insertion_point:]


# Preferred /dev/disk/by-id link kinds, most stable first: the WWN is the
# disk's own world-wide name; the bus-specific names embed model and serial.
_BY_ID_PREFERENCE = ("wwn-", "ata-", "scsi-", "nvme-")


def _stable_disk_path(disk: str, by_id_dir: Path = Path("/dev/disk/by-id")) -> str:
    """A name for ``/dev/<disk>`` that survives reordering (GRUB's targets).

    The kernel name (``sda``) can change between boots, and nixos-rebuild
    reinstalls GRUB to the configured devices, so a by-id link is used when
    one exists; otherwise the kernel name, which is logged.
    """

    target = os.path.realpath(f"/dev/{disk}") if by_id_dir == Path("/dev/disk/by-id") else None
    candidates: list[str] = []
    try:
        entries = sorted(by_id_dir.iterdir())
    except OSError:
        entries = []
    for entry in entries:
        if "-part" in entry.name:
            continue
        resolved = os.path.realpath(entry)
        if os.path.basename(resolved) == disk or (target is not None and resolved == target):
            candidates.append(entry.name)
    for prefix in _BY_ID_PREFERENCE:
        for name in candidates:
            if name.startswith(prefix):
                return str(by_id_dir / name)
    if candidates:
        return str(by_id_dir / candidates[0])
    log_event("pre_nixos.install.no_stable_disk_path", disk=disk, by_id_dir=by_id_dir)
    return f"/dev/{disk}"


def _render_loader_module(template: str, boot_devices: Sequence[str]) -> str:
    """Fill in GRUB's target disks where the template asks for them."""

    placeholder = boot_platform.BIOS_BOOT_DEVICES_PLACEHOLDER
    if placeholder not in template:
        return template
    assert template.count(placeholder) == 1, "placeholder must appear once"
    assert boot_devices, "a BIOS loader module needs at least one target disk"
    return template.replace(placeholder, _format_nix_list(boot_devices))


def _plan_boot_disks(storage_plan: Optional[Dict[str, Any]]) -> list[str]:
    """The disks the plan put the boot partitions on (``plan["boot"]``)."""

    boot = (storage_plan or {}).get("boot") or {}
    disks = boot.get("disks") or []
    assert all(isinstance(disk, str) for disk in disks), f"bad boot disks {disks!r}"
    return list(disks)


def _inject_configuration(
    root_path: Path,
    key_text: str,
    lan: LanConfiguration,
    storage_plan: Optional[Dict[str, Any]],
    install_network: Optional[InstallNetworkConfig] = None,
    console_kernel_params: Optional[Sequence[str]] = None,
    boot_setup: boot_platform.BootSetup = boot_platform.NIXOS_DEFAULT_SETUP,
    boot_devices: Sequence[str] = (),
    root_hash: Optional[root_password.RootHash] = None,
) -> None:
    """Rewrite ``configuration.nix`` with the managed auto-install block.

    ``boot_devices``: GRUB's target disks for ``X86_BIOS_GRUB`` (stable paths).
    ``root_hash``: the site's hashed root password, if any (reqs R-A1).
    """

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

    _write_auto_install_module(root_path)
    filtered = _ensure_import(filtered, _AUTO_INSTALL_MODULE)
    (config_dir / Path(_NETWORK_MODULE).name).write_text(
        _load_template(_NETWORK_MODULE_TEMPLATE), encoding="utf-8"
    )
    filtered = _ensure_import(filtered, _NETWORK_MODULE)
    for name in _RAID_ALERTS_FILES:
        (config_dir / name).write_text(_load_template(name), encoding="utf-8")
    filtered = _ensure_import(filtered, _RAID_ALERTS_MODULE)
    loader_template = boot_platform.loader_module_template(boot_setup)
    if loader_template is not None:
        (config_dir / boot_platform.LOADER_MODULE_FILE).write_text(
            _render_loader_module(_load_template(loader_template), boot_devices),
            encoding="utf-8",
        )
        filtered = _ensure_import(filtered, f"./{boot_platform.LOADER_MODULE_FILE}")

    filesystems, swaps = _collect_storage_definitions(storage_plan)
    effective_console_kernel_params = list(
        console_kernel_params
        if console_kernel_params is not None
        else _select_console_kernel_params()
    )

    original_name = _extract_original_name(lan.rename_rule)
    use_dhcp = install_network is None

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
        f"    useDHCP = {'true' if use_dhcp else 'false'};",
    ]

    if not use_dhcp:
        block_lines.append(
            "    ipv4.addresses = [ { address = \""
            + _escape_nix_string(install_network.address)
            + "\"; prefixLength = "
            + str(install_network.prefix_length)
            + "; } ];"
        )

    block_lines.extend(
        [
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
            *root_password.nix_lines(root_hash),
            "  systemd.network.enable = true;",
            '  systemd.network.networks."lan" = {',
        ]
    )

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

    if use_dhcp:
        network_block = ['    networkConfig.DHCP = "yes";']
    else:
        network_block = [
            '    networkConfig.DHCP = "no";',
            f'    networkConfig.Address = [ "{install_network.cidr}" ];',
            f'    networkConfig.Gateway = "{_escape_nix_string(install_network.gateway)}";',
            "    networkConfig.DNS = [ "
            + " ".join(f'"{_escape_nix_string(server)}"' for server in install_network.dns)
            + " ];",
        ]

    block_lines.extend(network_block + ["  };", ""])

    if not use_dhcp:
        block_lines.append(
            "  networking.defaultGateway = {"
            f' address = "{_escape_nix_string(install_network.gateway)}";'
            ' interface = "lan";'
            " };"
        )
        block_lines.append("")

    link_match_lines: list[str] = []
    if lan.mac_address:
        link_match_lines.append(
            f'    matchConfig.MACAddress = "{_escape_nix_string(lan.mac_address)}";'
        )
    else:
        fallback_name = original_name or lan.interface or "lan"
        link_match_lines.append(
            f'    matchConfig.OriginalName = "{_escape_nix_string(fallback_name)}";'
        )

    link_unit_name = (
        lan.rename_rule.stem if lan.rename_rule is not None else "lan"
    )
    # Double "{" is required in the f-string to emit a single "{" in the
    # generated Nix attribute set.
    block_lines.append(
        f'  systemd.network.links."{_escape_nix_string(link_unit_name)}" = {{'
    )
    block_lines.extend(link_match_lines)
    block_lines.extend(
        [
            '    linkConfig.Name = "lan";',
            "  };",
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
            f"  boot.kernelParams = {_format_nix_list(effective_console_kernel_params)};",
            *boot_platform.loader_config_lines(boot_setup),
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


# The names network.configure_lan gives the installer's units; older
# pre-nixos versions copied them into the target.
_INSTALLER_UNIT_NAMES = ("10-lan.link", "20-lan.network")


def _remove_installer_units(target_dir: Path, lan: LanConfiguration) -> list[Path]:
    """Remove copies of the installer's network units from the target.

    Only pre-nixos's own names (and those of ``lan``'s files) are touched;
    other files in ``target_dir`` are kept.  Returns the removed paths.
    """

    names = set(_INSTALLER_UNIT_NAMES)
    for source in (lan.rename_rule, lan.network_unit):
        if source is not None:
            names.add(source.name)
    removed: list[Path] = []
    for name in sorted(names):
        candidate = target_dir / name
        if candidate.is_file() and not candidate.is_symlink():
            candidate.unlink()
            removed.append(candidate)
    return removed


def _format_timestamp(moment: datetime) -> str:
    """Return ``moment`` formatted as an ISO-like UTC string."""

    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=timezone.utc)
    return moment.astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M:%SZ")


def _announce(message: str, *, to_stderr: bool = False) -> Tuple[bool, Dict[str, bool]] | None:
    """Print ``message``, and broadcast it to the consoles unless stdout is a
    terminal: there the reader already sees it, and on the serial console the
    terminal is ``/dev/console``, so a broadcast showed it twice (task queue
    item 40; #327, item 36).  ``None`` when nothing was broadcast."""

    print(message, file=sys.stderr if to_stderr else sys.stdout)
    if console.stdout_is_terminal():
        return None
    return _broadcast_install_message(message)


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


def _refuse_legacy_bios(
    boot_setup: boot_platform.BootSetup,
    storage_plan: Optional[Dict[str, Any]],
    *,
    status_dir: Path,
) -> Optional[AutoInstallResult]:
    """Record and announce a legacy-BIOS refusal (task queue item 33, R-B4)."""

    message = boot_platform.legacy_bios_refusal(boot_setup, _plan_boot_disks(storage_plan))
    if message is None:
        return None
    _announce(message)
    return _record_result(
        "failed",
        status_dir=status_dir,
        reason="bios-unsupported",
        details={"message": message},
    )


def refuse_unconfirmed_disks(
    message: str, *, status_dir: Optional[Path] = None
) -> AutoInstallResult:
    """Record and announce that disks need the user's answer first (R-S3).

    Nothing was provisioned or installed; the run waits for the user, so the
    install is ``skipped``, not ``failed``.
    """

    _announce(message, to_stderr=True)
    return _record_result(
        "skipped",
        status_dir=status_dir if status_dir is not None else state.default_state_dir(),
        reason=disk_class.UNCONFIRMED_REASON,
        details={"message": message},
    )


def legacy_bios_preflight(
    storage_plan: Dict[str, Any], *, status_dir: Optional[Path] = None
) -> Optional[AutoInstallResult]:
    """Refuse an auto-install that ``storage_plan`` cannot make bootable on a
    legacy-BIOS machine, **before** storage is provisioned for it; ``None``
    when the install may go ahead.

    An invalid boot declaration is left to :func:`auto_install` to report.
    """

    try:
        boot_setup = boot_platform.current_setup()
    except ValueError:
        return None
    return _refuse_legacy_bios(
        boot_setup,
        storage_plan,
        status_dir=status_dir if status_dir is not None else state.default_state_dir(),
    )


class InstallTrigger(enum.Enum):
    """Why an install runs (task queue item 44).

    ``AUTOMATIC``: after provisioning, because auto-install is enabled (the
    boot service, ``pre-nixos``, the TUI's Apply).  It waits for the network.
    ``REQUESTED``: the user asked for it (``--install-now``, the TUI's ``N``);
    it runs regardless, with a warning.
    """

    AUTOMATIC = "automatic"
    REQUESTED = "requested"


def _network_gate(trigger: InstallTrigger, status_dir: Path) -> Optional[AutoInstallResult]:
    """Skip an automatic install while the installer has no address and
    default route; ``None`` when the install may go ahead."""

    readiness = network.installer_network()
    log_event(
        "pre_nixos.install.network_readiness",
        trigger=trigger.value,
        address=readiness.address,
        gateway=readiness.gateway,
    )
    if readiness.ready:
        return None
    if trigger is InstallTrigger.REQUESTED:
        print(f"Warning: {readiness.problem}; the install may fail to download packages.")
        return None
    message = (
        f"Auto-install skipped: {readiness.problem} (it needs an IPv4 address and a "
        "default route). Configure the network, then run pre-nixos --install-now, "
        "or press N in pre-nixos-tui."
    )
    _announce(message)
    return _record_result(
        "skipped",
        status_dir=status_dir,
        reason="no-network",
        details={"message": message},
    )


def auto_install(
    lan: Optional[LanConfiguration],
    storage_plan: Optional[Dict[str, Any]] = None,
    *,
    install_network: Optional[InstallNetworkConfig] = None,
    enabled: bool = True,
    trigger: InstallTrigger = InstallTrigger.AUTOMATIC,
    dry_run: bool = False,
    root_path: Path = Path("/mnt"),
    status_dir: Path = Path("/run/pre-nixos"),
    mount_attempts: int = 30,
    mount_delay: float = 1.0,
    root_password_file: Path = root_password.EMBEDDED_FILE,
) -> AutoInstallResult:
    """Automatically install NixOS when prerequisites are satisfied.

    ``root_password_file``: the image's hashed root password (reqs R-A1); a
    missing file means the site set none.
    """

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

    if install_network is None:
        install_network = load_install_network_config(state_dir=status_dir)

    execute = os.environ.get("PRE_NIXOS_EXEC") == "1"
    if dry_run:
        return _record_result("skipped", status_dir=status_dir, reason="dry-run")
    if not execute:
        return _record_result(
            "skipped",
            status_dir=status_dir,
            reason="execution-disabled",
        )

    # Task queue item 44 (user decision b): an automatic install waits for an
    # IPv4 address and a default route; nothing on /mnt is touched before.
    gated = _network_gate(trigger, status_dir)
    if gated is not None:
        return gated

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

    # R-A2: nix/site.nix validated the hash when the image was built; a bad
    # one here means a broken image, so nothing on /mnt is touched.
    try:
        root_hash = root_password.load_embedded(root_password_file)
    except (root_password.InvalidRootHash, OSError, UnicodeDecodeError) as exc:
        log_event("pre_nixos.install.root_password_invalid", error=type(exc).__name__)
        return _record_result(
            "failed",
            status_dir=status_dir,
            reason="root-password-invalid",
        )
    log_event("pre_nixos.install.root_password", set=root_hash is not None)

    try:
        boot_setup = boot_platform.current_setup()
    except ValueError as exc:
        log_event("pre_nixos.install.installed_boot_invalid", error=str(exc))
        return _record_result(
            "failed",
            status_dir=status_dir,
            reason="installed-boot-config",
        )
    log_event(
        "pre_nixos.install.installed_boot",
        kind=boot_setup.kind.value,
        rpi_firmware=boot_setup.rpi_firmware,
    )

    refused = _refuse_legacy_bios(boot_setup, storage_plan, status_dir=status_dir)
    if refused is not None:
        return refused

    if not _wait_for_mount(root_path, attempts=mount_attempts, delay=mount_delay):
        return _record_result(
            "failed",
            status_dir=status_dir,
            reason="mount-unavailable",
        )

    # R-B2 (AArch64 plan item 9): on a Pi the target must boot before the SD
    # card, or the board would boot the installer again.  Checked before
    # anything is installed.
    if boot_setup.kind is boot_platform.InstalledBoot.RPI4_UBOOT_EXTLINUX:
        verdict = boot_order.verify_for_install(root_path)
        log_event("pre_nixos.install.boot_order", verdict=repr(verdict))
        if isinstance(verdict, boot_order.Refused):
            message = boot_order.describe_refusal(verdict)
            _announce(message)
            return _record_result(
                "failed",
                status_dir=status_dir,
                reason="boot-order",
                details={"message": message},
            )

    start_time = datetime.now(timezone.utc)
    start_message = (
        "Starting automatic NixOS installation at "
        f"{_format_timestamp(start_time)} UTC."
    )
    _announce(start_message)

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

    console_kernel_params = _select_console_kernel_params()
    log_event(
        "pre_nixos.install.console_policy",
        kernel_params=console_kernel_params,
    )

    try:
        _inject_configuration(
            root_path,
            key_text,
            lan,
            storage_plan,
            install_network,
            console_kernel_params,
            boot_setup,
            [_stable_disk_path(disk) for disk in _plan_boot_disks(storage_plan)]
            if boot_setup.kind is boot_platform.InstalledBoot.X86_BIOS_GRUB
            else (),
            root_hash,
        )
        _rewrite_hardware_configuration(root_path)
    except Exception as exc:  # pragma: no cover - unexpected filesystem errors
        log_event("pre_nixos.install.configuration_write_failed", error=str(exc))
        return _record_result(
            "failed",
            status_dir=status_dir,
            reason="configuration-write",
        )

    # #342: the target's network comes from the managed block alone, which
    # declares the rename (systemd.network.links) and the network.  The
    # installer's own units are not copied, and copies an earlier attempt
    # left are removed: NixOS does not manage these names, and "20-lan.network"
    # (the installer's DHCP unit) sorts before the declared units, so a
    # leftover silently overrode a static address.
    try:
        removed = _remove_installer_units(root_path / "etc/systemd/network", lan)
    except OSError as exc:
        log_event("pre_nixos.install.network_unit_cleanup_failed", error=str(exc))
        return _record_result(
            "failed",
            status_dir=status_dir,
            reason="network-unit-cleanup",
        )
    if removed:
        log_event("pre_nixos.install.stale_network_units_removed", files=[str(p) for p in removed])

    # Design D4: with mutable users NixOS applies hashedPassword only to a new
    # shadow entry, so an earlier attempt's /etc/shadow would keep root locked.
    if root_hash is not None:
        try:
            shadow_changed = root_password.apply_to_shadow_file(root_path / "etc/shadow", root_hash)
        except OSError as exc:
            log_event("pre_nixos.install.root_password_shadow_failed", error=str(exc))
            return _record_result(
                "failed",
                status_dir=status_dir,
                reason="root-password-shadow",
            )
        log_event("pre_nixos.install.root_password_shadow", changed=shadow_changed)

    try:
        boot_files = boot_platform.install_boot_files(boot_setup, root_path)
    except (OSError, RuntimeError) as exc:
        log_event("pre_nixos.install.boot_files_failed", error=str(exc))
        return _record_result(
            "failed",
            status_dir=status_dir,
            reason="boot-files",
        )
    if boot_files:
        log_event("pre_nixos.install.boot_files_copied", count=len(boot_files))

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
    completion_broadcast = _announce(completion_message)

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
