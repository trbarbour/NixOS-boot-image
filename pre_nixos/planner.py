"""Storage planning heuristics."""

from typing import List, Dict, Any

from .inventory import Disk


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


def plan_storage(mode: str, disks: List[Disk], ram: int = 0) -> Dict[str, Any]:
    """Generate storage plan from disks and mode.

    Args:
        mode: Planning mode (e.g. ``fast`` or ``careful``).
        disks: Detected disks.
        ram: System RAM in the same units as ``Disk.size``.

    The returned plan is a minimal representation with arrays, volume groups and
    logical volumes. It is sufficient for tests and will evolve as the project
    grows.
    """
    groups = group_by_rotational_and_size(disks)
    plan: Dict[str, Any] = {"arrays": [], "vgs": [], "lvs": []}
    array_index = 0

    # Handle SSD buckets for VG "main" and suffixed variants
    ssd_buckets = sorted(
        groups["ssd"],
        key=lambda b: sum(d.size for d in b),
        reverse=True,
    )
    for idx, bucket in enumerate(ssd_buckets):
        vg_name = "main" if idx == 0 else f"main-{idx}"
        arr = decide_ssd_array(bucket, mode)
        devices = arr["devices"]
        if arr["level"] == "single":
            plan["vgs"].append({"name": vg_name, "devices": devices})
        else:
            name = f"md{array_index}"
            array_index += 1
            plan["arrays"].append({"name": name, "level": arr["level"], "devices": devices, "type": "ssd"})
            plan["vgs"].append({"name": vg_name, "devices": [name]})

    # Handle HDD buckets for VG "swap" and "large" variants
    hdd_buckets = groups["hdd"]

    # Prefer the smallest suitable bucket for swap
    swap_size = ram * 2
    swap_bucket_index = None
    if swap_size > 0:
        candidates = [
            (sum(d.size for d in bucket), idx)
            for idx, bucket in enumerate(hdd_buckets)
            if len(bucket) >= 2 and bucket[0].size >= swap_size
        ]
        if candidates:
            _, swap_bucket_index = min(candidates)

    if swap_bucket_index is not None:
        swap_bucket = hdd_buckets.pop(swap_bucket_index)
        arr = decide_hdd_array(swap_bucket)
        devices = arr["devices"]
        if arr["level"] == "single":
            plan["vgs"].append({"name": "swap", "devices": devices})
        else:
            name = f"md{array_index}"
            array_index += 1
            plan["arrays"].append(
                {"name": name, "level": arr["level"], "devices": devices, "type": "hdd"}
            )
            plan["vgs"].append({"name": "swap", "devices": [name]})
        plan["lvs"].append({"name": "swap", "vg": "swap", "size": "100%"})

    # Remaining buckets form large and suffixed variants, preferring largest groups
    hdd_buckets = sorted(
        hdd_buckets,
        key=lambda b: sum(d.size for d in b),
        reverse=True,
    )
    for idx, bucket in enumerate(hdd_buckets):
        vg_name = "large" if idx == 0 else f"large-{idx}"
        arr = decide_hdd_array(bucket)
        devices = arr["devices"]
        if arr["level"] == "single":
            plan["vgs"].append({"name": vg_name, "devices": devices})
        else:
            name = f"md{array_index}"
            array_index += 1
            plan["arrays"].append({"name": name, "level": arr["level"], "devices": devices, "type": "hdd"})
            plan["vgs"].append({"name": vg_name, "devices": [name]})

    # Simple LV layout
    if any(vg["name"] == "main" for vg in plan["vgs"]):
        plan["lvs"].append({"name": "root", "vg": "main", "size": "100%"})
    if any(vg["name"] == "large" for vg in plan["vgs"]):
        plan["lvs"].append({"name": "data", "vg": "large", "size": "100%"})

    return plan
