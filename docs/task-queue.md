# Task Queue

_Last updated: 2025-10-23T13-52-41Z_

## Active Tasks

1. **Compare harness and service toggles to isolate any remaining regressions.**
   - Boot the baseline ISO, install the `pre-nixos` package manually, and execute `pre-nixos --plan-only` without the systemd unit.
   - Rebuild our ISO with targeted toggles (e.g., temporarily disabling `pre-nixos.service`) to observe behavioural changes, documenting contrasts.

2. **Expand unit coverage and regression safeguards.**
   - Add unit tests for LAN identification, SSH key propagation, and storage-plan execution edge cases surfaced during the outage.
   - Ensure structured logs are asserted in the unit suite so regressions surface before integration tests.

3. **Harden BootImageVM diagnostics.**
   - Keep improving the login helper so root escalation transcripts and serial output are captured automatically on failure.
   - Collect `journalctl -u pre-nixos.service -b` and `systemctl status pre-nixos` whenever provisioning or DHCP waits time out, and emit ISO metadata (store path, hash, root key fingerprint) in logs.
   - 2025-10-09T15-30-00Z improvements laid the groundwork; continue iterating as new edge cases appear. 【F:docs/work-notes/2025-10-09T15-30-00Z-boot-image-vm-test-attempt.md†L1-L42】

4. **Rebuild the boot image with future network/storage tweaks and rerun the VM regression.**
   - Use the now-working dev shell workflow to produce new ISOs whenever changes land, then run `pytest tests/test_boot_image_vm.py -vv` without interruption to validate end-to-end behaviour.
   - Promote passing serial/journal logs to `docs/boot-logs/` with updated test reports.

5. **Capture follow-up boot timings after configuration adjustments.**
    - With the harness stable, collect new timing data after each substantive change to detect regressions early.

6. **Ensure the full test suite runs without skips.**
    - Audit pytest skips and prerequisites so the VM suite remains active, and maintain CI coverage for the entire suite.


## Recently Completed
- 2025-10-19T11-58-00Z - Probed the storage-detection path inside the debug VM and captured `pre-nixos-detect-storage`/`pre-nixos --plan-only` output; see `docs/work-notes/2025-10-19T11-49-37Z-storage-detection-probe/`. 【F:docs/work-notes/2025-10-19T11-49-37Z-storage-detection-probe/storage-detection-probe.md†L1-L205】

- 2025-10-19T02-45-00Z - Verified the boot ISO embeds the generated root key; see `docs/work-notes/2025-10-19T02-45-00Z-embedded-key-verification.md`. 【F:docs/work-notes/2025-10-19T02-45-00Z-embedded-key-verification.md†L1-L58】
- 2025-10-19T01-40-00Z - Audited `systemctl list-dependencies sshd` on the rebuilt ISO: only `sysinit.target` and its mounts remain, `WantedBy=` is empty, and no `secure_ssh` unit exists—evidence captured in `docs/work-notes/2025-10-19T01-11-04Z-sshd-dependency-audit/`. 【F:docs/work-notes/2025-10-19T01-11-04Z-sshd-dependency-audit/sshd-dependency-notes.md†L1-L98】
- 2025-10-19T00-12-43Z - Captured sshd/pre-nixos verification before and after provisioning to confirm the non-blocking restart completes independently; artefacts in `docs/work-notes/2025-10-19T00-12-43Z-sshd-pre-nixos-verification/`.
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
