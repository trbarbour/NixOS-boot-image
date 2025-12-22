"""VM integration scenarios migrated from the legacy monolithic test file."""

from __future__ import annotations

import re

import pytest

from tests.vm.fixtures import SSHKeyPair
from tests.vm.controller import BootImageVM

pytestmark = [pytest.mark.vm, pytest.mark.slow]


def test_boot_image_provisions_clean_disk(boot_image_vm: BootImageVM) -> None:
    boot_image_vm.assert_commands_available("disko", "findmnt", "lsblk", "wipefs")
    status = boot_image_vm.wait_for_storage_status()
    if status.get("STATE") != "applied" or status.get("DETAIL") != "auto-applied":
        journal = boot_image_vm.collect_journal("pre-nixos.service")
        pytest.fail(
            "pre-nixos did not auto-apply provisioning:\n"
            f"status={status}\n"
            f"journalctl -u pre-nixos.service:\n{journal}"
        )

    vg_output = boot_image_vm.run_as_root(
        "vgs --noheadings --separator '|' -o vg_name", timeout=120
    )
    vg_names = {line.strip() for line in vg_output.splitlines() if line.strip()}
    assert "main" in vg_names

    lv_output = boot_image_vm.run_as_root(
        "lvs --noheadings --separator '|' -o lv_name,vg_name", timeout=120
    )
    lv_pairs = {
        tuple(part.strip() for part in line.split("|"))
        for line in lv_output.splitlines()
        if line.strip()
    }
    assert ("slash", "main") in lv_pairs


def test_boot_image_configures_network(
    boot_image_vm: BootImageVM,
    boot_ssh_key_pair: SSHKeyPair,
) -> None:
    addr_lines = boot_image_vm.wait_for_ipv4()
    assert any("inet " in line for line in addr_lines)

    status = boot_image_vm.wait_for_unit_inactive("pre-nixos", timeout=180)
    assert status == "inactive"

    ssh_identity = boot_image_vm.run_ssh(
        private_key=boot_ssh_key_pair.private_key,
        command="id -un",
    )
    assert ssh_identity == "root"


def test_boot_image_announces_lan_ipv4_on_serial_console(
    boot_image_vm: BootImageVM,
) -> None:
    boot_image_vm.wait_for_ipv4()
    serial_content = boot_image_vm.log_path.read_text(
        encoding="utf-8", errors="ignore"
    ).replace("\r", "")
    assert re.search(
        r"LAN IPv4 address: \d+\.\d+\.\d+\.\d+", serial_content
    ), "expected LAN IPv4 announcement in serial console log"
