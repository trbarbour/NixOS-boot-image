"""CLI entry point for pre-nixos."""

import argparse
import io
import json
import os
import sys
from typing import Collection, Iterable, Sequence, Set

from . import (
    apply,
    boot_platform,
    disk_class,
    install,
    inventory,
    lan_reuse,
    network,
    partition,
    planner,
    state,
    storage_cleanup,
    storage_detection,
)


def _maybe_open_console() -> io.TextIOWrapper | None:
    """Open the kernel console for log fan-out when present."""
    try:
        return open("/dev/console", "w", buffering=1)
    except OSError:
        return None


def _stdout_is_terminal() -> bool:
    """``True`` when stdout is a terminal, i.e. run by hand, not as a service."""

    try:
        return sys.stdout.isatty()
    except (AttributeError, ValueError):  # replaced or closed stdout
        return False


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


def _auto_install_default(lan_config: network.LanConfiguration | None) -> bool:
    """Return ``True`` when auto-install should be enabled by default."""

    env_value = os.environ.get("PRE_NIXOS_AUTO_INSTALL", "").strip().lower()
    env_enabled = env_value in {"1", "true", "yes", "on"}
    return env_enabled and lan_config is not None


def _plan_stdout_enabled() -> bool:
    """Return ``True`` when the storage plan should be printed to stdout."""

    value = os.environ.get("PRE_NIXOS_PLAN_STDOUT")
    if value is None:
        return True
    return value.strip().lower() not in {"", "0", "false", "no"}


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


def _normalise_device_path(device: str) -> str:
    device = device.strip()
    if device.startswith("/dev/"):
        return device
    return f"/dev/{device}" if device else device


def _collect_plan_devices(plan: dict[str, object]) -> Set[str]:
    devices: set[str] = set()

    def add(value: object) -> None:
        if not isinstance(value, str):
            return
        path = _normalise_device_path(value)
        if path:
            devices.add(path)

    for disk, partitions in (plan.get("partitions") or {}).items():
        if isinstance(disk, str):
            add(disk)
        if isinstance(partitions, Iterable):
            for entry in partitions:
                if isinstance(entry, dict):
                    add(entry.get("name"))

    for array in plan.get("arrays", []):
        if not isinstance(array, dict):
            continue
        add(array.get("name"))
        for device in array.get("devices", []) or []:
            add(device)

    for vg in plan.get("vgs", []):
        if not isinstance(vg, dict):
            continue
        for device in vg.get("devices", []) or []:
            add(device)

    return devices


def _expand_devices_with_lsblk(devices: Set[str]) -> Set[str]:
    expanded = set(devices)
    entries, _ = storage_cleanup._build_device_hierarchy()
    for entry in entries:
        name = str(entry.get("name") or "")
        if not name.startswith("/dev/"):
            continue
        parents = entry.get("parents") or []
        pkname = entry.get("pkname")
        related = list(parents)
        if pkname:
            related.append(str(pkname))
        if any(_normalise_device_path(rel) in devices for rel in related):
            expanded.add(name)
    return expanded


def _forced_cleanup_action() -> str | None:
    value = os.environ.get("PRE_NIXOS_FORCE_CLEANUP", "").strip().lower()
    enabled = value not in {"", "0", "false", "no"}
    if not enabled:
        return None

    requested = os.environ.get("PRE_NIXOS_FORCE_CLEANUP_ACTION", "").strip().lower()
    if requested:
        for option in storage_cleanup.CLEANUP_OPTIONS:
            if requested in {option.key, option.action.lower()}:
                return option.action
    return storage_cleanup.WIPE_SIGNATURES


def _refuse_protected_targets(
    targets: Iterable[str], protected_disks: Collection[str]
) -> None:
    """Exit if any target is, or lies on, a disk backing the running system."""

    # Compare canonical paths so aliases (/dev/disk/by-id/...) cannot slip by.
    protected = (
        {os.path.realpath(d) for d in _expand_devices_with_lsblk(set(protected_disks))}
        if protected_disks
        else set()
    )
    overlap = sorted({os.path.realpath(t) for t in targets} & protected)
    if overlap:
        print(
            "Refusing to modify protected device(s) backing the running system "
            "(boot medium): " + ", ".join(overlap),
            file=sys.stderr,
        )
        sys.exit(1)


def _handle_existing_storage(
    plan: dict[str, object],
    execute: bool,
    forced_action: str | None = None,
    protected_disks: Collection[str] = (),
) -> bool:
    try:
        devices = storage_detection.detect_existing_storage()
    except Exception as exc:
        print(f"Failed to inspect existing storage: {exc}")
        return False
    if not devices:
        return True
    if forced_action is None:
        forced_action = _forced_cleanup_action()
    if not _is_interactive() and forced_action is None:
        print(
            "Existing storage was detected but no interactive terminal is "
            "available to choose a wipe method. Aborting."
        )
        return False
    if forced_action is not None:
        action = forced_action
        print(
            "Existing storage detected; applying non-interactive cleanup "
            f"action '{action}'."
        )
    else:
        action = _prompt_storage_cleanup(devices)
        if action is None:
            print("Aborting without modifying storage.")
            return False
    cleanup_targets = _collect_plan_devices(plan)
    cleanup_targets.update(entry.device for entry in devices)
    cleanup_targets = _expand_devices_with_lsblk(cleanup_targets)
    _refuse_protected_targets(cleanup_targets, protected_disks)
    if cleanup_targets:
        print(
            "The selected cleanup will be applied to all devices referenced in "
            "the storage plan, including the detected devices listed above."
        )
    if action != storage_cleanup.SKIP_CLEANUP:
        storage_cleanup.perform_storage_cleanup(
            action,
            sorted(cleanup_targets),
            execute=execute,
        )
    return True


# Exit status of a run that stopped for the user's answer (R-S3); the boot
# service reports it as plan-only, not as a failure.
EXIT_NEEDS_ANSWER = 3


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
    parser.add_argument(
        "--auto-install",
        dest="auto_install",
        action=argparse.BooleanOptionalAction,
        default=None,
        help=(
            "Automatically run nixos-install after applying the storage plan when "
            "a root SSH key is available (defaults to enabled)."
        ),
    )
    parser.add_argument(
        "--install-now",
        action="store_true",
        help=(
            "Immediately run nixos-install using the last applied storage plan. "
            "Cannot be combined with planning options."
        ),
    )
    parser.add_argument(
        "--install-ip-address",
        help="Static IPv4 address to apply to the installed system (disables DHCP).",
    )
    parser.add_argument(
        "--install-netmask",
        help="Netmask for the installed system's static IPv4 configuration.",
    )
    parser.add_argument(
        "--install-gateway",
        help="Default gateway for the installed system's static IPv4 configuration.",
    )
    parser.add_argument(
        "--ssd",
        metavar="DISK",
        action="append",
        default=[],
        help=(
            "Plan DISK as an SSD, whatever the kernel reports (can be repeated). "
            "Answers the question about a disk named SSD but reported as rotating."
        ),
    )
    parser.add_argument(
        "--hdd",
        metavar="DISK",
        action="append",
        default=[],
        help="Plan DISK as an HDD, whatever the kernel reports (can be repeated).",
    )
    args = parser.parse_args(argv)
    try:
        class_answers = disk_class.parse_answers(args.ssd, args.hdd)
    except ValueError as exc:
        parser.error(str(exc))

    install_network: install.InstallNetworkConfig | None = install.load_install_network_config()
    install_network_args: tuple[str, str | None, str | None] | None = None
    ip_args = (
        args.install_ip_address,
        args.install_netmask,
        args.install_gateway,
    )
    if any(ip_args):
        if not args.install_ip_address:
            parser.error("--install-ip-address is required when setting install networking")
        install_network_args = (
            args.install_ip_address,
            args.install_netmask,
            args.install_gateway,
        )

    console = _maybe_open_console()

    lan_config: network.LanConfiguration | None = None

    try:
        # Configure networking before performing storage operations so the machine
        # becomes remotely reachable as early as possible.
        lan_config = lan_reuse.ensure_lan()
        auto_install_enabled = args.auto_install
        if auto_install_enabled is None:
            auto_install_enabled = _auto_install_default(lan_config)

        if install_network_args is not None:
            iface = lan_config.interface if lan_config and lan_config.interface else "lan"
            try:
                install_network = install.build_install_network_config_with_defaults(
                    install_network_args[0],
                    netmask=install_network_args[1],
                    gateway=install_network_args[2],
                    iface=iface,
                )
            except ValueError as exc:
                parser.error(str(exc))

        if install_network_args is not None and install_network is not None:
            try:
                state.record_install_network_config(install_network.to_payload())
            except OSError as exc:
                print(
                    f"Warning: failed to record install network configuration: {exc}",
                    file=sys.stderr,
                )

        if args.install_now:
            if args.plan_only or args.partition_boot or args.partition_lvm or class_answers:
                parser.error("--install-now cannot be combined with planning options")
            if args.output != "plan":
                parser.error("--install-now cannot be combined with --output")
            if lan_config is None:
                print("Unable to configure networking; aborting installation.")
                sys.exit(1)

            result = install.auto_install(
                lan_config,
                None,
                install_network=install_network,
                enabled=True,
                dry_run=args.dry_run,
            )
            if result.status == "failed":
                reason = result.reason or "unknown error"
                print(f"Install failed: {reason}", file=sys.stderr)
                sys.exit(1)
            if result.status == "success":
                print("Install completed successfully.")
            elif result.reason:
                print(f"Install skipped: {result.reason}.")
            return

        try:
            protected_disks = storage_detection.resolve_protected_disks()
        except Exception as exc:
            print(
                f"Cannot determine the disks backing the running system ({exc}); "
                "refusing to plan or modify storage.",
                file=sys.stderr,
            )
            sys.exit(1)

        explicit_targets = [args.partition_boot] if args.partition_boot else []
        explicit_targets += list(args.partition_lvm)
        _refuse_protected_targets(
            (_normalise_device_path(dev) or dev for dev in explicit_targets),
            protected_disks,
        )
        try:
            boot_setup = boot_platform.current_setup()
        except ValueError as exc:
            print(f"Invalid boot-image declaration: {exc}", file=sys.stderr)
            sys.exit(1)
        disks = inventory.exclude_disks(inventory.enumerate_disks(), protected_disks)
        try:
            classified = disk_class.apply_classes(disks, class_answers)
        except ValueError as exc:
            parser.error(str(exc))
        unconfirmed_disks = disk_class.unconfirmed(disks, class_answers)
        ram_gb = inventory.detect_ram_gb()
        plan = disk_class.annotate_plan(
            planner.plan_storage(
                args.mode,
                classified,
                prefer_raid6_on_four=args.prefer_raid6_on_four,
                ram_gb=ram_gb,
                boot_layout=boot_platform.partition_layout(boot_setup),
            ),
            class_answers,
        )
        if args.output == "plan":
            plan_output = {key: value for key, value in plan.items() if key != "disko"}
            output = json.dumps(plan_output, indent=2)
        else:
            devices = plan.get("disko") or {}
            output = apply._render_disko_config(devices)

        if _plan_stdout_enabled():
            print(output)
            # The console copy is for the boot-time service, whose stdout is
            # the journal.  At a terminal it would print the plan twice when
            # that terminal is the console, e.g. the serial ISO (item 36).
            if console is not None and not _stdout_is_terminal():
                # ``/dev/console`` expects carriage return + line feed for proper
                # rendering on some terminals. Ensure each newline in the rendered
                # output resets the cursor to the start of the line before returning
                # control to the caller.
                console_output = output.replace("\n", "\r\n") + "\r\n"
                console.write(console_output)
                console.flush()

        # R-S3 (task queue item 34): a disk named SSD but reported as rotating
        # is not classified by guesswork.  A run that would touch the disks
        # stops first until the user answers: one that provisions or installs,
        # a forced cleanup, which runs even with --plan-only and wipes the
        # plan's devices, and explicit partitioning, which zaps the named
        # disks (Codex on #335, both reviews).
        forced_cleanup_action = _forced_cleanup_action()
        if unconfirmed_disks:
            message = disk_class.refusal_message(unconfirmed_disks)
            touches_disks = (
                not args.plan_only
                or forced_cleanup_action is not None
                or bool(explicit_targets)
            )
            if touches_disks and not args.dry_run:
                install.refuse_unconfirmed_disks(message)
                sys.exit(EXIT_NEEDS_ANSWER)
            print(message, file=sys.stderr)

        # Explicit partitioning (after the R-S3 stop: it erases the disks).
        if args.partition_boot:
            partition.create_partitions(args.partition_boot, dry_run=args.dry_run)
        for dev in args.partition_lvm:
            partition.create_partitions(dev, with_efi=False, dry_run=args.dry_run)

        # Task queue item 33: an auto-install that cannot boot (legacy BIOS on
        # x86, R-B1) is refused before any disk is touched for it.
        if auto_install_enabled and not args.plan_only and not args.dry_run:
            refused = install.legacy_bios_preflight(plan)
            if refused is not None:
                print(f"Auto-install failed: {refused.reason}", file=sys.stderr)
                sys.exit(1)

        will_modify_storage = (
            not args.dry_run
            and os.environ.get("PRE_NIXOS_EXEC") == "1"
            and (forced_cleanup_action is not None or not args.plan_only)
        )
        if will_modify_storage:
            if not _handle_existing_storage(
                plan,
                execute=will_modify_storage,
                forced_action=forced_cleanup_action,
                protected_disks=protected_disks,
            ):
                return
            if _is_interactive() and not _confirm_storage_reset():
                print("Aborting without modifying storage.")
                return

        if not args.plan_only:
            apply.apply_plan(plan, dry_run=args.dry_run, protected_disks=protected_disks)
            result = install.auto_install(
                lan_config,
                plan,
                install_network=install_network,
                enabled=auto_install_enabled,
                dry_run=args.dry_run,
            )
            if result.status == "failed":
                reason = result.reason or "unknown error"
                print(f"Auto-install failed: {reason}", file=sys.stderr)
                sys.exit(1)
            if result.status == "success":
                print("Auto-install completed successfully.")
            elif auto_install_enabled and result.reason:
                print(f"Auto-install skipped: {result.reason}.")
    finally:
        if console is not None:
            console.close()


if __name__ == "__main__":
    main()
