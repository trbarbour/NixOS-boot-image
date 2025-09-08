"""CLI entry point for pre-nixos."""

import argparse
import json

from . import inventory, planner, apply, partition, network


def main(argv: list[str] | None = None) -> None:
    """Run the pre-nixos tool."""
    parser = argparse.ArgumentParser(description="Pre-NixOS setup")
    parser.add_argument("--mode", choices=["fast", "careful"], default="fast")
    parser.add_argument(
        "--plan-only", action="store_true", help="Only print the plan and exit"
    )
    parser.add_argument(
        "--partition-boot",
        metavar="DISK",
        help="Partition boot disk with EFI and LVM",
    )
    parser.add_argument(
        "--partition-lvm",
        metavar="DISK",
        action="append",
        default=[],
        help="Partition disk with a single LVM partition (can be repeated)",
    )
    parser.add_argument(
       "--prefer-raid6-on-four",
        action="store_true",
        help="Use RAID6 instead of RAID5 for four-disk HDD groups",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Only print commands without executing them",
    )
    args = parser.parse_args(argv)

    # Configure networking before performing storage operations so the machine
    # becomes remotely reachable as early as possible.
    network.configure_lan()

    if args.partition_boot:
        partition.create_partitions(args.partition_boot, dry_run=args.dry_run)
    for dev in args.partition_lvm:
        partition.create_partitions(dev, with_efi=False, dry_run=args.dry_run)

    disks = inventory.enumerate_disks()
    ram_gb = inventory.detect_ram_gb()
    plan = planner.plan_storage(
        args.mode,
        disks,
        prefer_raid6_on_four=args.prefer_raid6_on_four,
        ram_gb=ram_gb,
    )
    print(json.dumps(plan, indent=2))
    if not args.plan_only:
        apply.apply_plan(plan, dry_run=args.dry_run)


if __name__ == "__main__":
    main()
