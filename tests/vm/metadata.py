"""Utilities for capturing and annotating VM diagnostic metadata."""

from __future__ import annotations

import datetime
import json
from pathlib import Path
from typing import TYPE_CHECKING, Dict, List, Optional

DMESG_CAPTURE_COMMAND = "dmesg --color=never 2>&1 || dmesg 2>&1 || true"

if TYPE_CHECKING:  # pragma: no cover - type checking only
    from tests.vm.fixtures import BootImageBuild


def write_boot_image_metadata(
    metadata_path: Path,
    *,
    artifact: "BootImageBuild",
    harness_log: Path,
    serial_log: Path,
    qemu_command: List[str],
    qemu_version: Optional[str] = None,
    disk_image: Path,
    ssh_host: str,
    ssh_port: int,
    ssh_executable: str,
    started_at: Optional[datetime.datetime] = None,
    completed_at: Optional[datetime.datetime] = None,
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
    if qemu_version:
        metadata["qemu"]["version"] = qemu_version
    if started_at:
        metadata["timings"] = {
            "start": started_at.isoformat(),
            "end": (completed_at or datetime.datetime.now(datetime.timezone.utc)).isoformat(),
        }
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


__all__ = [
    "DMESG_CAPTURE_COMMAND",
    "record_boot_image_diagnostic",
    "write_boot_image_metadata",
]
