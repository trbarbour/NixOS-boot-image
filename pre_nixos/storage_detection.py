"""Detection helpers for existing storage signatures."""

from __future__ import annotations

from dataclasses import dataclass
import os
import subprocess
import sys
from typing import Callable, Iterable, Optional, Sequence

__all__ = [
    "CommandOutput",
    "DetectionEnvironment",
    "resolve_boot_disk",
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


_IGNORED_DEVICE_PREFIXES = (
    "/dev/loop",
    "/dev/zram",
    "/dev/ram",
    "/dev/dm",
    "/dev/md",
    "/dev/sr",
)


# ``lsblk`` and ``wipefs`` return 32 when the target device disappears between
# discovery and inspection.  Treat these transient errors as ignorable so that
# storage detection remains resilient to short-lived devices, mirroring the
# behaviour of udev when devices are unplugged mid-operation.
_IGNORABLE_RETURN_CODES = {32}


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


def resolve_boot_disk(env: DetectionEnvironment | None = None) -> Optional[str]:
    """Determine the disk that hosts the boot media, if possible."""

    env = env or DetectionEnvironment()

    for arg in env.read_cmdline():
        for prefix, base in _BOOT_ARG_PREFIXES.items():
            if not arg.startswith(prefix):
                continue
            candidate = base + arg[len(prefix) :]
            if not env.path_exists(candidate):
                continue
            boot_device = env.realpath(candidate)
            parent = _run_command(
                env, ["lsblk", "-npo", "PKNAME", boot_device], ignore_errors=True
            ).strip()
            if parent:
                return env.realpath(f"/dev/{parent}")
            return boot_device

    boot_source = _run_command(
        env, ["findmnt", "-n", "-o", "SOURCE", "/iso"], ignore_errors=True
    ).strip()
    if boot_source and env.path_exists(boot_source):
        parent = _run_command(
            env, ["lsblk", "-npo", "PKNAME", boot_source], ignore_errors=True
        ).strip()
        if parent:
            return env.realpath(f"/dev/{parent}")
        return env.realpath(boot_source)

    return None


def _iter_lsblk_rows(output: str) -> Iterable[tuple[str, str]]:
    for line in output.splitlines():
        if not line.strip():
            continue
        parts = line.split()
        if len(parts) != 2:
            continue
        yield parts[0], parts[1]


def has_existing_storage(
    env: DetectionEnvironment | None = None,
    *,
    boot_disk: Optional[str] = None,
) -> bool:
    """Return True when non-boot disks contain partitions or signatures."""

    env = env or DetectionEnvironment()
    listing = _run_command(env, ["lsblk", "-dnpo", "NAME,TYPE"])
    for device, dev_type in _iter_lsblk_rows(listing):
        if dev_type != "disk":
            continue
        if device.startswith(_IGNORED_DEVICE_PREFIXES):
            continue
        resolved = env.realpath(device)
        if boot_disk and resolved == boot_disk:
            continue
        type_result = env.run(["lsblk", "-rno", "TYPE", device])
        if type_result.returncode in _IGNORABLE_RETURN_CODES:
            continue
        if type_result.returncode != 0:
            raise RuntimeError(
                f"command lsblk -rno TYPE {device} exited with status "
                f"{type_result.returncode}"
            )
        type_listing = type_result.stdout
        type_lines = [line for line in type_listing.splitlines() if line.strip()]
        if len(type_lines) > 1:
            return True
        wipefs_result = env.run(["wipefs", "-n", device])
        if wipefs_result.returncode in _IGNORABLE_RETURN_CODES:
            continue
        if wipefs_result.returncode != 0:
            raise RuntimeError(
                f"command wipefs -n {device} exited with status "
                f"{wipefs_result.returncode}"
            )
        if wipefs_result.stdout.strip():
            return True
    return False


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
