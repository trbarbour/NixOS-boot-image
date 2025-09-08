"""CLI entry point for pre-nixos."""

import argparse
import json

from . import inventory, planner, apply


def main(argv: list[str] | None = None) -> None:
    """Run the pre-nixos tool."""
    parser = argparse.ArgumentParser(description="Pre-NixOS setup")
    parser.add_argument("--mode", choices=["fast", "careful"], default="fast")
    parser.add_argument(
        "--plan-only", action="store_true", help="Only print the plan and exit"
    )
    parser.add_argument(
        "--prefer-raid6-on-four",
        action="store_true",
        help="Use RAID6 instead of RAID5 for four-disk HDD groups",
    )
    args = parser.parse_args(argv)

    disks = inventory.enumerate_disks()
    plan = planner.plan_storage(
        args.mode, disks, prefer_raid6_on_four=args.prefer_raid6_on_four
    )
    print(json.dumps(plan, indent=2))
    if not args.plan_only:
        apply.apply_plan(plan)


if __name__ == "__main__":
    main()
