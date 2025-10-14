# Boot image VM regression follow-up - 2025-10-14T04:35:11Z

## Build
- `nix build .#bootImage` (plain build without `PRE_NIXOS_ROOT_KEY`) succeeded again; the `result` symlink now points at `/nix/store/78bdc10x5c7s07s7h3456slxdg7pdyv2-nixos-24.05.20241230.b134951-x86_64-linux.iso`.
- Verified that embedding the disposable SSH key requires `TMPDIR=/tmp` when running from `nix develop .#bootImageTest`; the default sandbox TMPDIR under `/tmp/nix-shell.*` is `0700` and breaks the builder with `install: cannot stat '/tmp/nix-shell.../env-vars': Permission denied`.

## Test execution
- Command: `nix develop .#bootImageTest -c bash -lc 'export TMPDIR=/tmp; pytest tests/test_boot_image_vm.py'`
- Duration: ~12 minutes end-to-end, including QEMU boot.
- Outcome: both tests failed.
  - `test_boot_image_provisions_clean_disk` logged `pre-nixos: Provisioning failed.` on the serial console and the storage status remained `STATE=failed`/`DETAIL=auto-applied`.
  - `test_boot_image_configures_network` showed the LAN interface obtaining `10.0.2.15/24`, but `systemctl is-active pre-nixos` never returned `inactive`; the harness captured the `ip -o -4 addr` output instead.
- Logs archived at `docs/test-reports/2025-10-14T04-33-37Z-boot-image-vm-test/` (serial + harness transcripts).

## Next steps
- Root-cause why `pre-nixos` marks provisioning as failed despite reporting `DETAIL=auto-applied`.
- Investigate the `systemctl is-active pre-nixos` invocation sequence - determine whether the unit is actually stuck active or if the harness prompt handling is mis-aligning command output.
- Update the dev shell definition (or a helper script) to export `TMPDIR=/tmp` so the disposable SSH key is always readable by the Nix builders.
