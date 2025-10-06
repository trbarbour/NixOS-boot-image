# Boot Image Test Report - 2025-10-06

- **Tester:** gpt-5-codex (interactive shell)
- **Command:** `time pytest tests/test_boot_image_vm.py -rs`
- **Environment:** Containerized Ubuntu base image with project `.venv` activated; Nix 2.21.2 from `/root/.nix-profile`; QEMU 8.2.2 (no KVM acceleration).
- **Result:** FAILURE during session-scoped fixture `boot_image_vm`; `pexpect` timed out waiting for the booted VM to present any login or shell prompt within 600s.

## Timeline

| Stage | Start (UTC) | End (UTC) | Duration | Notes |
| --- | --- | --- | --- | --- |
| `nix build .#bootImage --no-link --print-out-paths` | 06:25 | ~06:41 | ~16m | Observed via `ps`; heavy `mksquashfs` dominated the build. |
| QEMU boot + login handshake | 06:41 | 06:51 | ~10m | Serial log captured ISOLINUX menu + kernel/initrd load, but nothing beyond; timeout triggered at 600s. |
| Total pytest wall clock | 06:25 | 06:51 | 25m23s | Matches `time` output. |

## Console Log Snapshot

Saved a sanitized copy of the QEMU serial output at `docs/boot-logs/2025-10-06T0641Z-serial-log.txt`. Excerpt:

```
ISOLINUX 6.04   Copyright (C) 1994-2015 H. Peter Anvin et al
Automatic boot in 10 seconds... Automatic boot in 9 seconds...
Automatic boot in 8 seconds... Automatic boot in 7 seconds...
Loading /boot/bzImage... ok
Loading /boot/initrd...ok
```

## Diagnosis

* The boot process never writes a login banner to the serial console, so `BootImageVM._login` does not match any of its expected patterns.
* The ISO selected by the `bootImage` flake output appears to boot with a graphical console by default. Once ISOLINUX hands control to the kernel there is no `console=ttyS0,115200` kernel parameter, leaving the serial line silent after the initial loader messages.

## Next Actions

1. Inspect the NixOS configuration that builds the ISO and ensure serial console redirection is enabled (e.g., via `boot.kernelParams = [ "console=ttyS0,115200" "console=tty0" ];`).
2. Rebuild the ISO with the adjusted kernel parameters, re-run the integration tests, and compare the serial log against the saved baseline.
3. Automate capture of timing metrics (build vs boot) so future runs can quickly confirm whether caching is effective.
