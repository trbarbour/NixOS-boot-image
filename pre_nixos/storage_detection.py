"""Detection helpers for existing storage signatures."""

from __future__ import annotations

from dataclasses import dataclass
import os
import subprocess
import sys
from typing import Callable, Iterable, Optional, Sequence

from .logging_utils import log_event

__all__ = [
    "CommandOutput",
    "DetectionEnvironment",
    "ExistingStorageDevice",
    "detect_existing_storage",
    "format_existing_storage_reasons",
    "collect_boot_probe_data",
    "resolve_boot_disk",
    "scan_existing_storage",
    "has_existing_storage",
    "main",
]


@dataclass
class CommandOutput:
    """Minimal command result container for dependency injection."""

    stdout: str
    returncode: int = 0


class DetectionEnvironment:
    """Encapsulate external interactions for storage detection."""

    def __init__(
        self,
        *,
        run: Callable[[Sequence[str]], CommandOutput] | None = None,
        path_exists: Callable[[str], bool] | None = None,
        realpath: Callable[[str], str] | None = None,
        read_cmdline: Callable[[], Sequence[str]] | None = None,
    ) -> None:
        self.run = run or self._default_run
        self.path_exists = path_exists or os.path.exists
        self.realpath = realpath or os.path.realpath
        self.read_cmdline = read_cmdline or self._default_read_cmdline

    @staticmethod
    def _default_run(cmd: Sequence[str]) -> CommandOutput:
        completed = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            check=False,
        )
        return CommandOutput(stdout=completed.stdout, returncode=completed.returncode)

    @staticmethod
    def _default_read_cmdline() -> Sequence[str]:
        try:
            with open("/proc/cmdline", "r", encoding="utf-8") as fp:
                data = fp.read()
        except OSError:
            return []
        return data.split()


_BOOT_ARG_PREFIXES = {
    "boot=LABEL=": "/dev/disk/by-label/",
    "boot=UUID=": "/dev/disk/by-uuid/",
}


_MOUNT_SOURCE_PREFIXES = {
    "LABEL=": "/dev/disk/by-label/",
    "UUID=": "/dev/disk/by-uuid/",
    "PARTUUID=": "/dev/disk/by-partuuid/",
    "PARTLABEL=": "/dev/disk/by-partlabel/",
}


_IGNORED_DEVICE_PREFIXES = (
    "/dev/loop",
    "/dev/zram",
    "/dev/ram",
    "/dev/dm",
    "/dev/md",
    "/dev/fd",
    "/dev/sr",
)


# ``lsblk`` and ``wipefs`` return 32 when the target device disappears between
# discovery and inspection.  Treat these transient errors as ignorable so that
# storage detection remains resilient to short-lived devices, mirroring the
# behaviour of udev when devices are unplugged mid-operation.
_DISAPPEARED_DEVICE_RETURN_CODES = {32}


@dataclass(frozen=True)
class ExistingStorageDevice:
    """Describe a device that already contains storage metadata."""

    device: str
    reasons: tuple[str, ...]


def _run_command(
    env: DetectionEnvironment, cmd: Sequence[str], *, ignore_errors: bool = False
) -> str:
    result = env.run(cmd)
    if result.returncode != 0:
        if ignore_errors:
            return ""
        raise RuntimeError(
            f"command {' '.join(cmd)} exited with status {result.returncode}"
        )
    return result.stdout


def _candidate_paths_from_source(source: str) -> list[str]:
    """Return potential device paths for a mount *source* string."""

    raw = source.strip()
    if not raw:
        return []

    variations = {
        raw,
        raw.replace("\\040", " "),
        raw.replace("\\040", "\\x20"),
    }
    candidates: list[str] = []
    seen: set[str] = set()
    for variant in variations:
        if not variant:
            continue
        handled_prefix = False
        for prefix, base in _MOUNT_SOURCE_PREFIXES.items():
            if not variant.startswith(prefix):
                continue
            value = variant[len(prefix) :]
            candidate = base + value
            if candidate not in seen:
                candidates.append(candidate)
                seen.add(candidate)
            handled_prefix = True
        if handled_prefix:
            continue
        candidate = variant if variant.startswith("/") else f"/dev/{variant}"
        if candidate not in seen:
            candidates.append(candidate)
            seen.add(candidate)
    return candidates


_BOOT_MOUNT_TARGETS = (
    "/iso",
    "/run/archiso/bootmnt",
    "/nix/.ro-store",
)

_BOOT_FILESYSTEM_TYPES = ("squashfs", "iso9660")


def _resolve_boot_disk_with_probes(
    env: DetectionEnvironment,
) -> tuple[Optional[str], list[dict[str, object]]]:
    probes: list[dict[str, object]] = []

    for arg in env.read_cmdline():
        for prefix, base in _BOOT_ARG_PREFIXES.items():
            if not arg.startswith(prefix):
                continue
            candidate = base + arg[len(prefix) :]
            exists = env.path_exists(candidate)
            resolved_candidate = env.realpath(candidate) if exists else None
            probe: dict[str, object] = {
                "probe": "cmdline",
                "argument": arg,
                "candidate": candidate,
                "exists": exists,
            }
            if not exists:
                probes.append(probe)
                continue
            boot_device = resolved_candidate
            parent = _run_command(
                env, ["lsblk", "-npo", "PKNAME", boot_device], ignore_errors=True
            ).strip()
            resolved_boot = (
                env.realpath(f"/dev/{parent}") if parent else boot_device
            )
            probe["parent"] = parent or None
            probe["resolved"] = resolved_boot
            probes.append(probe)
            return resolved_boot, probes
    sources: list[dict[str, object]] = []
    for target in _BOOT_MOUNT_TARGETS:
        sources.append(
            {
                "probe": "mountpoint",
                "target": target,
                "source": _run_command(
                    env, ["findmnt", "-n", "-o", "SOURCE", target], ignore_errors=True
                ).strip(),
            }
        )
    for fs_type in _BOOT_FILESYSTEM_TYPES:
        listing = _run_command(
            env, ["findmnt", "-nr", "-t", fs_type, "-o", "SOURCE"], ignore_errors=True
        ).strip()
        if listing:
            for source in listing.splitlines():
                sources.append({"probe": "filesystem", "fs_type": fs_type, "source": source})
    for source_info in sources:
        source = str(source_info.get("source", "")).strip()
        candidates_info: list[dict[str, object]] = []
        for candidate in _candidate_paths_from_source(source):
            exists = env.path_exists(candidate)
            resolved_candidate = env.realpath(candidate) if exists else None
            candidate_info: dict[str, object] = {
                "candidate": candidate,
                "exists": exists,
            }
            if not exists:
                candidates_info.append(candidate_info)
                continue
            boot_device = resolved_candidate
            parent = _run_command(
                env, ["lsblk", "-npo", "PKNAME", boot_device], ignore_errors=True
            ).strip()
            resolved_boot = (
                env.realpath(f"/dev/{parent}") if parent else boot_device
            )
            candidate_info["parent"] = parent or None
            candidate_info["resolved"] = resolved_boot
            source_info["selected"] = resolved_boot
            candidates_info.append(candidate_info)
            probes.append({**source_info, "candidates": candidates_info})
            return resolved_boot, probes
        probes.append({**source_info, "candidates": candidates_info})
    return None, probes


def collect_boot_probe_data(env: DetectionEnvironment | None = None) -> dict[str, object]:
    env = env or DetectionEnvironment()
    boot_disk, probes = _resolve_boot_disk_with_probes(env)
    return {"boot_disk": boot_disk, "probes": probes}


def resolve_boot_disk(env: DetectionEnvironment | None = None) -> Optional[str]:
    """Determine the disk that hosts the boot media, if possible."""

    env = env or DetectionEnvironment()
    boot_disk, probes = _resolve_boot_disk_with_probes(env)
    log_event("pre_nixos.storage.resolve_boot_disk", boot_disk=boot_disk, probes=probes)
    return boot_disk


def _iter_lsblk_rows(output: str) -> Iterable[tuple[str, str, str | None]]:
    for line in output.splitlines():
        if not line.strip():
            continue
        parts = line.split()
        if len(parts) < 2:
            continue
        removable = parts[2] if len(parts) >= 3 else None
        yield parts[0], parts[1], removable


def scan_existing_storage(
    env: DetectionEnvironment | None = None,
    *,
    boot_disk: Optional[str] = None,
) -> list[ExistingStorageDevice]:
    """Return a list of non-boot disks that contain storage metadata."""

    env = env or DetectionEnvironment()
    listing = _run_command(env, ["lsblk", "-dnpo", "NAME,TYPE,RM"])
    detected: list[ExistingStorageDevice] = []
    for device, dev_type, removable in _iter_lsblk_rows(listing):
        if dev_type != "disk":
            continue
        resolved = env.realpath(device)
        skip_reasons: list[str] = []
        detection_reasons: list[str] = []
        if device.startswith(_IGNORED_DEVICE_PREFIXES):
            skip_reasons.append("ignored_prefix")
        if removable == "1":
            skip_reasons.append("removable_media")
        if boot_disk and resolved == boot_disk:
            skip_reasons.append("boot_disk")
        if skip_reasons:
            log_event(
                "pre_nixos.storage.device_filtered",
                device=device,
                resolved=resolved,
                reasons=skip_reasons,
                removable=removable == "1",
                boot_disk=boot_disk,
            )
            continue
        type_result = env.run(["lsblk", "-rno", "TYPE", device])
        if type_result.returncode in _DISAPPEARED_DEVICE_RETURN_CODES:
            if env.path_exists(device):
                raise RuntimeError(
                    f"command lsblk -rno TYPE {device} exited with status "
                    f"{type_result.returncode} while device still present"
                )
            continue
        if type_result.returncode != 0:
            raise RuntimeError(
                f"command lsblk -rno TYPE {device} exited with status "
                f"{type_result.returncode}"
            )
        type_listing = type_result.stdout
        type_lines = [line for line in type_listing.splitlines() if line.strip()]
        if len(type_lines) > 1:
            detection_reasons.append("partitions")
        wipefs_result = env.run(["wipefs", "-n", device])
        if wipefs_result.returncode in _DISAPPEARED_DEVICE_RETURN_CODES:
            if env.path_exists(device):
                raise RuntimeError(
                    f"command wipefs -n {device} exited with status "
                    f"{wipefs_result.returncode} while device still present"
                )
            continue
        if wipefs_result.returncode != 0:
            raise RuntimeError(
                f"command wipefs -n {device} exited with status "
                f"{wipefs_result.returncode}"
            )
        if wipefs_result.stdout.strip():
            detection_reasons.append("signatures")
        if detection_reasons:
            device_info = ExistingStorageDevice(
                device=resolved, reasons=tuple(detection_reasons)
            )
            detected.append(device_info)
            log_event(
                "pre_nixos.storage.device_detected",
                device=device,
                resolved=resolved,
                reasons=detection_reasons,
                removable=removable == "1",
                boot_disk=boot_disk,
            )
        else:
            log_event(
                "pre_nixos.storage.device_filtered",
                device=device,
                resolved=resolved,
                reasons=["no_signatures"],
                removable=removable == "1",
                boot_disk=boot_disk,
            )
    return detected


def detect_existing_storage(
    env: DetectionEnvironment | None = None,
) -> list[ExistingStorageDevice]:
    """Inspect the system and return devices that contain existing storage."""

    env = env or DetectionEnvironment()
    boot_disk = resolve_boot_disk(env)
    return scan_existing_storage(env, boot_disk=boot_disk)


def format_existing_storage_reasons(reasons: Sequence[str]) -> str:
    """Return a human-readable summary of detection reasons."""

    if not reasons:
        return "unknown"
    return ", ".join(reasons)


def has_existing_storage(
    env: DetectionEnvironment | None = None,
    *,
    boot_disk: Optional[str] = None,
) -> bool:
    """Return True when non-boot disks contain partitions or signatures."""

    return bool(scan_existing_storage(env, boot_disk=boot_disk))


def main(argv: Optional[Sequence[str]] = None) -> int:  # pragma: no cover - thin wrapper
    del argv
    env = DetectionEnvironment()
    try:
        boot_disk = resolve_boot_disk(env)
        if has_existing_storage(env, boot_disk=boot_disk):
            return 0
        return 1
    except Exception as exc:
        print(f"pre-nixos-detect-storage: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
