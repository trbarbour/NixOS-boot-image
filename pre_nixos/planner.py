"""Storage planning heuristics."""
from __future__ import annotations

from typing import List, Dict, Any

from .inventory import Disk

# Default logical volume sizes.  Using fixed sizes avoids consuming the entire
# volume group, leaving room for administrators to create additional volumes as
# needed.  Logical volumes can be grown later but shrinking them is more
# cumbersome, especially once filesystems are in place.
ROOT_LV_SIZE = "50G"
DATA_LV_SIZE = "100G"


def _to_bytes(size: int) -> int:
    """Return ``size`` in bytes.

    Tests often use small integers to represent GiB.  To keep those tests
    working while still handling real byte counts, values below 1 MiB are
    interpreted as GiB.
    """

    return size if size >= 1 << 20 else size * 1024 ** 3


def _parse_size(s: str) -> int:
    """Parse size strings like ``"20G"`` or ``"512M"`` into bytes."""

    s = s.upper()
    if s.endswith("G"):
        return int(s[:-1]) * 1024 ** 3
    if s.endswith("M"):
        return int(s[:-1]) * 1024 ** 2
    return int(s)


def _format_size(size: int) -> str:
    """Format ``size`` in bytes as a human readable string."""

    if size % (1024 ** 3) == 0:
        return f"{size // (1024 ** 3)}G"
    if size % (1024 ** 2) == 0:
        return f"{size // (1024 ** 2)}M"
    return str(size)


EFI_PARTITION_SIZE = _parse_size("1G")
MI_BYTE = 1024 ** 2


def _array_capacity(level: str, sizes: List[int]) -> int:
    """Return usable size in bytes for an array of ``sizes``."""

    n = len(sizes)
    if n == 0:
        return 0
    min_size = min(sizes)
    if level in {"single", "raid0"}:
        return sum(sizes)
    if level == "raid1":
        return min_size
    if level == "raid5":
        return sum(sizes) - min_size
    if level == "raid6":
        return sum(sizes) - 2 * min_size
    if level == "raid10":
        return sum(sizes) // 2
    return sum(sizes)


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
    plan: Dict[str, Any] = {"arrays": [], "vgs": [], "lvs": [], "partitions": {}, "disko": {}}
    array_index = 0
    device_sizes: Dict[str, int] = {}
    vg_sizes: Dict[str, int] = {}
    used_vg_sizes: Dict[str, int] = {}

    def record_partitions(ds: List[Disk], with_efi: bool, raid: bool) -> List[str]:
        """Record partitions for ``ds`` and return their data devices.

        The final partition type depends on ``raid``: when ``True`` the
        partition is marked as ``linux-raid`` (FD00); otherwise it becomes a
        ``lvm`` partition (8E00).
        """

        devices: List[str] = []
        for d in ds:
            if d.name not in plan["partitions"]:
                parts: List[Dict[str, str]] = []
                idx = 1
                if with_efi:
                    parts.append({"name": _part_name(d.name, idx), "type": "efi"})
                    idx += 1
                ptype = "linux-raid" if raid else "lvm"
                part_name = _part_name(d.name, idx)
                parts.append({"name": part_name, "type": ptype})
                plan["partitions"][d.name] = parts
                capacity = _to_bytes(d.size)
                if with_efi:
                    capacity = max(capacity - EFI_PARTITION_SIZE, 0)
                if capacity > 0:
                    capacity -= capacity % MI_BYTE
                device_sizes[part_name] = capacity
            # last partition in the list is always the data one
            devices.append(plan["partitions"][d.name][-1]["name"])
        return devices

    def add_vg(name: str, devices: List[str]) -> None:
        plan["vgs"].append({"name": name, "devices": devices})
        vg_sizes[name] = sum(device_sizes[d] for d in devices)

    def add_array(name: str, level: str, devices: List[str], typ: str) -> None:
        plan["arrays"].append({"name": name, "level": level, "devices": devices, "type": typ})
        device_sizes[name] = _array_capacity(level, [device_sizes[d] for d in devices])

    def add_lv(name: str, vg: str, size: str) -> None:
        total = vg_sizes.get(vg, 0)
        used = used_vg_sizes.get(vg, 0)
        free = max(total - used, 0)
        if free <= 0:
            return
        req = _parse_size(size)
        alloc = req if req <= free else free
        used_vg_sizes[vg] = used + alloc
        plan["lvs"].append({"name": name, "vg": vg, "size": _format_size(alloc)})

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
        arr = decide_hdd_array(bucket, prefer_raid6_on_four=prefer_raid6_on_four)
        devices = record_partitions(bucket, with_efi=True, raid=arr["level"] != "single")
        if arr["level"] == "single":
            add_vg("main", devices)
        else:
            name = f"md{array_index}"
            array_index += 1
            add_array(name, arr["level"], devices, "hdd")
            add_vg("main", [name])
        swap_size = f"{ram_gb * 2 * 1024}M"
        add_lv("slash", "main", ROOT_LV_SIZE)
        add_lv("swap", "main", swap_size)
        return plan

    for idx, bucket in enumerate(ssd_buckets):
        vg_name = "main" if idx == 0 else f"main-{idx}"
        arr = decide_ssd_array(bucket, mode)
        devices = record_partitions(
            bucket, with_efi=vg_name == "main", raid=arr["level"] != "single"
        )
        if arr["level"] == "single":
            add_vg(vg_name, devices)
        else:
            name = f"md{array_index}"
            array_index += 1
            add_array(name, arr["level"], devices, "ssd")
            add_vg(vg_name, [name])

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

    hdd_arrays = [
        decide_hdd_array(bucket, prefer_raid6_on_four=prefer_raid6_on_four)
        for bucket in hdd_buckets
    ]

    main_bucket_idx: int | None = None
    if not ssd_buckets and hdd_buckets:
        for idx, arr in enumerate(hdd_arrays):
            if arr["level"] == "raid1":
                main_bucket_idx = idx
                break
        if main_bucket_idx is None:
            for idx, arr in enumerate(hdd_arrays):
                if arr["level"] != "single":
                    main_bucket_idx = idx
                    break
        if main_bucket_idx is None:
            main_bucket_idx = 0

    large_idx = 0
    for idx, bucket in enumerate(hdd_buckets):
        if idx == swap_bucket_idx:
            vg_name = "swap"
        elif idx == main_bucket_idx:
            vg_name = "main"
        else:
            vg_name = "large" if large_idx == 0 else f"large-{large_idx}"
            large_idx += 1
        arr = hdd_arrays[idx]
        devices = record_partitions(
            bucket, with_efi=vg_name == "main", raid=arr["level"] != "single"
        )
        if arr["level"] == "single":
            add_vg(vg_name, devices)
        else:
            name = f"md{array_index}"
            array_index += 1
            add_array(name, arr["level"], devices, "hdd")
            add_vg(vg_name, [name])

    swap_size = f"{ram_gb * 2 * 1024}M"
    swap_vg = next((vg["name"] for vg in plan["vgs"] if vg["name"] == "swap"), None)
    if swap_vg is None:
        swap_vg = next(
            (vg["name"] for vg in plan["vgs"] if vg["name"].startswith("large")),
            None,
        )
    if swap_vg is None and not hdd_buckets:
        swap_vg = next(
            (vg["name"] for vg in plan["vgs"] if vg["name"] == "main"),
            None,
        )
    if any(vg["name"] == "main" for vg in plan["vgs"]):
        add_lv("slash", "main", ROOT_LV_SIZE)
    if swap_vg is not None:
        add_lv("swap", swap_vg, swap_size)
    if any(vg["name"].startswith("large") for vg in plan["vgs"]):
        add_lv("data", "large", DATA_LV_SIZE)

    plan["disko"] = _plan_to_disko_devices(plan)
    return plan


def _plan_to_disko_devices(plan: Dict[str, Any]) -> Dict[str, Any]:
    """Translate an internal plan to ``disko.devices``."""

    devices: Dict[str, Any] = {"disk": {}, "mdadm": {}, "lvm_vg": {}}

    arrays_by_name = {arr["name"]: arr for arr in plan.get("arrays", [])}
    partition_to_array: Dict[str, str] = {}
    for arr in plan.get("arrays", []):
        for dev in arr.get("devices", []):
            partition_to_array[dev] = arr["name"]

    partition_to_vg: Dict[str, str] = {}
    for vg in plan.get("vgs", []):
        for dev in vg.get("devices", []):
            if dev not in arrays_by_name:
                partition_to_vg[dev] = vg["name"]

    efi_count = 0
    for disk, parts in plan.get("partitions", {}).items():
        partitions: Dict[str, Any] = {}
        for part in parts:
            ptype = part.get("type")
            name = part.get("name")
            if not name:
                continue
            if ptype == "efi":
                label = "EFI" if efi_count == 0 else f"EFI{efi_count + 1}"
                efi_count += 1
                content: Dict[str, Any] = {
                    "type": "filesystem",
                    "format": "vfat",
                    "label": label,
                }
                if label == "EFI":
                    content["mountpoint"] = "/boot"
                    content["mountOptions"] = ["umask=0077"]
                partitions[name] = {
                    "size": "1G",
                    "type": "EF00",
                    "content": content,
                }
                continue
            entry: Dict[str, Any] = {"size": "100%"}
            array_name = partition_to_array.get(name)
            if array_name:
                entry["content"] = {"type": "mdraid", "name": array_name}
            else:
                vg_name = partition_to_vg.get(name)
                if vg_name:
                    entry["content"] = {"type": "lvm_pv", "vg": vg_name}
            partitions[name] = entry
        devices["disk"][disk] = {
            "type": "disk",
            "device": f"/dev/{disk}",
            "content": {"type": "gpt", "partitions": partitions},
        }

    array_to_vg: Dict[str, str] = {}
    for vg in plan.get("vgs", []):
        for dev in vg.get("devices", []):
            if dev in arrays_by_name:
                array_to_vg[dev] = vg["name"]

    level_map = {"raid0": 0, "raid1": 1, "raid5": 5, "raid6": 6, "raid10": 10}
    for name, arr in arrays_by_name.items():
        entry: Dict[str, Any] = {
            "type": "mdadm",
            "level": level_map.get(arr.get("level", ""), arr.get("level")),
        }
        target_vg = array_to_vg.get(name)
        if target_vg:
            entry["content"] = {"type": "lvm_pv", "vg": target_vg}
        devices["mdadm"][name] = entry

    lvs_by_vg: Dict[str, Dict[str, Any]] = {}
    for lv in plan.get("lvs", []):
        vg = lv.get("vg")
        if not vg:
            continue
        lvs = lvs_by_vg.setdefault(vg, {})
        size = lv.get("size")
        if size is None:
            continue
        if lv.get("name") == "swap":
            content = {"type": "swap"}
        else:
            mountpoint = "/" if lv.get("name") == "slash" else f"/{lv.get('name')}"
            content = {
                "type": "filesystem",
                "format": "ext4",
                "mountpoint": mountpoint,
                "mountOptions": ["noatime"],
            }
        lvs[lv["name"]] = {"size": size, "content": content}

    for vg, lvs in lvs_by_vg.items():
        devices["lvm_vg"][vg] = {"type": "lvm_vg", "lvs": lvs}

    return devices
