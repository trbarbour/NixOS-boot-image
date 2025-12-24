"""Utilities for capturing and annotating VM diagnostic metadata."""

from __future__ import annotations

import datetime
import json
from pathlib import Path
from typing import TYPE_CHECKING, Dict, List, Optional

REPO_ROOT = Path(__file__).resolve().parents[2]

DMESG_CAPTURE_COMMAND = "dmesg --color=never 2>&1 || dmesg 2>&1 || true"

if TYPE_CHECKING:  # pragma: no cover - type checking only
    from tests.vm.fixtures import BootImageBuild
    from tests.vm.fixtures import RunTimings


def write_boot_image_metadata(
    metadata_path: Path,
    *,
    artifact: "BootImageBuild",
    harness_log: Path,
    serial_log: Path,
    qemu_command: List[str],
    qemu_version: Optional[str] = None,
    disk_image: Path,
    extra_disks: Optional[List[Path]] = None,
    ssh_host: str,
    ssh_port: int,
    ssh_executable: str,
    started_at: Optional[datetime.datetime] = None,
    completed_at: Optional[datetime.datetime] = None,
    run_timings: Optional["RunTimings"] = None,
) -> None:
    """Persist structured metadata describing the active BootImageVM session."""

    log_dir = metadata_path.parent
    diagnostics_dir = log_dir / "diagnostics"
    diagnostics_dir.mkdir(parents=True, exist_ok=True)
    metadata: Dict[str, object] = {
        "generated_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "artifact": {
            "iso_path": str(artifact.iso_path),
            "store_path": str(artifact.store_path),
            "deriver": artifact.deriver,
            "nar_hash": artifact.nar_hash,
            "root_key_fingerprint": artifact.root_key_fingerprint,
        },
        "logs": {
            "harness": str(harness_log),
            "serial": str(serial_log),
        },
        "qemu": {
            "command": qemu_command,
            "disk_image": str(disk_image),
        },
        "ssh": {
            "host": ssh_host,
            "port": ssh_port,
            "executable": ssh_executable,
        },
        "diagnostics": {
            "directory": str(diagnostics_dir),
            "artifacts": [],
        },
    }
    if extra_disks:
        metadata["qemu"]["extra_disks"] = [str(path) for path in extra_disks]
    if qemu_version:
        metadata["qemu"]["version"] = qemu_version
    if started_at:
        metadata["timings"] = {
            "start": started_at.isoformat(),
            "end": (completed_at or datetime.datetime.now(datetime.timezone.utc)).isoformat(),
        }
    elif run_timings:
        timings = run_timings.to_metadata()
        if timings:
            metadata["timings"] = timings
    metadata_path.write_text(
        json.dumps(metadata, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def record_boot_image_diagnostic(
    metadata_path: Path,
    *,
    label: str,
    path: Path,
) -> None:
    """Append a diagnostic artifact entry to ``metadata.json`` when available."""

    try:
        raw_metadata = metadata_path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return

    if not raw_metadata.strip():
        return

    try:
        metadata = json.loads(raw_metadata)
    except json.JSONDecodeError:
        return

    diagnostics = metadata.setdefault("diagnostics", {})
    artifacts = diagnostics.setdefault("artifacts", [])
    entry = {"label": label, "path": str(path)}
    if any(existing.get("path") == entry["path"] for existing in artifacts):
        return

    artifacts.append(entry)
    metadata_path.write_text(
        json.dumps(metadata, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _read_diagnostics(metadata_path: Path) -> List[Dict[str, str]]:
    """Return diagnostic artifact entries from ``metadata.json`` when present."""

    try:
        raw_metadata = metadata_path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return []
    if not raw_metadata.strip():
        return []
    try:
        metadata = json.loads(raw_metadata)
    except json.JSONDecodeError:
        return []
    diagnostics_section = metadata.get("diagnostics")
    if not isinstance(diagnostics_section, dict):
        return []
    artifacts = diagnostics_section.get("artifacts")
    if not isinstance(artifacts, list):
        return []
    entries: List[Dict[str, str]] = []
    for artifact in artifacts:
        label = artifact.get("label") if isinstance(artifact, dict) else None
        path = artifact.get("path") if isinstance(artifact, dict) else None
        if isinstance(label, str) and isinstance(path, str):
            entries.append({"label": label, "path": path})
    return entries


def record_run_timings(
    metadata_path: Path, *, run_timings: "RunTimings"
) -> None:
    """Merge timing measurements into the metadata file without dropping diagnostics."""

    try:
        raw_metadata = metadata_path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return

    if not raw_metadata.strip():
        return

    try:
        metadata = json.loads(raw_metadata)
    except json.JSONDecodeError:
        return

    timings = run_timings.to_metadata()
    if not timings:
        return

    existing = metadata.get("timings", {})
    merged = {**existing, **timings}
    metadata["timings"] = merged
    metadata_path.write_text(
        json.dumps(metadata, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def append_run_ledger_entry(
    ledger_path: Path,
    *,
    metadata_path: Path,
    run_timings: "RunTimings",
    harness_log: Path,
    serial_log: Path,
    qemu_command: List[str],
    qemu_version: Optional[str],
    ssh_host: str,
    ssh_port: int,
    invocation_args: List[str],
    spawn_timeout: int,
    login_timeout: int,
    outcome: str,
) -> None:
    """Append a JSON line capturing a VM test attempt to the run ledger.

    The ledger is stored under ``notes/`` by default so that timing and
    diagnostic metadata can be reviewed across sessions without trawling
    through temporary directories. Entries are additive and should not be
    rewritten.
    """

    entry: Dict[str, object] = {
        "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "metadata": str(metadata_path),
        "harness_log": str(harness_log),
        "serial_log": str(serial_log),
        "ssh": {"host": ssh_host, "port": ssh_port},
        "qemu": {"command": qemu_command, "version": qemu_version},
        "pytest_args": invocation_args,
        "timeouts": {
            "spawn_seconds": spawn_timeout,
            "login_seconds": login_timeout,
        },
        "outcome": outcome,
    }
    timings = run_timings.to_metadata()
    if timings:
        entry["timings"] = timings
        total_seconds = timings.get("total_seconds")
        if isinstance(total_seconds, (int, float)):
            entry["session_ceiling_exceeded"] = total_seconds >= 3600
    diagnostics = _read_diagnostics(metadata_path)
    if diagnostics:
        entry["diagnostics"] = diagnostics

    ledger_path = ledger_path.resolve()
    if not ledger_path.is_absolute():  # pragma: no cover - defensive fallback
        ledger_path = (REPO_ROOT / ledger_path).resolve()
    ledger_path.parent.mkdir(parents=True, exist_ok=True)
    with ledger_path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(entry, sort_keys=True) + "\n")


__all__ = [
    "DMESG_CAPTURE_COMMAND",
    "append_run_ledger_entry",
    "record_run_timings",
    "record_boot_image_diagnostic",
    "write_boot_image_metadata",
]
