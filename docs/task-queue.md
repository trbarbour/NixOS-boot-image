# Task Queue

_Last updated: 2025-10-19T01-30-00Z_

## Active Tasks

1. **Resume sshd/pre-nixos verification with the passing harness.**
   - Rebuild the ISO if recent SSH changes land, then execute `pytest tests/test_boot_image_vm.py -vv --boot-image-debug` and pause once networking configures.
   - From the debug shell, capture `systemctl list-jobs`, `systemctl status pre-nixos`, `journalctl -u pre-nixos.service -b`, and `systemctl status sshd` to confirm the non-blocking restart keeps sshd independent of `pre-nixos.service`.
   - Archive the debug transcripts alongside harness/serial logs under a new timestamped directory in `docs/work-notes/`, noting the storage status reported by `/run/pre-nixos/storage-status`.
   - 2025-10-14T00-00-00Z captures still show sshd stuck in `start-pre` even though `pre-nixos.service` completes; retake the capture now that Task 1 restored end-to-end provisioning. 【F:docs/work-notes/2025-10-14T00-00-00Z-sshd-pre-nixos-verify/serial.log†L70-L141】

2. **Confirm dependent services behave with sshd held back by `wantedBy = []`.**
   - During the resumed VM debug session, audit `systemctl list-dependencies sshd` and `systemctl status secure_ssh` to ensure nothing else races sshd online before provisioning finishes.
   - Cross-reference captures with earlier runs to document behaviour changes after the successful regression fix.
   - 2025-10-10T04-47-41Z manual debug showed dependent services still assuming sshd starts automatically; re-check with the latest ISO while the VM is paused from Task 1. 【F:docs/work-notes/2025-10-10T04-47-41Z-boot-image-vm-debug-session/serial.log†L40-L137】

3. **Verify the embedded SSH public key inside the ISO artefact.**
   - Use `unsquashfs -ll` (or mount the image) on the freshly built ISO to confirm `pre_nixos/root_key.pub` matches the generated fingerprint.
   - If the key is missing, audit the `flake.nix` wiring and environment variables that feed `PRE_NIXOS_ROOT_KEY` into the build, and document findings.

4. **Probe the storage-detection path from inside the debug VM.**
   - Within the paused VM, run `pre-nixos-detect-storage` and `pre-nixos --plan-only` to ensure the blank disk is detected correctly post-fix.
   - Inspect `/run/pre-nixos/storage-status`, `/var/log/pre-nixos/disko-config.nix`, and any running `disko`/`wipefs` processes to confirm provisioning success.
   - Preserve command output in investigation notes for future comparison.

5. **Establish a known-good baseline with an upstream minimal NixOS ISO.**
   - Boot `nixpkgs#nixosConfigurations.installerMinimal.x86_64-linux.config.system.build.isoImage` (or similar) with the harness settings.
   - Verify DHCP, storage, and console interaction to validate host assumptions now that our image passes.

6. **Compare harness and service toggles to isolate any remaining regressions.**
   - Boot the baseline ISO, install the `pre-nixos` package manually, and execute `pre-nixos --plan-only` without the systemd unit.
   - Rebuild our ISO with targeted toggles (e.g., temporarily disabling `pre-nixos.service`) to observe behavioural changes, documenting contrasts.

7. **Expand unit coverage and regression safeguards.**
   - Add unit tests for LAN identification, SSH key propagation, and storage-plan execution edge cases surfaced during the outage.
   - Ensure structured logs are asserted in the unit suite so regressions surface before integration tests.

8. **Harden BootImageVM diagnostics.**
   - Keep improving the login helper so root escalation transcripts and serial output are captured automatically on failure.
   - Collect `journalctl -u pre-nixos.service -b` and `systemctl status pre-nixos` whenever provisioning or DHCP waits time out, and emit ISO metadata (store path, hash, root key fingerprint) in logs.
   - 2025-10-09T15-30-00Z improvements laid the groundwork; continue iterating as new edge cases appear. 【F:docs/work-notes/2025-10-09T15-30-00Z-boot-image-vm-test-attempt.md†L1-L42】

9. **Rebuild the boot image with future network/storage tweaks and rerun the VM regression.**
   - Use the now-working dev shell workflow to produce new ISOs whenever changes land, then run `pytest tests/test_boot_image_vm.py -vv` without interruption to validate end-to-end behaviour.
   - Promote passing serial/journal logs to `docs/boot-logs/` with updated test reports.

10. **Capture follow-up boot timings after configuration adjustments.**
    - With the harness stable, collect new timing data after each substantive change to detect regressions early.

11. **Ensure the full test suite runs without skips.**
    - Audit pytest skips and prerequisites so the VM suite remains active, and maintain CI coverage for the entire suite.

## Recently Completed

- 2025-10-19T01-15-00Z - BootImageVM harness now regains a root shell for privileged probes and waits for `pre-nixos` to become inactive, removing the LVM permission failure and IPv4 buffering. 【F:docs/work-notes/2025-10-18T22-57-17Z-boot-image-vm-regression/harness.log†L120-L185】
- 2025-10-18T22-57-17Z - `nix develop .#bootImageTest -c pytest tests/test_boot_image_vm.py -vv` passes both VM cases end-to-end using the shared `/tmp/boot-image-shared-tmp`; logs archived under `docs/work-notes/2025-10-18T22-57-17Z-boot-image-vm-regression/` with summary in `docs/test-reports/2025-10-18T22-57-17Z-boot-image-vm-test.md`. 【F:docs/work-notes/2025-10-18T22-57-17Z-boot-image-vm-regression/harness.log†L1-L185】【F:docs/test-reports/2025-10-18T22-57-17Z-boot-image-vm-test.md†L1-L26】
- 2025-10-18T17-45-00Z - The `bootImageTest` dev shell enforces a shared `/tmp/boot-image-shared-tmp`, letting `nix build .#bootImage` succeed without manual overrides; the ISO completed at `/nix/store/83vw736vi27nryfaa3i2bawy435xspqm-…-x86_64-linux.iso`. 【F:flake.nix†L120-L135】【029fd2†L1-L68】【0054d1†L1-L4】
- 2025-10-17T03-10-54Z - Disko label regression is resolved and the impure ISO build now completes: `/run/pre-nixos/storage-status` reaches `STATE=applied`/`DETAIL=auto-applied`, and the harness records the rebuilt store path before launching the VM. 【F:docs/test-reports/2025-10-17T03-10-54Z-boot-image-vm-test.md†L1-L12】【F:docs/work-notes/2025-10-17T03-20-16Z-boot-image-vm-regression/harness.log†L1-L5】
- 2025-10-14T05-00-00Z - Added HDD-only regression coverage in `tests/test_apply.py` that asserts the generated disko configuration provisions both disks, keeps `md0` bound to the `main` volume group, and retains the slash LV mount at root.
- 2025-10-14T01-01-49Z - HDD-only plans now populate `plan["disko"]` and the single-disk regression test asserts the emitted disk/LVM layout (`pre_nixos/planner.py`, `tests/test_plan_storage.py`).
- 2025-10-13T00-00-00Z - `secure_ssh` now invokes `systemctl reload-or-restart --no-block sshd` with unit coverage guarding against regressions; follow-up VM runs will confirm the oneshot no longer blocks on sshd.
 - 2025-10-11T04-10-39Z - Pre-built the boot image ahead of VM regressions, recording `/nix/store/d8xvgbl51svz0axi2n0xzrij330hw6i4-nixos-24.05.20241230.b134951-x86_64-linux.iso` in `docs/work-notes/2025-10-11T04-10-39Z-boot-image-prebuild.md` for reuse.
- 2025-10-10T13-05-00Z - Confirmed structured `pre_nixos` journal entries are present in the debug session logs (former queue item 2). No logging configuration changes required; see `docs/work-notes/2025-10-10T13-05-00Z-pre-nixos-journalctl-verification.md` for details.
- 2025-10-08T06-10-00Z - Confirmed the boot image crashed because `systemd-networkd.service` is absent, captured `journalctl -u pre-nixos.service`, and planned fixes (enable networkd + guard restarts). See `docs/work-notes/2025-10-08T06-10-00Z-pre-nixos-networkd-investigation.md` and new serial log `docs/boot-logs/2025-10-08T06-10-00Z-serial.log`.
- 2025-10-07T04-01-53Z - Verified `boot.kernelParams` for the pre-installer ISO include `console=ttyS0,115200n8` and `console=tty0`; no further changes required for persistent serial logging. See `docs/work-notes/2025-10-07T04-01-53Z-serial-console-verification.md`.
- 2025-10-07T03-58-17Z - Identified `wipefs -n /dev/fd0` failures as the source of the storage detection error, taught the detector to ignore `/dev/fd*`, and ensured VM tests print `journalctl -u pre-nixos.service` on provisioning failures; see `docs/work-notes/2025-10-07T03-58-17Z-pre-nixos-storage-detection.md`.
- 2025-10-07T03-11-58Z - Hardened BootImageVM login handling against ANSI escape sequences; see `tests/test_boot_image_vm.py` and regression log `docs/test-reports/2025-10-07T03-11-58Z-boot-image-vm-test.md` for details (remaining provisioning/network issues persist).
- 2025-10-07T02-11-38Z - Audited boot-image VM prerequisites; see `docs/test-reports/2025-10-07T02-11-38Z-boot-image-prereq-audit.md` for detailed pass/fail outcomes and recommended follow-ups.
- 2025-10-07T01-11-00Z - Identified root cause of boot-image VM login failure: colourised Bash prompt emits ANSI escapes that our regex does not match, preventing `_login` from issuing `sudo -i`. See `docs/work-notes/2025-10-07T01-11-00Z-boot-image-vm-root-prompt-analysis.md`.
- 2025-10-06T15-54-30Z - Captured baseline boot-image VM test output, timings, and serial log for reference.
