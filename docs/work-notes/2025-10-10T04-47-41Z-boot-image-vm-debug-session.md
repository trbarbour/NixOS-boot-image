# Boot image VM manual debug session (2025-10-10T04:47:41Z)

## Summary
- Captured the first full manual debug session using the boot-image VM harness with `--boot-image-debug` wiring in place.
- `pre-nixos.service` stayed in the `activating` state while `pre_nixos.network.wait_for_lan` retried waiting for the `lan` interface alias; no IPv4 lease ever arrived.
- `networkctl status lan` failed because the alias never appeared, while `ip -o link` showed only `lo` and a downed `ens4` interface (altname `enp0s4`).
- Attempting `poweroff` from the harness triggered `polkit` authentication, implying the shell never actually escalated to root despite the harness thinking it had.

## Procedure
1. Ran `python scripts/manual_vm_debug.py --output-dir docs/work-notes/2025-10-10T04-47-41Z-boot-image-vm-debug-session` to spin up QEMU via the `BootImageVM` helper and gather the required artifacts.
2. Waited for the harness to log in automatically, run the evidence commands, and shut the VM down.
3. Archived the generated `harness.log`, `serial.log`, and `manual-debug-output.txt` alongside this note for future analysis.

## Key observations
- `systemctl status pre-nixos` shows the unit stuck in `activating` with `pre_nixos.network.wait_for_lan` repeating after 55s; the JSON log lines captured in `serial.log` confirm the loop is blocking progress.
- `networkctl status lan` reports `Interface "lan" not found.` even though the virtio NIC is present as `ens4`, indicating the rename never happened.
- `ip -o link` output lists `ens4` in the `DOWN` state with no carrier, matching the earlier provisioning failures waiting for DHCP.
- The failed `poweroff` (`Interactive authentication required`) demonstrates the harness did not actually escalate to a root shell, so future runs should double-check the login logic.

## Next steps
- Adjust Task Queue item #1 with the captured evidence and highlight the missing `lan` alias plus sudo escalation mismatch.
- Investigate why `BootImageVM` mis-detects root when auto-login drops to the `nixos` user.
- Plan a focused experiment on `systemd-networkd` to understand why the interface rename never fires under QEMU.

## Artifacts
- `docs/work-notes/2025-10-10T04-47-41Z-boot-image-vm-debug-session/harness.log`
- `docs/work-notes/2025-10-10T04-47-41Z-boot-image-vm-debug-session/serial.log`
- `docs/work-notes/2025-10-10T04-47-41Z-boot-image-vm-debug-session/manual-debug-output.txt`
