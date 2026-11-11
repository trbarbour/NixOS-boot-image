"""The installer adopts the static network settings (task queue item 41).

Design: plans/2026-11-11T183853Z-installer-static-network-design.md.

QEMU's user network always offers DHCP, so the installer has an address and
``auto`` would leave it alone.  ``--installer-network yes`` applies the static
settings anyway, which proves the mechanism: the runtime networkd unit takes
precedence over the boot's DHCP unit, and its DNS servers reach
systemd-resolved.  The no-address trigger is covered by unit tests.
"""

from __future__ import annotations

import time

import pytest

from tests.vm.controller import BootImageVM

pytestmark = [pytest.mark.vm, pytest.mark.slow]

STATIC = "10.0.2.20"
GATEWAY = "10.0.2.2"
# Not QEMU's DHCP DNS server (10.0.2.3), so the DHCP setting cannot pass the
# check (Codex on #351).  It need not answer: resolved only has to adopt it.
DNS = "10.0.2.53"


def test_installer_takes_the_static_settings(boot_image_vm: BootImageVM) -> None:
    vm = boot_image_vm
    vm.wait_for_storage_status()
    out = vm.run_as_root(
        "pre-nixos --plan-only"
        f" --install-ip-address {STATIC} --install-netmask 255.255.255.0 --install-gateway {GATEWAY}"
        f" --install-dns {DNS} --installer-network yes > /tmp/static.log 2>&1; echo exit=$?; cat /tmp/static.log",
        timeout=600,
    )
    assert "exit=0" in out, out
    assert f"now uses {STATIC}/24 via {GATEWAY}" in out, out

    deadline = time.monotonic() + 120
    while True:
        addresses = vm.run_as_root("ip -4 -o addr show lan; ip -4 route show default", timeout=60)
        # DNS only from systemd-resolved, not from the unit file (Codex on #351).
        resolved = vm.run_as_root("resolvectl dns lan", timeout=60)
        if (f"inet {STATIC}/24" in addresses and f"default via {GATEWAY}" in addresses
                and DNS in resolved):
            break
        if time.monotonic() > deadline:
            unit = vm.run_as_root("cat /run/systemd/network/10-lan-static.network", timeout=60)
            pytest.fail(f"lan did not take the static settings:\n{addresses}\n{resolved}\n--- unit ---\n{unit}")
        time.sleep(5)
    # DHCP is off for lan: QEMU's DHCP address and DNS server are gone.
    assert "inet 10.0.2.15/" not in addresses, addresses
    assert "10.0.2.3" not in resolved.replace(DNS, ""), resolved
