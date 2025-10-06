# Task Queue

_Last updated: 2025-10-06T16-05-17Z_

## Active Tasks

1. **Investigate root escalation failure in boot-image VM test.**
   - Captured serial log shows automatic login leaves shell as `nixos` user and `_login` escalates but never observes root prompt.
   - Identify why `sudo -i` path does not yield `root@` prompt even though it should; confirm whether `sudo` is present in image and whether `pexpect` prompt patterns need adjustment.
2. **Diagnose pre-nixos storage provisioning error.**
   - Serial log reports "Storage detection encountered an error; provisioning ran in plan-only mode." Determine underlying journal entries and how to surface them for debugging.
3. **Enable persistent serial console output through boot.**
   - Confirm kernel parameters include `console=ttyS0,115200` and add configuration changes if missing so subsequent boots retain serial logging after init.
4. **Capture follow-up boot timings after configuration adjustments.**
   - Once fixes are implemented, re-run the VM test to measure improved timings and compare against current 10m21s wall clock.

## Recently Completed

- 2025-10-06T15-54-30Z - Captured baseline boot-image VM test output, timings, and serial log for reference.
