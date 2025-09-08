"""Apply storage plans."""

from typing import Dict, Any, List


def apply_plan(plan: Dict[str, Any], dry_run: bool = True) -> List[str]:
    """Apply a storage plan.

    Parameters:
        plan: Plan dictionary produced by :func:`pre_nixos.planner.plan_storage`.
        dry_run: If ``True``, commands are returned without execution.

    Returns:
        A list of shell command strings in the order they would be executed.
    """
    commands: List[str] = []

    for array in plan.get("arrays", []):
        devices = " ".join(f"/dev/{d}" for d in array["devices"])
        commands.append(
            f"mdadm --create /dev/{array['name']} --level={array['level']} {devices}"
        )

    for vg in plan.get("vgs", []):
        devs = " ".join(f"/dev/{d}" for d in vg["devices"])
        commands.append(f"vgcreate {vg['name']} {devs}")

    for lv in plan.get("lvs", []):
        commands.append(
            f"lvcreate -n {lv['name']} {lv['vg']} -l {lv['size']}"
        )
        lv_path = f"/dev/{lv['vg']}/{lv['name']}"
        # The Nix store contains millions of small files. Using a dense
        # inode allocation (1 inode per 2 KiB) prevents running out of
        # inodes long before the LV is full.
        commands.append(f"mkfs.ext4 -i 2048 {lv_path}")
        commands.append(f"e2label {lv_path} {lv['name']}")
        mount_point = "/mnt" if lv["name"] == "root" else f"/mnt/{lv['name']}"
        if mount_point != "/mnt":
            commands.append(f"mkdir -p {mount_point}")
        commands.append(f"mount -L {lv['name']} {mount_point}")

    if dry_run:
        return commands
    raise NotImplementedError("Real execution not yet implemented")
