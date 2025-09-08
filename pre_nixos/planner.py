"""Storage planning heuristics."""

from typing import List, Dict, Any

from .inventory import Disk


def _part_name(device: str, part: int) -> str:
    """Return partition name for ``device`` and ``part`` number."""
    suffix = f"p{part}" if device.startswith("nvme") else str(part)
    return f"{device}{suffix}"


def group_by_rotational_and_size(disks: List[Disk], tolerance: float = 0.01) -> Dict[str, Any]:
    """Group disks into SSD/HDD buckets by size.

    Returns a mapping ``{"ssd": [[...], ...], "hdd": [[...], ...]}`` where each
    inner list contains disks of roughly equal size.
    """
    groups = {"ssd": [], "hdd": []}
    for disk in disks:
        key = "hdd" if disk.rotational else "ssd"
        buckets = groups[key]
        placed = False
        for bucket in buckets:
            ref = bucket[0].size
            if ref and abs(disk.size - ref) / ref <= tolerance:
                bucket.append(disk)
                placed = True
                break
        if not placed:
            buckets.append([disk])
    return groups


def decide_ssd_array(group: List[Disk], mode: str) -> Dict[str, Any]:
    """Decide RAID configuration for SSD group."""
    count = len(group)
    if count == 0:
        return {"level": None, "devices": []}
    devices = [d.name for d in group]
    if count == 1:
        level = "single"
    elif mode == "careful":
        if count == 2:
            level = "raid1"
        elif count >= 4 and count % 2 == 0:
            level = "raid10"
        else:
            level = "raid1"
            devices = devices[:2]
    else:
        level = "raid0"
    return {"level": level, "devices": devices}


def decide_hdd_array(group: List[Disk]) -> Dict[str, Any]:
    """Decide RAID configuration for HDD group."""
    count = len(group)
    devices = [d.name for d in group]
    if count <= 1:
        level = "single"
    elif count == 2:
        level = "raid1"
    elif 3 <= count <= 5:
        level = "raid5"
    else:
        level = "raid6"
    return {"level": level, "devices": devices}


def plan_storage(mode: str, disks: List[Disk]) -> Dict[str, Any]:
    """Generate storage plan from disks and mode.

    The returned plan is a minimal representation with arrays, volume groups and
    logical volumes. It is sufficient for tests and will evolve as the project
    grows.
    """
    groups = group_by_rotational_and_size(disks)
    plan: Dict[str, Any] = {"arrays": [], "vgs": [], "lvs": [], "partitions": {}}
    array_index = 0

    def record_partitions(ds: List[Disk], with_efi: bool) -> List[str]:
        devices: List[str] = []
        for d in ds:
            if d.name not in plan["partitions"]:
                parts = []
                idx = 1
                if with_efi:
                    parts.append({"name": _part_name(d.name, idx), "type": "efi"})
                    idx += 1
                parts.append({"name": _part_name(d.name, idx), "type": "linux-raid"})
                plan["partitions"][d.name] = parts
            # last partition in the list is always the linux-raid one
            devices.append(plan["partitions"][d.name][-1]["name"])
        return devices

    ssd_buckets = sorted(
        groups["ssd"],
        key=lambda b: sum(d.size for d in b),
        reverse=True,
    )

    hdd_buckets = sorted(
        groups["hdd"],
        key=lambda b: sum(d.size for d in b),
        reverse=True,
    )

    if not ssd_buckets and len(hdd_buckets) == 1 and len(hdd_buckets[0]) == 2:
        bucket = hdd_buckets[0]
        devices = record_partitions(bucket, with_efi=True)
        arr = decide_hdd_array(bucket)
        if arr["level"] == "single":
            plan["vgs"].append({"name": "main", "devices": devices})
        else:
            name = f"md{array_index}"
            array_index += 1
            plan["arrays"].append({"name": name, "level": arr["level"], "devices": devices, "type": "hdd"})
            plan["vgs"].append({"name": "main", "devices": [name]})
        plan["lvs"].append({"name": "root", "vg": "main", "size": "100%"})
        plan["lvs"].append({"name": "swap", "vg": "main", "size": "100%"})
        return plan

    for idx, bucket in enumerate(ssd_buckets):
        vg_name = "main" if idx == 0 else f"main-{idx}"
        arr = decide_ssd_array(bucket, mode)
        devices = record_partitions(bucket, with_efi=vg_name == "main")
        if arr["level"] == "single":
            plan["vgs"].append({"name": vg_name, "devices": devices})
        else:
            name = f"md{array_index}"
            array_index += 1
            plan["arrays"].append({"name": name, "level": arr["level"], "devices": devices, "type": "ssd"})
            plan["vgs"].append({"name": vg_name, "devices": [name]})

    swap_done = False
    large_idx = 0
    for idx, bucket in enumerate(hdd_buckets):
        remaining = len(hdd_buckets) - idx - 1
        has_ssd = bool(ssd_buckets)
        if not swap_done and (
            (len(bucket) == 2 and (has_ssd or remaining > 0))
            or (len(bucket) == 1 and has_ssd)
        ):
            vg_name = "swap"
            swap_done = True
        else:
            vg_name = "large" if large_idx == 0 else f"large-{large_idx}"
            large_idx += 1
        devices = record_partitions(bucket, with_efi=vg_name == "main")
        arr = decide_hdd_array(bucket)
        if arr["level"] == "single":
            plan["vgs"].append({"name": vg_name, "devices": devices})
        else:
            name = f"md{array_index}"
            array_index += 1
            plan["arrays"].append({"name": name, "level": arr["level"], "devices": devices, "type": "hdd"})
            plan["vgs"].append({"name": vg_name, "devices": [name]})

    if any(vg["name"] == "main" for vg in plan["vgs"]):
        plan["lvs"].append({"name": "root", "vg": "main", "size": "100%"})
    if any(vg["name"] == "large" for vg in plan["vgs"]):
        plan["lvs"].append({"name": "data", "vg": "large", "size": "100%"})
    if any(vg["name"] == "swap" for vg in plan["vgs"]):
        plan["lvs"].append({"name": "swap", "vg": "swap", "size": "100%"})

    return plan
