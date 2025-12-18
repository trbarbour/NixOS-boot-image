"""Utilities for wiping existing storage before applying a plan."""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
import shlex
import subprocess
from typing import Callable, Iterable, List, Mapping, Sequence, Set, Tuple

from . import storage_detection
from .logging_utils import log_event

__all__ = [
    "WIPE_SIGNATURES",
    "DISCARD_BLOCKS",
    "OVERWRITE_RANDOM",
    "SKIP_CLEANUP",
    "CleanupOption",
    "CLEANUP_OPTIONS",
    "perform_storage_cleanup",
]


CommandRunner = Callable[[Sequence[str]], subprocess.CompletedProcess | None]

WIPE_SIGNATURES = "wipe-signatures"
DISCARD_BLOCKS = "discard"
OVERWRITE_RANDOM = "overwrite-random"
SKIP_CLEANUP = "skip"


@dataclass(frozen=True)
class CleanupOption:
    """Choice presented to operators when wiping existing storage."""

    key: str
    action: str | None
    description: str


@dataclass
class StorageNode:
    """A storage element participating in cleanup."""

    name: str
    node_type: str
    fstype: str | None = None
    mountpoints: list[str] = field(default_factory=list)
    parents: set[str] = field(default_factory=set)
    children: set[str] = field(default_factory=set)
    metadata: dict[str, str] = field(default_factory=dict)


CLEANUP_OPTIONS: Tuple[CleanupOption, ...] = (
    CleanupOption(
        "1",
        WIPE_SIGNATURES,
        "Wipe partition tables and filesystem signatures (fast)",
    ),
    CleanupOption(
        "2",
        DISCARD_BLOCKS,
        "Discard all blocks (SSD/NVMe only)",
    ),
    CleanupOption(
        "3",
        OVERWRITE_RANDOM,
        "Overwrite the entire device with random data (slow)",
    ),
    CleanupOption("s", SKIP_CLEANUP, "Skip wiping and continue"),
    CleanupOption("q", None, "Abort without making changes"),
)


def _default_runner(cmd: Sequence[str]) -> subprocess.CompletedProcess:
    """Run *cmd* with output captured to avoid noisy stderr/tty chatter."""

    return subprocess.run(
        cmd,
        check=False,
        capture_output=True,
        text=True,
    )


def _command_to_str(cmd: Sequence[str]) -> str:
    return " ".join(shlex.quote(part) for part in cmd)


def _command_output_fields(result: subprocess.CompletedProcess) -> dict[str, str]:
    """Return a mapping of non-empty output streams for logging."""

    fields = {}
    stdout = (result.stdout or "").strip()
    stderr = (result.stderr or "").strip()
    if stdout:
        fields["stdout"] = stdout
    if stderr:
        fields["stderr"] = stderr
    return fields


def _collect_wipefs_diagnostics(device: str) -> dict[str, object]:
    mounts_result = subprocess.run(
        ["findmnt", "-rn", "-o", "TARGET,SOURCE", "-T", device],
        capture_output=True,
        text=True,
        check=False,
    )
    mount_lines = [line for line in mounts_result.stdout.splitlines() if line.strip()]
    boot_probe_data = storage_detection.collect_boot_probe_data()
    return {"mounts": mount_lines, **boot_probe_data}


def _capture_diagnostic_output(cmd: Sequence[str]) -> str:
    """Return combined stdout/stderr from *cmd* for diagnostics."""

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            check=False,
        )
    except OSError as exc:  # pragma: no cover - defensive
        return f"{cmd[0]}: {exc}"

    output = (result.stdout or "") + (result.stderr or "")
    output = output.strip()
    if output:
        return output
    if result.returncode != 0:
        return f"{cmd[0]} exited with {result.returncode}"
    return ""


def _collect_storage_stack_state() -> dict[str, object]:
    """Return a snapshot of block-layer state for diagnostics."""

    return {
        "lsblk_json": _capture_diagnostic_output(["lsblk", "--output-all", "--json"]),
        "mdadm_detail_scan": _capture_diagnostic_output(["mdadm", "--detail", "--scan"]),
        "dmsetup_tree": _capture_diagnostic_output(["dmsetup", "ls", "--tree"]),
    }


_ALLOWED_NONZERO_EXIT_CODES: Mapping[Tuple[str, ...], Set[int]] = {
    ("sgdisk", "--zap-all"): {2},
    ("partprobe",): {1},
}


def _is_allowed_returncode(cmd: Sequence[str], returncode: int) -> bool:
    """Return ``True`` when *returncode* is acceptable for *cmd*."""

    if returncode == 0:
        return True
    for prefix_length in range(len(cmd), 0, -1):
        key = tuple(cmd[:prefix_length])
        allowed = _ALLOWED_NONZERO_EXIT_CODES.get(key)
        if allowed and returncode in allowed:
            return True
    return False


def _execute_command(
    cmd: Sequence[str],
    *,
    action: str,
    device: str,
    execute: bool,
    runner: CommandRunner,
    scheduled: List[str],
    tolerate_failure: bool = False,
) -> subprocess.CompletedProcess:
    cmd_str = _command_to_str(cmd)
    scheduled.append(cmd_str)
    log_event(
        "pre_nixos.cleanup.command",
        action=action,
        device=device,
        command=cmd_str,
        execute=execute,
    )
    if not execute:
        return subprocess.CompletedProcess(cmd, 0)

    result = runner(cmd)
    if result is None:
        return subprocess.CompletedProcess(cmd, 0)
    if isinstance(result, subprocess.CompletedProcess):
        if not _is_allowed_returncode(cmd, result.returncode):
            if cmd[0] == "wipefs":
                diagnostics = _collect_wipefs_diagnostics(device)
                log_event(
                    "pre_nixos.cleanup.wipefs_failed",
                    action=action,
                    device=device,
                    command=cmd_str,
                    returncode=result.returncode,
                    **_command_output_fields(result),
                    **diagnostics,
                )
            if tolerate_failure:
                log_event(
                    "pre_nixos.cleanup.command_failed",
                    action=action,
                    device=device,
                    command=cmd_str,
                    returncode=result.returncode,
                    **_command_output_fields(result),
                )
                return result
            raise subprocess.CalledProcessError(
                result.returncode,
                cmd_str,
                output=result.stdout,
                stderr=result.stderr,
            )
        if result.returncode != 0:
            log_event(
                "pre_nixos.cleanup.command_nonzero",
                action=action,
                device=device,
                command=cmd_str,
                returncode=result.returncode,
                **_command_output_fields(result),
            )
        return result
    raise TypeError("Command runner must return CompletedProcess or None")


def _run_json_command(cmd: Sequence[str]) -> dict[str, object]:
    result = subprocess.run(cmd, capture_output=True, text=True, check=False)
    if result.returncode != 0:
        return {}
    try:
        return json.loads(result.stdout or "{}")
    except json.JSONDecodeError:
        return {}


def _list_block_devices() -> list[dict[str, object]]:
    result = subprocess.run(
        ["lsblk", "--json", "--paths", "--output-all"],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        return []
    try:
        parsed = json.loads(result.stdout or "{}")
    except json.JSONDecodeError:
        return []
    devices = parsed.get("blockdevices")
    return devices if isinstance(devices, list) else []


def _list_pvs() -> list[dict[str, object]]:
    data = _run_json_command(["pvs", "--reportformat", "json", "-o", "pv_name,vg_name"])
    records: list[dict[str, object]] = []
    for report in data.get("report", []) or []:
        for pv in report.get("pv", []) or []:
            if isinstance(pv, dict):
                records.append(pv)
    return records


def _list_vgs() -> list[dict[str, object]]:
    data = _run_json_command(["vgs", "--reportformat", "json", "-o", "vg_name"])
    records: list[dict[str, object]] = []
    for report in data.get("report", []) or []:
        for vg in report.get("vg", []) or []:
            if isinstance(vg, dict):
                records.append(vg)
    return records


def _list_lvs() -> list[dict[str, object]]:
    data = _run_json_command(["lvs", "--reportformat", "json", "-o", "lv_path,vg_name"])
    records: list[dict[str, object]] = []
    for report in data.get("report", []) or []:
        for lv in report.get("lv", []) or []:
            if isinstance(lv, dict):
                records.append(lv)
    return records


def _list_losetup() -> list[dict[str, object]]:
    data = _run_json_command(["losetup", "--list", "--json"])
    loopdevices: list[dict[str, object]] = []
    devices = data.get("loopdevices")
    if isinstance(devices, list):
        loopdevices = [entry for entry in devices if isinstance(entry, dict)]
    return loopdevices


def _flatten_lsblk(entry: dict[str, object], parents: list[str]) -> Iterable[dict[str, object]]:
    name = str(entry.get("name", ""))
    children = entry.get("children") or []
    mountpoints: list[str] = []
    raw_mount = entry.get("mountpoint")
    if isinstance(raw_mount, str) and raw_mount:
        mountpoints.append(raw_mount)
    raw_mounts = entry.get("mountpoints")
    if isinstance(raw_mounts, list):
        mountpoints.extend(str(item) for item in raw_mounts if item)
    record = {
        "name": name,
        "type": entry.get("type"),
        "mountpoints": mountpoints,
        "pkname": entry.get("pkname"),
        "fstype": entry.get("fstype"),
        "parents": list(parents),
    }
    yield record
    for child in children:
        if isinstance(child, dict):
            yield from _flatten_lsblk(child, parents + [name])


def _build_storage_graph() -> dict[str, StorageNode]:
    nodes: dict[str, StorageNode] = {}

    def ensure_node(name: str, node_type: str | None = None) -> StorageNode:
        node = nodes.get(name)
        if node is None:
            node = StorageNode(name=name, node_type=node_type or "unknown")
            nodes[name] = node
        elif node_type and node.node_type == "unknown":
            node.node_type = node_type
        return node

    for entry in _list_block_devices():
        for flat in _flatten_lsblk(entry, []):
            name = flat.get("name")
            if not isinstance(name, str) or not name:
                continue
            node = ensure_node(name, str(flat.get("type") or "unknown"))
            if flat.get("fstype"):
                node.fstype = str(flat.get("fstype"))
            node.mountpoints = list({*node.mountpoints, *flat.get("mountpoints", [])})
            parents = flat.get("parents", []) or []
            if parents:
                parent = str(parents[-1])
                parent_node = ensure_node(parent)
                parent_node.children.add(node.name)
                node.parents.add(parent_node.name)
            pkname = flat.get("pkname")
            if pkname:
                parent_node = ensure_node(str(pkname))
                parent_node.children.add(node.name)
                node.parents.add(parent_node.name)

    vg_nodes: dict[str, StorageNode] = {}
    for vg in _list_vgs():
        vg_name = str(vg.get("vg_name") or "")
        if not vg_name:
            continue
        vg_node = ensure_node(f"lvm-vg:{vg_name}", "lvm_vg")
        vg_node.metadata["vg_name"] = vg_name
        vg_nodes[vg_name] = vg_node

    for pv in _list_pvs():
        pv_name = str(pv.get("pv_name") or "")
        vg_name = str(pv.get("vg_name") or "")
        if not pv_name or not vg_name:
            continue
        pv_node = ensure_node(pv_name)
        pv_node.metadata["vg_name"] = vg_name
        vg_node = vg_nodes.get(vg_name) or ensure_node(f"lvm-vg:{vg_name}", "lvm_vg")
        vg_node.metadata["vg_name"] = vg_name
        pv_node.children.add(vg_node.name)
        vg_node.parents.add(pv_node.name)

    for lv in _list_lvs():
        lv_name = str(lv.get("lv_path") or "")
        vg_name = str(lv.get("vg_name") or "")
        if not lv_name or not vg_name:
            continue
        lv_node = ensure_node(lv_name, "lvm_lv")
        lv_node.metadata["vg_name"] = vg_name
        vg_node = vg_nodes.get(vg_name) or ensure_node(f"lvm-vg:{vg_name}", "lvm_vg")
        vg_node.metadata["vg_name"] = vg_name
        vg_node.children.add(lv_node.name)
        lv_node.parents.add(vg_node.name)

    loop_data = _list_losetup()
    for loop_entry in loop_data:
        loop_name = str(loop_entry.get("name") or "")
        backing = str(loop_entry.get("back-file") or "")
        if not loop_name or not backing:
            continue
        loop_node = ensure_node(loop_name, "loop")
        file_node = ensure_node(backing, "file")
        file_node.children.add(loop_node.name)
        loop_node.parents.add(file_node.name)

    return nodes


def _build_device_hierarchy() -> tuple[list[dict[str, object]], dict[str, list[dict[str, object]]]]:
    """Compatibility wrapper returning flattened lsblk data and children mapping."""

    entries: list[dict[str, object]] = []
    for entry in _list_block_devices():
        entries.extend(_flatten_lsblk(entry, []))

    children: dict[str, list[dict[str, object]]] = {}
    for entry in entries:
        parents = entry.get("parents", []) or []
        if parents:
            parent = parents[-1]
            children.setdefault(parent, []).append(entry)

    return entries, children


def _reachable_nodes(graph: dict[str, StorageNode], roots: Sequence[str]) -> set[str]:
    reachable: set[str] = set()

    def visit(name: str) -> None:
        if name in reachable:
            return
        reachable.add(name)
        node = graph.get(name)
        if not node:
            return
        for child in node.children:
            visit(child)

    for root in roots:
        visit(root)
    return reachable


def _compute_depths(graph: dict[str, StorageNode], subset: set[str]) -> dict[str, int]:
    depths: dict[str, int] = {}
    visiting: set[str] = set()

    def depth(name: str) -> int:
        if name in depths:
            return depths[name]
        if name in visiting:
            return 0
        visiting.add(name)
        node = graph.get(name)
        child_depths = [depth(child) for child in (node.children if node else []) if child in subset]
        visiting.remove(name)
        value = 0 if not child_depths else 1 + max(child_depths)
        depths[name] = value
        return value

    for name in subset:
        depth(name)
    return depths


def _ordered_nodes_leaf_to_root(graph: dict[str, StorageNode], subset: set[str]) -> list[str]:
    depths = _compute_depths(graph, subset)
    return sorted(subset, key=lambda name: (depths.get(name, 0), name))


def _is_swap_node(node: StorageNode) -> bool:
    return node.fstype == "swap" or any(mp == "[SWAP]" for mp in node.mountpoints)


def _is_raid_node(node: StorageNode) -> bool:
    node_type = node.node_type or ""
    return node_type.startswith("raid") or node.name.startswith("/dev/md") or node.fstype == "linux_raid_member"


def _is_dm_node(node: StorageNode) -> bool:
    return node.node_type in {"crypt", "dm"} or node.name.startswith("/dev/dm")


def _teardown_node(
    action: str,
    device: str,
    node: StorageNode,
    *,
    execute: bool,
    runner: CommandRunner,
    scheduled: List[str],
) -> bool:
    success = True
    for mountpoint in list(dict.fromkeys(node.mountpoints)):
        result = _execute_command(
            ["umount", mountpoint],
            action=action,
            device=device,
            execute=execute,
            runner=runner,
            scheduled=scheduled,
            tolerate_failure=True,
        )
        if result.returncode != 0:
            success = False

    if _is_swap_node(node):
        result = _execute_command(
            ["swapoff", node.name],
            action=action,
            device=device,
            execute=execute,
            runner=runner,
            scheduled=scheduled,
            tolerate_failure=True,
        )
        if result.returncode != 0:
            success = False

    if node.node_type in {"lvm", "lvm_lv"}:
        result = _execute_command(
            ["lvchange", "-an", node.name],
            action=action,
            device=device,
            execute=execute,
            runner=runner,
            scheduled=scheduled,
            tolerate_failure=True,
        )
        if result.returncode != 0:
            success = False

    if node.node_type == "lvm_vg":
        vg_name = node.metadata.get("vg_name", node.name.replace("lvm-vg:", ""))
        result = _execute_command(
            ["vgchange", "-an", vg_name],
            action=action,
            device=device,
            execute=execute,
            runner=runner,
            scheduled=scheduled,
            tolerate_failure=True,
        )
        if result.returncode != 0:
            success = False

    if _is_raid_node(node):
        result = _execute_command(
            ["mdadm", "--stop", node.name],
            action=action,
            device=device,
            execute=execute,
            runner=runner,
            scheduled=scheduled,
            tolerate_failure=True,
        )
        if result.returncode != 0:
            success = False

    if _is_dm_node(node):
        result = _execute_command(
            ["dmsetup", "remove", node.name],
            action=action,
            device=device,
            execute=execute,
            runner=runner,
            scheduled=scheduled,
            tolerate_failure=True,
        )
        if result.returncode != 0:
            success = False

    if node.node_type == "loop":
        result = _execute_command(
            ["losetup", "-d", node.name],
            action=action,
            device=device,
            execute=execute,
            runner=runner,
            scheduled=scheduled,
            tolerate_failure=True,
        )
        if result.returncode != 0:
            success = False

    return success


def _teardown_graph(
    action: str,
    device: str,
    nodes: list[str],
    graph: dict[str, StorageNode],
    *,
    execute: bool,
    runner: CommandRunner,
    scheduled: List[str],
) -> bool:
    success = True
    for name in nodes:
        node = graph.get(name)
        if not node:
            continue
        node_success = _teardown_node(
            action,
            device,
            node,
            execute=execute,
            runner=runner,
            scheduled=scheduled,
        )
        if not node_success:
            success = False
    if not success:
        log_event(
            "pre_nixos.cleanup.teardown_failed",
            action=action,
            device=device,
            execute=execute,
            **_collect_storage_stack_state(),
        )
    return success


def _wipe_descendant_metadata_graph(
    action: str,
    device: str,
    nodes: list[str],
    graph: dict[str, StorageNode],
    *,
    execute: bool,
    runner: CommandRunner,
    scheduled: List[str],
) -> bool:
    success = True
    for name in nodes:
        node = graph.get(name)
        if not node:
            continue
        if node.node_type == "file":
            continue
        if node.node_type in {"lvm", "lvm_lv"}:
            result = _execute_command(
                ["wipefs", "-a", node.name],
                action=action,
                device=device,
                execute=execute,
                runner=runner,
                scheduled=scheduled,
                tolerate_failure=True,
            )
            if result.returncode != 0:
                success = False
            result = _execute_command(
                ["lvremove", "-fy", node.name],
                action=action,
                device=device,
                execute=execute,
                runner=runner,
                scheduled=scheduled,
                tolerate_failure=True,
            )
            if result.returncode != 0:
                success = False
            continue
        if node.node_type == "lvm_vg":
            vg_name = node.metadata.get("vg_name", node.name.replace("lvm-vg:", ""))
            result = _execute_command(
                ["vgremove", "-ff", "-y", vg_name],
                action=action,
                device=device,
                execute=execute,
                runner=runner,
                scheduled=scheduled,
                tolerate_failure=True,
            )
            if result.returncode != 0:
                success = False
            continue
        if node.metadata.get("vg_name"):
            result = _execute_command(
                ["pvremove", "-ff", "-y", node.name],
                action=action,
                device=device,
                execute=execute,
                runner=runner,
                scheduled=scheduled,
                tolerate_failure=True,
            )
            if result.returncode != 0:
                success = False
        if _is_raid_node(node):
            result = _execute_command(
                ["mdadm", "--zero-superblock", "--force", node.name],
                action=action,
                device=device,
                execute=execute,
                runner=runner,
                scheduled=scheduled,
                tolerate_failure=True,
            )
            if result.returncode != 0:
                success = False
        result = _execute_command(
            ["wipefs", "-a", node.name],
            action=action,
            device=device,
            execute=execute,
            runner=runner,
            scheduled=scheduled,
            tolerate_failure=True,
        )
        if result.returncode != 0:
            success = False
    if not success:
        log_event(
            "pre_nixos.cleanup.descendant_wipe_failed",
            action=action,
            device=device,
            execute=execute,
        )
    return success


def _collect_partition_refresh_diagnostics() -> dict[str, object]:
    """Collect context for partition refresh failures.

    The device is logged separately by :func:`log_event`, so it is intentionally
    omitted here to avoid passing multiple ``device`` keyword arguments while
    still capturing the rest of the diagnostics we care about.
    """

    return {
        **storage_detection.collect_boot_probe_data(),
        **_collect_storage_stack_state(),
    }


def _refresh_partition_table(
    action: str,
    device: str,
    *,
    execute: bool,
    runner: CommandRunner,
    scheduled: List[str],
    attempts: int = 3,
    delay_seconds: float = 0.5,
) -> bool:
    for attempt in range(attempts):
        blockdev_result = _execute_command(
            ["blockdev", "--rereadpt", device],
            action=action,
            device=device,
            execute=execute,
            runner=runner,
            scheduled=scheduled,
            tolerate_failure=True,
        )
        partprobe_result = _execute_command(
            ["partprobe", device],
            action=action,
            device=device,
            execute=execute,
            runner=runner,
            scheduled=scheduled,
            tolerate_failure=True,
        )
        settle_result = _execute_command(
            ["udevadm", "settle"],
            action=action,
            device=device,
            execute=execute,
            runner=runner,
            scheduled=scheduled,
            tolerate_failure=True,
        )
        if (
            blockdev_result.returncode in {0, 16}
            and partprobe_result.returncode in {0, 1}
            and settle_result.returncode == 0
        ):
            return True
        time.sleep(delay_seconds)
    log_event(
        "pre_nixos.cleanup.partition_refresh_failed",
        action=action,
        device=device,
        execute=execute,
        **_collect_partition_refresh_diagnostics(),
    )
    return False


def _wipe_root_device(
    action: str,
    device: str,
    *,
    execute: bool,
    runner: CommandRunner,
    scheduled: List[str],
) -> None:
    _execute_command(
        ("sgdisk", "--zap-all", device),
        action=action,
        device=device,
        execute=execute,
        runner=runner,
        scheduled=scheduled,
    )

    if not _refresh_partition_table(
        action,
        device,
        execute=execute,
        runner=runner,
        scheduled=scheduled,
    ):
        return

    if action == DISCARD_BLOCKS:
        _execute_command(
            ("blkdiscard", "--force", device),
            action=action,
            device=device,
            execute=execute,
            runner=runner,
            scheduled=scheduled,
        )
    elif action == OVERWRITE_RANDOM:
        _execute_command(
            ("shred", "-n", "1", "-vz", device),
            action=action,
            device=device,
            execute=execute,
            runner=runner,
            scheduled=scheduled,
        )

    _execute_command(
        ("wipefs", "-a", device),
        action=action,
        device=device,
        execute=execute,
        runner=runner,
        scheduled=scheduled,
    )


def perform_storage_cleanup(
    action: str,
    devices: Sequence[str],
    *,
    execute: bool,
    runner: CommandRunner | None = None,
) -> List[str]:
    """Apply the requested storage cleanup action to *devices*.

    Returns the list of shell command strings that were scheduled. When
    ``execute`` is ``False`` the commands are only logged.
    """

    runner = runner or _default_runner
    scheduled: List[str] = []
    log_event(
        "pre_nixos.cleanup.start",
        action=action,
        devices=list(devices),
        execute=execute,
    )
    if action == SKIP_CLEANUP:
        log_event(
            "pre_nixos.cleanup.finished",
            action=action,
            devices=list(devices),
            execute=execute,
            commands=scheduled,
        )
        return scheduled

    if action not in {
        WIPE_SIGNATURES,
        DISCARD_BLOCKS,
        OVERWRITE_RANDOM,
    }:
        raise ValueError(f"unknown storage cleanup action: {action}")

    graph = _build_storage_graph()
    for device in devices:
        graph.setdefault(device, StorageNode(name=device, node_type="unknown"))
    reachable = _reachable_nodes(graph, devices)
    ordered_nodes = _ordered_nodes_leaf_to_root(graph, reachable)

    _teardown_graph(
        action,
        ",".join(devices),
        ordered_nodes,
        graph,
        execute=execute,
        runner=runner,
        scheduled=scheduled,
    )

    _wipe_descendant_metadata_graph(
        action,
        ",".join(devices),
        ordered_nodes,
        graph,
        execute=execute,
        runner=runner,
        scheduled=scheduled,
    )

    for device in devices:
        _wipe_root_device(
            action,
            device,
            execute=execute,
            runner=runner,
            scheduled=scheduled,
        )

    log_event(
        "pre_nixos.cleanup.finished",
        action=action,
        devices=list(devices),
        execute=execute,
        commands=scheduled,
    )
    return scheduled
