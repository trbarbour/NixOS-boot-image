# Boot image VM regression test - 2025-10-14T04:33:37Z

## Context
- `nix build .#bootImage` (no embedded key) completed successfully; `result -> /nix/store/78bdc10x5c7s07s7h3456slxdg7pdyv2-nixos-24.05.20241230.b134951-x86_64-linux.iso`.
- Running the VM integration tests inside `nix develop .#bootImageTest` required overriding `TMPDIR=/tmp` (the default `/tmp/nix-shell.*` has mode 0700 and breaks the builders that embed the disposable SSH key).
- Command executed for the suite: `nix develop .#bootImageTest -c bash -lc 'export TMPDIR=/tmp; pytest tests/test_boot_image_vm.py'`.

## Result
- Both tests executed and **failed** after ~12 minutes of QEMU runtime.
  - `test_boot_image_provisions_clean_disk` observed `pre-nixos: Provisioning failed.` on the serial console and the final storage status remained `STATE=failed`/`DETAIL=auto-applied` instead of settling in an applied state.
  - `test_boot_image_configures_network` confirmed the LAN interface received `10.0.2.15/24` but `systemctl is-active pre-nixos` never returned `inactive`; instead the harness printed the `ip -o -4 addr` output block.
- The harness logs (serial + command transcript) are archived alongside this report for further debugging.

## Artifacts
- `2025-10-14T04-33-37Z-boot-image-vm-test/harness.log`
- `2025-10-14T04-33-37Z-boot-image-vm-test/serial.log`

## Follow-up
- Investigate why `pre-nixos` exits with `STATE=failed` even though its status detail reports `auto-applied`.
- Track why `systemctl is-active pre-nixos` is returning an `ip` transcript instead of the unit status; confirm whether the harness is issuing the expected command or if prompt handling is leaking prior output.
- Consider adjusting the dev shell to export `TMPDIR=/tmp` automatically so future `nix build --impure` invocations can read the temporary SSH key without manual overrides.
