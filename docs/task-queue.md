# Task Queue

_Last updated: 2025-10-08T00-41-32Z_

## Active Tasks

1. **Root-cause the new VM provisioning failure.**
   - Collect `journalctl -u pre-nixos` from the serial log or via the harness to understand why the service now exits with "Provisioning failed".
   - Analyse the 2025-10-08T00-41-32Z serial log (`docs/boot-logs/2025-10-08T00-41-32Z-serial.log`) from the latest VM run and capture additional diagnostics during the next attempt.
2. **Embed or simulate root SSH key for LAN configuration.**
   - Copy the generated public key into the Python package during `nix build --impure` so `pre_nixos/network.py` sees `root_key.pub` at runtime.
   - Investigate the current `pre-nixos: Provisioning failed` journal entry to confirm the key is honoured and that LAN renaming/DHCP proceed afterwards.
3. **Automate ephemeral SSH key injection for VM tests.**
   - Generate a disposable SSH key pair within the test harness, export the public key via `PRE_NIXOS_ROOT_KEY`, and verify the private key grants SSH access once networking is healthy.
   - Capture and document the key lifecycle so future runs do not depend on persisted keys.
4. **Capture follow-up boot timings after configuration adjustments.**
   - The latest run (2025-10-08T00-41-32Z) still failed after 1000.26s because provisioning aborted; rerun once the tasks above restore networking and storage setup to measure meaningful timings.
5. **Ensure the full test suite runs without skips (especially `test_boot_image_vm`).**
   - Audit pytest skips and environment prerequisites; install or document missing dependencies so the VM test executes rather than skipping.
   - Maintain scripts or nix expressions that exercise the entire suite as part of CI/regression testing.

## Recently Completed

- 2025-10-07T04-01-53Z - Verified `boot.kernelParams` for the pre-installer ISO include `console=ttyS0,115200n8` and `console=tty0`; no further changes required for persistent serial logging. See `docs/work-notes/2025-10-07T04-01-53Z-serial-console-verification.md`.
- 2025-10-07T03-58-17Z - Identified `wipefs -n /dev/fd0` failures as the source of the storage detection error, taught the detector to ignore `/dev/fd*`, and ensured VM tests print `journalctl -u pre-nixos.service` on provisioning failures; see `docs/work-notes/2025-10-07T03-58-17Z-pre-nixos-storage-detection.md`.
- 2025-10-07T03-11-58Z - Hardened BootImageVM login handling against ANSI escape sequences; see `tests/test_boot_image_vm.py` and regression log `docs/test-reports/2025-10-07T03-11-58Z-boot-image-vm-test.md` for details (remaining provisioning/network issues persist).
- 2025-10-07T02-11-38Z - Audited boot-image VM prerequisites; see `docs/test-reports/2025-10-07T02-11-38Z-boot-image-prereq-audit.md` for detailed pass/fail outcomes and recommended follow-ups.
- 2025-10-07T01-11-00Z - Identified root cause of boot-image VM login failure: colourised Bash prompt emits ANSI escapes that our regex does not match, preventing `_login` from issuing `sudo -i`. See `docs/work-notes/2025-10-07T01-11-00Z-boot-image-vm-root-prompt-analysis.md`.
- 2025-10-06T15-54-30Z - Captured baseline boot-image VM test output, timings, and serial log for reference.
