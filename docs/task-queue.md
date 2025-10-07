# Task Queue

_Last updated: 2025-10-07T03-11-58Z_

## Active Tasks

1. **Diagnose pre-nixos storage provisioning error.**
   - Serial log reports "Storage detection encountered an error; provisioning ran in plan-only mode." Determine underlying journal entries and how to surface them for debugging.
2. **Enable persistent serial console output through boot.**
   - Confirm kernel parameters include `console=ttyS0,115200` and add configuration changes if missing so subsequent boots retain serial logging after init.
3. **Capture follow-up boot timings after configuration adjustments.**
   - Once fixes are implemented, re-run the VM test to measure improved timings and compare against current 10m21s wall clock.
4. **Embed or simulate root SSH key for LAN configuration.**
   - Provide a `pre_nixos/root_key.pub` or set `PRE_NIXOS_ROOT_KEY` during ISO build/testing so `configure_lan` can rename the NIC to `lan` and enable DHCP.
   - Document temporary key management or adjust the module to permit DHCP without SSH hardening for automated tests.

## Recently Completed

- 2025-10-07T03-11-58Z - Hardened BootImageVM login handling against ANSI escape sequences; see `tests/test_boot_image_vm.py` and regression log `docs/test-reports/2025-10-07T03-11-58Z-boot-image-vm-test.md` for details (remaining provisioning/network issues persist).
- 2025-10-07T02-11-38Z - Audited boot-image VM prerequisites; see `docs/test-reports/2025-10-07T02-11-38Z-boot-image-prereq-audit.md` for detailed pass/fail outcomes and recommended follow-ups.
- 2025-10-07T01-11-00Z - Identified root cause of boot-image VM login failure: colourised Bash prompt emits ANSI escapes that our regex does not match, preventing `_login` from issuing `sudo -i`. See `docs/work-notes/2025-10-07T01-11-00Z-boot-image-vm-root-prompt-analysis.md`.
- 2025-10-06T15-54-30Z - Captured baseline boot-image VM test output, timings, and serial log for reference.
