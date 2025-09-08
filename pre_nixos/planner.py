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


def decide_hdd_array(group: List[Disk], prefer_raid6_on_four: bool = False) -> Dict[str, Any]:
    """Decide RAID configuration for HDD group.

    Uses ``raid5`` for three disks, optionally ``raid6`` for four disks when
    ``prefer_raid6_on_four`` is ``True``, and ``raid6`` for five or more disks.
    """
    count = len(group)
    devices = [d.name for d in group]
    if count <= 1:
        level = "single"
    elif count == 2:
        level = "raid1"
    elif count == 3:
        level = "raid5"
    elif count == 4:
        level = "raid6" if prefer_raid6_on_four else "raid5"
    else:
        level = "raid6"
    return {"level": level, "devices": devices}


def plan_storage(
    mode: str,
    disks: List[Disk],
    prefer_raid6_on_four: bool = False,
    ram_gb: int = 16,
) -> Dict[str, Any]:
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

    if not ssd_buckets and len(hdd_buckets) == 1 and len(hdd_buckets[0]) <= 2:
        bucket = hdd_buckets[0]
        devices = record_partitions(bucket, with_efi=True)
        arr = decide_hdd_array(bucket, prefer_raid6_on_four=prefer_raid6_on_four)
        if arr["level"] == "single":
            plan["vgs"].append({"name": "main", "devices": devices})
        else:
            name = f"md{array_index}"
            array_index += 1
            plan["arrays"].append(
                {"name": name, "level": arr["level"], "devices": devices, "type": "hdd"}
            )
            plan["vgs"].append({"name": "main", "devices": [name]})
        swap_size = f"{ram_gb * 2 * 1024}M"
        plan["lvs"].append({"name": "swap", "vg": "main", "size": swap_size})
        plan["lvs"].append({"name": "root", "vg": "main", "size": "100%FREE"})
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

    has_ssd = bool(ssd_buckets)

    # Determine which HDD bucket, if any, should become the swap VG.  We prefer the
    # smallest suitable bucket instead of the largest.  A bucket is suitable when it
    # either contains two disks and we have additional HDD capacity or SSDs for data,
    # or when it contains a single disk but SSDs are present.  The bucket must also
    # have enough capacity for a swap LV of size ``2 * RAM`` (mirrored size for RAID1
    # is limited by the smallest disk).
    swap_bucket_idx: int | None = None
    required_swap = 2 * ram_gb
    candidates: List[tuple[int, int]] = []  # (total_size, index)
    total_buckets = len(hdd_buckets)
    for idx, bucket in enumerate(hdd_buckets):
        cond = False
        if len(bucket) == 2:
            cond = has_ssd or total_buckets > 1
        elif len(bucket) == 1:
            cond = has_ssd
        if not cond:
            continue
        min_size = min(d.size for d in bucket)
        if min_size < required_swap:
            continue
        total_size = sum(d.size for d in bucket)
        candidates.append((total_size, idx))
    if candidates:
        # Pick the smallest total raw size.
        _, swap_bucket_idx = min(candidates, key=lambda x: x[0])

    large_idx = 0
    for idx, bucket in enumerate(hdd_buckets):
        if idx == swap_bucket_idx:
            vg_name = "swap"
        else:
            vg_name = "large" if large_idx == 0 else f"large-{large_idx}"
            large_idx += 1
        devices = record_partitions(bucket, with_efi=vg_name == "main")
        arr = decide_hdd_array(bucket, prefer_raid6_on_four=prefer_raid6_on_four)
        if arr["level"] == "single":
            plan["vgs"].append({"name": vg_name, "devices": devices})
        else:
            name = f"md{array_index}"
            array_index += 1
            plan["arrays"].append({"name": name, "level": arr["level"], "devices": devices, "type": "hdd"})
            plan["vgs"].append({"name": vg_name, "devices": [name]})

    swap_size = f"{ram_gb * 2 * 1024}M"
    if any(vg["name"] == "swap" for vg in plan["vgs"]):
        plan["lvs"].append({"name": "swap", "vg": "swap", "size": swap_size})
    if any(vg["name"] == "main" for vg in plan["vgs"]):
        plan["lvs"].append({"name": "root", "vg": "main", "size": "100%FREE"})
    if any(vg["name"] == "large" for vg in plan["vgs"]):
        plan["lvs"].append({"name": "data", "vg": "large", "size": "100%FREE"})

    return plan
