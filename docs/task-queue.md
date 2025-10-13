# Task Queue

_Last updated: 2025-10-13T00-00-00Z_

## Active Tasks

1. **Verify the sshd/pre-nixos interaction after the non-blocking restart change.**
   - Rebuild the ISO if necessary, then execute `pytest tests/test_boot_image_vm.py -vv --boot-image-debug` and keep the VM paused once networking is configured.
   - From the debug shell, capture `systemctl list-jobs`, `systemctl status pre-nixos`, `journalctl -u pre-nixos.service -b`, and `systemctl status sshd` to confirm the sshd job no longer waits on `pre-nixos.service` now that `secure_ssh` uses `systemctl reload-or-restart --no-block`.
   - Archive the resulting harness log, serial log, and manual command transcripts under a new timestamped directory in `docs/work-notes/`, noting whether `/run/pre-nixos/storage-status` reports `STATE=applied`/`DETAIL=auto-applied`.
   - 2025-10-13T00-05-40Z - Pytest run still fails before SSH checks (`termios.error` prevents interactive debug) but automated capture shows `pre-nixos.service` finishing in 5.8s while `systemctl list-jobs` continues to list `sshd.service` in `start running`. See `docs/work-notes/2025-10-13T00-05-40Z-sshd-pre-nixos-debug/` for harness/serial logs and command outputs.
   - 2025-10-13T13-06-59Z - `collect_sshd_pre_nixos_debug.py` confirms `pre-nixos.service` exits cleanly and storage status reports `STATE=applied`/`DETAIL=auto-applied`, but `systemctl list-jobs` still shows the `sshd.service` start job active and `systemctl status sshd` remains in `start-pre` under `sshd-pre-start`. Artefacts in `docs/work-notes/2025-10-13T13-06-59Z-sshd-pre-nixos-debug/`. 【F:docs/work-notes/2025-10-13T13-06-59Z-sshd-pre-nixos-debug/serial.log†L55-L200】
   - 2025-10-12T17-13-25Z - Automated capture via `scripts/collect_sshd_pre_nixos_debug.py` still documents the pre-change deadlock evidence in `docs/work-notes/2025-10-12T17-13-25Z-sshd-pre-nixos-deadlock/`; repeat the capture once the updated ISO is available for comparison.

2. **Confirm dependent services behave with sshd held back by `wantedBy = []`.**
   - Audit any additional units (e.g., console helpers) that expect to pull `sshd.service` in via `WantedBy` and ensure they explicitly order themselves after `secure_ssh` if necessary.
   - During the VM verification run, check `systemctl list-dependencies sshd` to confirm nothing else attempts to start the service before `secure_ssh` finishes provisioning.

3. **If the hang persists, bisect between plan generation and application.**
   - With the updated ISO booted in debug mode, inspect `journalctl -u pre-nixos.service -b` and `/run/pre-nixos/storage-status` to see whether execution stalls before or after `apply.apply_plan`.
   - Capture the storage plan (`pre-nixos --plan-only`), any running `disko` processes, and related logs so we can split the investigation between plan creation and disk application on subsequent runs.
   - Promote any new discoveries into focused follow-up tasks and update this queue accordingly.

## Backlog (previously active items)

1. **Reproduce the boot-image VM failure with maximum visibility.**
   - After the ISO build finishes, execute `pytest tests/test_boot_image_vm.py -vv --boot-image-debug` and remain in the interactive session to inspect the guest instead of tearing it down immediately.
   - Collect `systemctl status pre-nixos`, `journalctl -u pre-nixos.service -b`, `networkctl status lan`, `ip -o link`, and `/run/pre-nixos/storage-status` from the debug shell, then archive the transcripts (`harness.log`, `serial.log`, and shell captures) under `docs/work-notes/`.
   - 2025-10-12T02-04-19Z - Archived a fresh VM run in `docs/work-notes/2025-10-12T02-04-19Z-boot-image-vm-debug-session/`. `pre-nixos.service` stayed `activating` even though `networkctl status lan` showed `lan` with DHCP `10.0.2.15`; `/run/pre-nixos/storage-status` remained empty. 【F:docs/work-notes/2025-10-12T02-04-19Z-boot-image-vm-debug-session/serial.log†L40-L131】
   - 2025-10-12T03-06-00Z - Re-ran the suite with `--boot-image-debug`; copied the resulting harness/serial logs to `docs/work-notes/2025-10-12T03-06-00Z-boot-image-vm-debug-session/`. `pre-nixos.service` was still `activating` after ~26 minutes, `systemctl status pre-nixos` showed the service stuck in the start job, and `ip -o -4 addr` confirmed `lan` held `10.0.2.15/24`. Manual `networkctl`/`ip -o link` captures were not possible without a TTY. 【F:docs/work-notes/2025-10-12T03-06-00Z-boot-image-vm-debug-session/systemctl_status_pre_nixos.txt†L1-L11】【F:docs/work-notes/2025-10-12T03-06-00Z-boot-image-vm-debug-session/ip_o_4_lan.txt†L1-L3】【F:docs/work-notes/2025-10-12T03-06-00Z-boot-image-vm-debug-session/README.md†L9-L19】
   - 2025-10-12T04-00-25Z - Normalized the manual VM debug transcript so the captured command output renders without stray quote markers (`docs/work-notes/2025-10-12T04-00-25Z-boot-image-vm-debug-session/command-captures.md`).
   - Cross-reference the captured evidence with earlier runs to highlight changes in behaviour as fixes land.
   - 2025-10-10T04-47-41Z - Manual debug session gathered the requested evidence (`docs/work-notes/2025-10-10T04-47-41Z-boot-image-vm-debug-session/`). `pre-nixos.service` remained `activating` while `pre_nixos.network.wait_for_lan` looped; `networkctl status lan` reported `Interface "lan" not found`, and `ip -o link` listed only `lo` plus a downed `ens4`. BootImageVM also failed to escalate to root; future reproductions must capture the sudo transcript.

2. **Verify the embedded SSH public key inside the ISO artefact.**
   - Use `unsquashfs -ll` (or mount the image) on the freshly built ISO to confirm `pre_nixos/root_key.pub` is present and matches the generated key fingerprint.
   - If the key is missing, audit the `flake.nix` wiring and environment variables so `PRE_NIXOS_ROOT_KEY` is propagated during the build. Record findings alongside the reproduction logs.

3. **Probe the storage-detection path from inside the debug VM.**
   - Within the paused VM, run `pre-nixos-detect-storage` and `pre-nixos --plan-only` to see whether the blank disk is mis-detected as provisioned.
   - Inspect `/run/pre-nixos/storage-status`, `/var/log/pre-nixos/disko-config.nix`, and any running `disko`/`wipefs` processes to understand where provisioning halts.
   - Preserve command output in the investigation notes so we can compare against future fixes.

4. **Establish a known-good baseline with an upstream minimal NixOS ISO.**
   - Build `nixpkgs#nixosConfigurations.installerMinimal.x86_64-linux.config.system.build.isoImage` (or similar) and boot it with the same QEMU parameters used by the harness.
   - Verify DHCP, storage visibility, and console interaction work under the harness to validate host-side assumptions.
   - 2025-10-12T00-31-04Z - Documented the overarching half-splitting plan and noted that the first draft of an upstream ISO probe harness still blocks waiting for the VM login prompt (`docs/work-notes/2025-10-12T00-31-04Z-half-splitting-plan.md`).

5. **Compare harness and service toggles to isolate the regression.**
   - Boot the baseline ISO, install the `pre-nixos` package manually, and execute `pre-nixos --plan-only` to observe behaviour without the systemd unit.
   - Rebuild our ISO with targeted toggles (e.g., temporarily disabling `pre-nixos.service`) to see which combinations allow networking to succeed, then document the contrasts.

6. **Deep-dive instrumentation around the failure point.**
   - Use the debug session to capture `journalctl -u pre-nixos.service -b`, `_run` command exit codes, and the generated `disko` configuration to determine whether execution stops before or after plan application.
   - Extend logging as required and ensure every timeout automatically saves the relevant journal excerpts for offline review.

7. **Expand unit coverage and regression safeguards.**
   - Add focused unit tests that exercise LAN identification, SSH key propagation, and storage-plan execution edge cases uncovered during the investigation.
   - Ensure new structured logs are asserted in the unit suite so regressions surface before integration tests.

8. **Harden BootImageVM root escalation and capture richer failure context.**
   - Extend the login helper with step-by-step logging, fail fast when `sudo -i` does not yield a root shell, and surface the captured transcript in assertion messages so we can observe why escalation stalls.
   - Automatically collect `journalctl -u pre-nixos.service -b` and `systemctl status pre-nixos` whenever storage provisioning or DHCP waits time out, ensuring every failure includes the relevant journal excerpts.
   - Emit the booted ISO derivation path, hash, and embedded root key fingerprints in the harness logs to rule out stale artefacts or mismatched images during investigations.
   - 2025-10-09T15-30-00Z - BootImageVM harness now records step-by-step transcripts, journals on storage/network timeouts, and ISO metadata (`tests/test_boot_image_vm.py`). `pytest tests/test_boot_image_vm.py` was interrupted after 4m46s because `nix build .#bootImage` continued compiling dependencies; rerun once the derivation has finished building to validate the changes end-to-end.
   - 2025-10-09T23-39-12Z - Added serial-output capture to the login transcript and documented the renewed pytest attempt (`docs/work-notes/2025-10-09T23-39-12Z-boot-image-vm-test-attempt.md`). The run was aborted after ~350s while `nix build .#bootImage` continued compiling, so the enhanced logging still needs in-situ validation once the build completes.
   - 2025-10-10T00-07-04Z - Testing policy updated: `pytest tests/test_boot_image_vm.py -vv` must be allowed to run without interruption for at least 30 minutes to capture the full provisioning behaviour before declaring failure.
   - 2025-10-10T00-17-07Z - Latest pytest run completed fixture setup after 9m38s and failed with `KeyError: 0` because `nix path-info --json` returned a mapping; documented results in `docs/work-notes/2025-10-10T00-17-07Z-boot-image-vm-test-attempt.md`.
   - 2025-10-10T00-47-08Z - Pytest ran for 22m51s without interruption; both VM tests failed waiting for storage status and IPv4 despite new logging. Full notes in `docs/work-notes/2025-10-10T00-47-08Z-boot-image-vm-test-attempt.md`.

9. **Rebuild the boot image with the network fixes and rerun the VM regression.**
    - 2025-10-08T13-51-16Z run (`pytest tests/test_boot_image_vm.py`) still fails: `test_boot_image_provisions_clean_disk` flagged `disko`, `lsblk`, and `wipefs` as missing and `test_boot_image_configures_network` timed out without an IPv4 lease. The captured journal shows `pre_nixos.network.identify_lan` raising `OSError: [Errno 22] Invalid argument` when reading the NIC carrier file (see `docs/test-reports/2025-10-08T13-51-16Z-boot-image-vm-test.md`).
    - Prior run (2025-10-08T07-36-29Z) exhibited the same symptoms on the earlier ISO build; see `docs/test-reports/2025-10-08T07-36-29Z-boot-image-vm-test.md` for historical context.
    - Implement a fix for the carrier read failure (e.g. guard `identify_lan` against `OSError` and confirm the interface detection logic tolerates virtio NICs without link state).
    - Stabilise the command-availability probe so the first `command -v` execution does not race the prompt update.
    - Rebuild the ISO, rerun the VM regression, and confirm provisioning, DHCP, and SSH succeed. Promote fresh serial/journal logs to `docs/boot-logs/` together with an updated test report when the run passes.
    - 2025-10-09T01-32-01Z run exercised the updated carrier handling and command probe (`pytest tests/test_boot_image_vm.py`). Command checks now report `OK`, and `identify_lan` no longer crashes, but provisioning still timed out waiting for `pre-nixos` to populate `/run/pre-nixos/storage-status` and no IPv4 lease appeared on `lan`. See `docs/test-reports/2025-10-09T01-32-01Z-boot-image-vm-test.md` and the new serial log at `docs/boot-logs/2025-10-09T01-32-01Z-serial.log`.

10. **Capture follow-up boot timings after configuration adjustments.**
    - The latest run (2025-10-08T00-41-32Z) still failed after 1000.26s because provisioning aborted; rerun once the networking fix is validated to measure meaningful timings.

11. **Ensure the full test suite runs without skips (especially `test_boot_image_vm`).**
    - Audit pytest skips and environment prerequisites; install or document missing dependencies so the VM test executes rather than skipping.
    - Maintain scripts or nix expressions that exercise the entire suite as part of CI/regression testing.

## Recently Completed

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
