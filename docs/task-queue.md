# Task Queue

_Last updated: 2025-10-07T01-11-00Z_

## Active Tasks

1. **Audit boot-image VM test prerequisites.**
   - Follow the condition checklist in `docs/work-notes/2025-10-07T00-56-30Z-boot-image-vm-condition-plan.md` to confirm host tooling, ISO contents, and VM runtime behaviour all satisfy test expectations.
   - Record pass/fail for each condition and capture supporting logs to unblock subsequent fixes.
2. **Harden BootImageVM prompt handling for ANSI-coloured shells.**
   - Extend the login matcher or normalise serial output so `_login` reliably detects prompts that include escape sequences before re-attempting sudo escalation.
   - Add regression coverage so bracketed-paste toggles and colour codes no longer stall the test.
   - After implementing the fix, re-run the VM test to confirm the hypothesis and observe whether other outstanding issues (serial console drop-out, storage provisioning warning) persist.
3. **Diagnose pre-nixos storage provisioning error.**
   - Serial log reports "Storage detection encountered an error; provisioning ran in plan-only mode." Determine underlying journal entries and how to surface them for debugging.
4. **Enable persistent serial console output through boot.**
   - Confirm kernel parameters include `console=ttyS0,115200` and add configuration changes if missing so subsequent boots retain serial logging after init.
5. **Capture follow-up boot timings after configuration adjustments.**
   - Once fixes are implemented, re-run the VM test to measure improved timings and compare against current 10m21s wall clock.

## Recently Completed

- 2025-10-07T01-11-00Z - Identified root cause of boot-image VM login failure: colourised Bash prompt emits ANSI escapes that our regex does not match, preventing `_login` from issuing `sudo -i`. See `docs/work-notes/2025-10-07T01-11-00Z-boot-image-vm-root-prompt-analysis.md`.
- 2025-10-06T15-54-30Z - Captured baseline boot-image VM test output, timings, and serial log for reference.
