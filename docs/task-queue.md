# Task Queue

_Last updated: 2025-10-08T07-36-29Z_

## Active Tasks

1. **Rebuild the boot image with the network fixes and rerun the VM regression.**
   - 2025-10-08T07-36-29Z run (`pytest tests/test_boot_image_vm.py`) still failed: both tests reported missing storage tools and no IPv4 assignment even though the ISO was rebuilt from `4hsa8bvg3d073am0pp9ajv056rhqsfr4-...` with a fresh root key (see `docs/test-reports/2025-10-08T07-36-29Z-boot-image-vm-test.md`).
   - Collect `journalctl -u pre-nixos.service` on the next attempt to confirm whether `_systemctl(..., ignore_missing=True)` executed and why provisioning aborts.
   - Verify `pre-nixos` ultimately provisions the blank disk, obtains DHCP on `lan`, and accepts SSH.
   - Capture updated serial logs and promote them to `docs/boot-logs/` together with a fresh test report once the run succeeds.
2. **Capture follow-up boot timings after configuration adjustments.**
   - The latest run (2025-10-08T00-41-32Z) still failed after 1000.26s because provisioning aborted; rerun once the networking fix is validated to measure meaningful timings.
3. **Ensure the full test suite runs without skips (especially `test_boot_image_vm`).**
   - Audit pytest skips and environment prerequisites; install or document missing dependencies so the VM test executes rather than skipping.
   - Maintain scripts or nix expressions that exercise the entire suite as part of CI/regression testing.

## Recently Completed

- 2025-10-08T06-10-00Z - Confirmed the boot image crashed because `systemd-networkd.service` is absent, captured `journalctl -u pre-nixos.service`, and planned fixes (enable networkd + guard restarts). See `docs/work-notes/2025-10-08T06-10-00Z-pre-nixos-networkd-investigation.md` and new serial log `docs/boot-logs/2025-10-08T06-10-00Z-serial.log`.
- 2025-10-07T04-01-53Z - Verified `boot.kernelParams` for the pre-installer ISO include `console=ttyS0,115200n8` and `console=tty0`; no further changes required for persistent serial logging. See `docs/work-notes/2025-10-07T04-01-53Z-serial-console-verification.md`.
- 2025-10-07T03-58-17Z - Identified `wipefs -n /dev/fd0` failures as the source of the storage detection error, taught the detector to ignore `/dev/fd*`, and ensured VM tests print `journalctl -u pre-nixos.service` on provisioning failures; see `docs/work-notes/2025-10-07T03-58-17Z-pre-nixos-storage-detection.md`.
- 2025-10-07T03-11-58Z - Hardened BootImageVM login handling against ANSI escape sequences; see `tests/test_boot_image_vm.py` and regression log `docs/test-reports/2025-10-07T03-11-58Z-boot-image-vm-test.md` for details (remaining provisioning/network issues persist).
- 2025-10-07T02-11-38Z - Audited boot-image VM prerequisites; see `docs/test-reports/2025-10-07T02-11-38Z-boot-image-prereq-audit.md` for detailed pass/fail outcomes and recommended follow-ups.
- 2025-10-07T01-11-00Z - Identified root cause of boot-image VM login failure: colourised Bash prompt emits ANSI escapes that our regex does not match, preventing `_login` from issuing `sudo -i`. See `docs/work-notes/2025-10-07T01-11-00Z-boot-image-vm-root-prompt-analysis.md`.
- 2025-10-06T15-54-30Z - Captured baseline boot-image VM test output, timings, and serial log for reference.
