"""CLI entry point for pre-nixos."""

import argparse
import io
import json
import os
import sys
from typing import Sequence

from . import (
    apply,
    inventory,
    network,
    partition,
    planner,
    storage_cleanup,
    storage_detection,
)


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
    """Request confirmation before applying the storage plan."""

    prompt = "Apply the proposed storage plan now? This may erase data. [y/N]: "
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


def _prompt_storage_cleanup(
    devices: Sequence[storage_detection.ExistingStorageDevice],
) -> str | None:
    print("Existing storage detected on the following devices:")
    for entry in devices:
        reasons = storage_detection.format_existing_storage_reasons(entry.reasons)
        print(f"  - {entry.device} ({reasons})")
    print("Choose how to erase the existing data before applying the plan:")
    for option in storage_cleanup.CLEANUP_OPTIONS:
        print(f"  [{option.key}] {option.description}")
    while True:
        try:
            response = input("Selection [q]: ")
        except EOFError:
            return None
        choice = response.strip().lower() or "q"
        for option in storage_cleanup.CLEANUP_OPTIONS:
            if choice == option.key:
                return option.action
        print("Please choose one of the listed options.")


def _handle_existing_storage(execute: bool) -> bool:
    try:
        devices = storage_detection.detect_existing_storage()
    except Exception as exc:
        print(f"Failed to inspect existing storage: {exc}")
        return False
    if not devices:
        return True
    if not _is_interactive():
        print(
            "Existing storage was detected but no interactive terminal is "
            "available to choose a wipe method. Aborting."
        )
        return False
    action = _prompt_storage_cleanup(devices)
    if action is None:
        print("Aborting without modifying storage.")
        return False
    if action != storage_cleanup.SKIP_CLEANUP:
        storage_cleanup.perform_storage_cleanup(
            action,
            [entry.device for entry in devices],
            execute=execute,
        )
    return True


def main(argv: list[str] | None = None) -> None:
    """Run the pre-nixos tool."""
    parser = argparse.ArgumentParser(description="Pre-NixOS setup")
    parser.add_argument("--mode", choices=["fast", "careful"], default="fast")
    parser.add_argument(
        "--plan-only", action="store_true", help="Only print the plan and exit"
    )
    parser.add_argument(
        "--output",
        choices=["plan", "disko"],
        default="plan",
        help="Choose between the summarized plan or rendered disko config",
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
        if args.output == "plan":
            plan_output = {key: value for key, value in plan.items() if key != "disko"}
            output = json.dumps(plan_output, indent=2)
        else:
            devices = plan.get("disko") or {}
            output = apply._render_disko_config(devices)
        print(output)
        if console is not None:
            # ``/dev/console`` expects carriage return + line feed for proper
            # rendering on some terminals. Ensure each newline in the rendered
            # output resets the cursor to the start of the line before returning
            # control to the caller.
            console_output = output.replace("\n", "\r\n") + "\r\n"
            console.write(console_output)
            console.flush()

        will_modify_storage = (
            not args.plan_only
            and not args.dry_run
            and os.environ.get("PRE_NIXOS_EXEC") == "1"
        )
        if will_modify_storage:
            if not _handle_existing_storage(execute=will_modify_storage):
                return
            if _is_interactive() and not _confirm_storage_reset():
                print("Aborting without modifying storage.")
                return

        if not args.plan_only:
            apply.apply_plan(plan, dry_run=args.dry_run)
    finally:
        if console is not None:
            console.close()


if __name__ == "__main__":
    main()
