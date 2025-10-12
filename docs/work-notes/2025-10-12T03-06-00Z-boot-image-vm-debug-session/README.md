# Boot image VM debug session (2025-10-12T03:06:00Z)

## Overview
- Executed `pytest tests/test_boot_image_vm.py -vv --boot-image-debug` after installing `pexpect`.
- The boot image built successfully (`nix build .#bootImage`); the VM booted, auto-logged in as root, and the harness captured serial and harness logs.
- `pre-nixos.service` stayed `activating` and never wrote `/run/pre-nixos/storage-status`; both integration tests failed after ~26 minutes waiting for storage status and verifying that the service deactivated.
- The DHCP client acquired `10.0.2.15/24` on `lan`, confirming that networking progressed further than earlier runs, but the provisioning service still stalled.

## Captured artefacts
- `serial.log` and `harness.log` are copied verbatim from `/tmp/pytest-of-root/pytest-0/boot-image-logs0/`.
- `journalctl_pre_nixos.txt`, `systemctl_status_pre_nixos.txt`, `ip_o_4_lan.txt`, `systemctl_is_active.txt`, and `storage_status.txt` summarise the command outputs parsed from the serial transcript.
- `metadata.json` records the ISO derivation path, deriver, nar hash, and root SSH key fingerprint emitted at the start of the run.

## Gaps and follow-ups
- `networkctl status lan` and `ip -o link` could not be captured because the debug hook requires a TTY for manual interaction; the harness exited the interactive session immediately. Future runs need a real TTY or an automated helper to collect these commands before shutdown.
- The repeated `cat /run/pre-nixos/storage-status` reads confirm the file never appeared; the placeholder in `storage_status.txt` documents the absence of content.
- Attempting `poweroff` from the harness failed (`Interactive authentication required`), so the VM was terminated via the test fixture.

