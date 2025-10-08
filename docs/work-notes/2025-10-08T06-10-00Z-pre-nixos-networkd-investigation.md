# Pre-NixOS networkd failure investigation

- **Timestamp:** 2025-10-08T06:10:00Z (UTC)
- **Objective:** Determine why `pre-nixos.service` exits with `Provisioning failed` in the latest VM regression run.

## Actions
- Reused the previously built boot image and ephemeral SSH key from the regression test.
- Launched the ISO inside QEMU with the test harness' `BootImageVM` helper to reach the failure state deterministically.
- Collected `/run/pre-nixos/storage-status` and `journalctl -u pre-nixos.service -b` from the live VM.
- Archived the serial console transcript to `docs/boot-logs/2025-10-08T06-10-00Z-serial.log` for reference.

## Findings
- `pre-nixos` detected the virtio NIC (`configure_lan: detected active interface 'ens4'`) and attempted to restart `systemd-networkd`.
- The restart failed with `Unit systemd-networkd.service not found.` and raised `subprocess.CalledProcessError`, aborting `pre-nixos` before storage provisioning could begin.
- Because the service crashed, the boot image never wrote `/run/pre-nixos/storage-status` beyond `STATE=failed`, and DHCP never executed, explaining the missing LAN address in the regression test.

## Conclusion
- The boot image does not enable `systemd-networkd`, so the service is absent and any restart fails. The networking stage must tolerate missing units *and* ensure the unit is present on the boot image.
- Fix strategy: enable `systemd.network` in the NixOS module, disable conflicting network managers, and guard `configure_lan` against missing systemd units so provisioning no longer aborts.

## Next steps
- Update `modules/pre-nixos.nix` to enable `systemd.network` and disable NetworkManager on the boot ISO.
- Teach `pre_nixos.network.configure_lan` to treat `systemctl restart systemd-networkd` as best-effort when the unit is missing.
- Re-run the VM regression test to confirm provisioning and DHCP now succeed.
