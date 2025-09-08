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
        if lv["name"] == "swap":
            commands.append(f"mkswap /dev/{lv['vg']}/{lv['name']}")

    if dry_run:
        return commands
    raise NotImplementedError("Real execution not yet implemented")
