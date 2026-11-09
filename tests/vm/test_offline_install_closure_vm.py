"""The installed system must build offline from the ISO's store (user report,
2026-11-08; task queue items 12 and 43).

On the first BIOS PC (no DHCP, outbound traffic blocked) the TUI provisioned
the disks with 0.26.2 and started ``nixos-install``, which then planned to
build 1907 derivations, starting from the stage-0 compiler bootstrap
(``hex0-seed``, ``stage0-posix``, gcc and glibc sources), and failed on the
first download (``gawk-5.4.1.tar.xz``).  An offline install should only copy
what the ISO carries and build the configuration's own small derivations.

The machine is the SATA disk-class one.  ``pre-nixos --install-now`` writes
the real configuration under ``/mnt``; ``nixos-install`` is replaced by a
dry-run build of that configuration with every substituter disabled, which
lists what an offline install would have to build from the ISO's store.  The
stand-in exits non-zero so pre-nixos does not reboot the VM.
"""

from __future__ import annotations

import re

import pytest

from tests.vm.controller import BootImageVM

pytestmark = [pytest.mark.vm, pytest.mark.slow]

APPLY_TIMEOUT = 1500
DRY_RUN_TIMEOUT = 1800

# Derivations whose presence means the C toolchain would be bootstrapped from
# source: never possible offline.
BOOTSTRAP_MARKERS = ("stage0-posix", "hex0-seed", "bootstrap-tools", "-gcc-", "glibc-2.")

STAND_IN = """#!/bin/sh
# Stand-in for nixos-install (tests/vm/test_offline_install_closure_vm.py).
nix-build '<nixpkgs/nixos>' -A system -I nixos-config=/mnt/etc/nixos/configuration.nix \\
  --dry-run --option substituters '' > /tmp/offline-dry-run.txt 2>&1
echo "dry-run-exit=$?" >> /tmp/offline-dry-run.txt
exit 1
"""


def _ssd_name(vm: BootImageVM) -> str:
    listing = vm.run_as_root_checked(
        'for d in /sys/block/sd*; do echo "${d##*/} $(cat $d/size)"; done', timeout=120
    )
    sizes = [line.split() for line in listing.splitlines() if line.startswith("sd")]
    (name,) = [name for name, size in sizes if int(size) * 512 == 4 * 1024**3]
    return name


ANSI = re.compile(r"\x1b\[[0-9;?]*[A-Za-z]")


def _to_build(dry_run: str) -> list[str]:
    """The derivations listed under "will be built" by ``nix-build --dry-run``.

    The serial transcript carries terminal escapes and carriage returns
    (``\x1b[?2004l\r`` before the header on 2026-11-09), so lines are
    cleaned first.
    """

    built: list[str] = []
    collecting = False
    # Split on newlines only: splitlines() also splits on the stray "\r"s,
    # leaving empty lines that ended the list.
    for raw in dry_run.split("\n"):
        line = ANSI.sub("", raw).replace("\r", "")
        if re.search(r"(these \d+ derivations|this derivation) will be built:", line):
            collecting = True
            continue
        if collecting and line.startswith("  /nix/store/"):
            built.append(line.strip())
            continue
        if collecting and not line.strip():
            # "\r\r\n" endings become blank lines in a text-mode read.
            continue
        collecting = False
    return built


def test_installed_system_builds_offline(boot_image_vm_with_ambiguous_ssd: BootImageVM) -> None:
    vm = boot_image_vm_with_ambiguous_ssd
    vm.wait_for_storage_status()
    ssd = _ssd_name(vm)

    vm.run_as_root_checked(
        f"pre-nixos --ssd {ssd} --no-auto-install > /tmp/provision.log 2>&1", timeout=APPLY_TIMEOUT
    )
    vm.run_as_root_checked("findmnt -n /mnt/boot", timeout=60)

    vm.run_as_root_checked(
        "mkdir -p /root/shim && cat > /root/shim/nixos-install <<'EOF'\n"
        + STAND_IN
        + "EOF\nchmod +x /root/shim/nixos-install",
        timeout=60,
    )
    vm.run_as_root(
        "PATH=/root/shim:$PATH pre-nixos --install-now > /tmp/install.log 2>&1; true",
        timeout=DRY_RUN_TIMEOUT,
    )
    dry_run = vm.run_as_root("cat /tmp/offline-dry-run.txt", timeout=300)
    built = _to_build(dry_run)
    bootstrap = [drv for drv in built if any(marker in drv for marker in BOOTSTRAP_MARKERS)]
    summary = f"{len(built)} derivations to build offline; first 40:\n" + "\n".join(built[:40])
    assert "dry-run-exit=0" in dry_run, dry_run[-4000:]
    if bootstrap:
        # Evidence for #340: which nixpkgs nixos-install evaluates, and whether
        # its gawk is the ISO's.
        diagnostics = vm.run_as_root(
            "echo NIX_PATH=$NIX_PATH; "
            "echo find-file=$(nix-instantiate --find-file nixpkgs); "
            "echo channel=$(readlink -f /nix/var/nix/profiles/per-user/root/channels/nixos); "
            "echo lib-version=$(nix-instantiate --eval -E '(import <nixpkgs> {}).lib.version'); "
            "echo iso-version=$(cat /run/current-system/nixos-version); "
            "echo eval-gawk=$(nix-instantiate --eval -E '(import <nixpkgs> {}).gawk.outPath'); "
            "echo iso-gawk=$(readlink -f /run/current-system/sw/bin/gawk); "
            "echo eval-stdenv=$(nix-instantiate --eval -E '(import <nixpkgs> {}).stdenv.outPath'); "
            "echo iso-system-pkgs-path=$(nix-instantiate --eval -E 'builtins.toString <nixpkgs>'); "
            "ls /nix/store | grep -c -- '-stdenv-linux$'; true",
            timeout=600,
        )
        pytest.fail(f"the toolchain would be built from source:\n{summary}\n--- diagnostics ---\n{diagnostics}")
