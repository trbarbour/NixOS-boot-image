"""CLI entry point for pre-nixos."""

import argparse
import io
import json
import os
import sys

from . import inventory, planner, apply, partition, network


def _maybe_open_console() -> io.TextIOWrapper | None:
    """Open the kernel console for log fan-out when present."""
    try:
        return open("/dev/console", "w", buffering=1)
    except OSError:
        return None


def _is_interactive() -> bool:
    """Return ``True`` when the CLI is connected to an interactive terminal."""

    try:
        return sys.stdin.isatty() and sys.stdout.isatty()
    except Exception:  # pragma: no cover - extremely defensive
        return False


def _confirm_storage_reset() -> bool:
    """Request confirmation before destroying existing storage."""

    prompt = (
        "This will erase and reinitialize all detected storage. Continue? [y/N]: "
    )
    while True:
        try:
            response = input(prompt)
        except EOFError:
            return False
        choice = response.strip().lower()
        if choice in {"y", "yes"}:
            return True
        if choice in {"", "n", "no"}:
            return False
        print("Please respond with 'yes' or 'no'.")


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

    console = _maybe_open_console()

    try:
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
        output = json.dumps(plan, indent=2)
        print(output)
        if console is not None:
            # ``/dev/console`` expects carriage return + line feed for proper
            # rendering on some terminals. Ensure each newline in the JSON
            # output resets the cursor to the start of the line before
            # returning control to the caller.
            console_output = output.replace("\n", "\r\n") + "\r\n"
            console.write(console_output)
            console.flush()

        will_modify_storage = (
            not args.plan_only
            and not args.dry_run
            and os.environ.get("PRE_NIXOS_EXEC") == "1"
        )
        if will_modify_storage and _is_interactive():
            if not _confirm_storage_reset():
                print("Aborting without modifying storage.")
                return

        if not args.plan_only:
            apply.apply_plan(plan, dry_run=args.dry_run)
    finally:
        if console is not None:
            console.close()


if __name__ == "__main__":
    main()
