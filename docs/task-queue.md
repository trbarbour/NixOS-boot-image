# Task Queue

_Last updated: 2025-10-11T02-57-09Z_

## Active Tasks

1. **Pre-build boot image before VM regressions.**
   - Run `nix build .#bootImage --impure --print-out-paths` before invoking pytest so the build phase is explicit and timestamps can be recorded in the work notes.
   - Capture the resulting store path and completion time in the associated investigation log to ensure future reruns use the same artefact unless code changes require a rebuild.
   - 2025-10-11T03-44-19Z - Cold `nix build` completed after ~35 minutes; recorded `/nix/store/4iyqq7b17l7pnpmwrpzcwhspdbybqfmf-nixos-24.05.20241230.b134951-x86_64-linux.iso` in `docs/work-notes/2025-10-11T03-44-19Z-boot-image-prebuild.md` for reuse.

2. **Reproduce the boot-image VM failure with maximum visibility.**
   - After the ISO build finishes, execute `pytest tests/test_boot_image_vm.py -vv --boot-image-debug` and remain in the interactive session to inspect the guest instead of tearing it down immediately.
   - Collect `systemctl status pre-nixos`, `journalctl -u pre-nixos.service -b`, `networkctl status lan`, `ip -o link`, and `/run/pre-nixos/storage-status` from the debug shell, then archive the transcripts (`harness.log`, `serial.log`, and shell captures) under `docs/work-notes/`.
   - Cross-reference the captured evidence with earlier runs to highlight changes in behaviour as fixes land.
   - 2025-10-10T04-47-41Z - Manual debug session gathered the requested evidence (`docs/work-notes/2025-10-10T04-47-41Z-boot-image-vm-debug-session/`). `pre-nixos.service` remained `activating` while `pre_nixos.network.wait_for_lan` looped; `networkctl status lan` reported `Interface "lan" not found`, and `ip -o link` listed only `lo` plus a downed `ens4`. BootImageVM also failed to escalate to root; future reproductions must capture the sudo transcript.

3. **Verify the embedded SSH public key inside the ISO artefact.**
   - Use `unsquashfs -ll` (or mount the image) on the freshly built ISO to confirm `pre_nixos/root_key.pub` is present and matches the generated key fingerprint.
   - If the key is missing, audit the `flake.nix` wiring and environment variables so `PRE_NIXOS_ROOT_KEY` is propagated during the build. Record findings alongside the reproduction logs.

4. **Probe the storage-detection path from inside the debug VM.**
   - Within the paused VM, run `pre-nixos-detect-storage` and `pre-nixos --plan-only` to see whether the blank disk is mis-detected as provisioned.
   - Inspect `/run/pre-nixos/storage-status`, `/var/log/pre-nixos/disko-config.nix`, and any running `disko`/`wipefs` processes to understand where provisioning halts.
   - Preserve command output in the investigation notes so we can compare against future fixes.

5. **Establish a known-good baseline with an upstream minimal NixOS ISO.**
   - Build `nixpkgs#nixosConfigurations.installerMinimal.x86_64-linux.config.system.build.isoImage` (or similar) and boot it with the same QEMU parameters used by the harness.
   - Verify DHCP, storage visibility, and console interaction work under the harness to validate host-side assumptions.

6. **Compare harness and service toggles to isolate the regression.**
   - Boot the baseline ISO, install the `pre-nixos` package manually, and execute `pre-nixos --plan-only` to observe behaviour without the systemd unit.
   - Rebuild our ISO with targeted toggles (e.g., temporarily disabling `pre-nixos.service`) to see which combinations allow networking to succeed, then document the contrasts.

7. **Deep-dive instrumentation around the failure point.**
   - Use the debug session to capture `journalctl -u pre-nixos.service -b`, `_run` command exit codes, and the generated `disko` configuration to determine whether execution stops before or after plan application.
   - Extend logging as required and ensure every timeout automatically saves the relevant journal excerpts for offline review.

8. **Expand unit coverage and regression safeguards.**
   - Add focused unit tests that exercise LAN identification, SSH key propagation, and storage-plan execution edge cases uncovered during the investigation.
   - Ensure new structured logs are asserted in the unit suite so regressions surface before integration tests.

9. **Harden BootImageVM root escalation and capture richer failure context.**
   - Extend the login helper with step-by-step logging, fail fast when `sudo -i` does not yield a root shell, and surface the captured transcript in assertion messages so we can observe why escalation stalls.
   - Automatically collect `journalctl -u pre-nixos.service -b` and `systemctl status pre-nixos` whenever storage provisioning or DHCP waits time out, ensuring every failure includes the relevant journal excerpts.
   - Emit the booted ISO derivation path, hash, and embedded root key fingerprints in the harness logs to rule out stale artefacts or mismatched images during investigations.
   - 2025-10-09T15-30-00Z - BootImageVM harness now records step-by-step transcripts, journals on storage/network timeouts, and ISO metadata (`tests/test_boot_image_vm.py`). `pytest tests/test_boot_image_vm.py` was interrupted after 4m46s because `nix build .#bootImage` continued compiling dependencies; rerun once the derivation has finished building to validate the changes end-to-end.
   - 2025-10-09T23-39-12Z - Added serial-output capture to the login transcript and documented the renewed pytest attempt (`docs/work-notes/2025-10-09T23-39-12Z-boot-image-vm-test-attempt.md`). The run was aborted after ~350s while `nix build .#bootImage` continued compiling, so the enhanced logging still needs in-situ validation once the build completes.
   - 2025-10-10T00-07-04Z - Testing policy updated: `pytest tests/test_boot_image_vm.py -vv` must be allowed to run without interruption for at least 30 minutes to capture the full provisioning behaviour before declaring failure.
   - 2025-10-10T00-17-07Z - Latest pytest run completed fixture setup after 9m38s and failed with `KeyError: 0` because `nix path-info --json` returned a mapping; documented results in `docs/work-notes/2025-10-10T00-17-07Z-boot-image-vm-test-attempt.md`.
   - 2025-10-10T00-47-08Z - Pytest ran for 22m51s without interruption; both VM tests failed waiting for storage status and IPv4 despite new logging. Full notes in `docs/work-notes/2025-10-10T00-47-08Z-boot-image-vm-test-attempt.md`.

10. **Rebuild the boot image with the network fixes and rerun the VM regression.**
    - 2025-10-08T13-51-16Z run (`pytest tests/test_boot_image_vm.py`) still fails: `test_boot_image_provisions_clean_disk` flagged `disko`, `lsblk`, and `wipefs` as missing and `test_boot_image_configures_network` timed out without an IPv4 lease. The captured journal shows `pre_nixos.network.identify_lan` raising `OSError: [Errno 22] Invalid argument` when reading the NIC carrier file (see `docs/test-reports/2025-10-08T13-51-16Z-boot-image-vm-test.md`).
    - Prior run (2025-10-08T07-36-29Z) exhibited the same symptoms on the earlier ISO build; see `docs/test-reports/2025-10-08T07-36-29Z-boot-image-vm-test.md` for historical context.
    - Implement a fix for the carrier read failure (e.g. guard `identify_lan` against `OSError` and confirm the interface detection logic tolerates virtio NICs without link state).
    - Stabilise the command-availability probe so the first `command -v` execution does not race the prompt update.
    - Rebuild the ISO, rerun the VM regression, and confirm provisioning, DHCP, and SSH succeed. Promote fresh serial/journal logs to `docs/boot-logs/` together with an updated test report when the run passes.
    - 2025-10-09T01-32-01Z run exercised the updated carrier handling and command probe (`pytest tests/test_boot_image_vm.py`). Command checks now report `OK`, and `identify_lan` no longer crashes, but provisioning still timed out waiting for `pre-nixos` to populate `/run/pre-nixos/storage-status` and no IPv4 lease appeared on `lan`. See `docs/test-reports/2025-10-09T01-32-01Z-boot-image-vm-test.md` and the new serial log at `docs/boot-logs/2025-10-09T01-32-01Z-serial.log`.

11. **Capture follow-up boot timings after configuration adjustments.**
    - The latest run (2025-10-08T00-41-32Z) still failed after 1000.26s because provisioning aborted; rerun once the networking fix is validated to measure meaningful timings.

12. **Ensure the full test suite runs without skips (especially `test_boot_image_vm`).**
    - Audit pytest skips and environment prerequisites; install or document missing dependencies so the VM test executes rather than skipping.
    - Maintain scripts or nix expressions that exercise the entire suite as part of CI/regression testing.

## Recently Completed

- 2025-10-10T13-05-00Z - Confirmed structured `pre_nixos` journal entries are present in the debug session logs (former queue item 2). No logging configuration changes required; see `docs/work-notes/2025-10-10T13-05-00Z-pre-nixos-journalctl-verification.md` for details.
- 2025-10-08T06-10-00Z - Confirmed the boot image crashed because `systemd-networkd.service` is absent, captured `journalctl -u pre-nixos.service`, and planned fixes (enable networkd + guard restarts). See `docs/work-notes/2025-10-08T06-10-00Z-pre-nixos-networkd-investigation.md` and new serial log `docs/boot-logs/2025-10-08T06-10-00Z-serial.log`.
- 2025-10-07T04-01-53Z - Verified `boot.kernelParams` for the pre-installer ISO include `console=ttyS0,115200n8` and `console=tty0`; no further changes required for persistent serial logging. See `docs/work-notes/2025-10-07T04-01-53Z-serial-console-verification.md`.
- 2025-10-07T03-58-17Z - Identified `wipefs -n /dev/fd0` failures as the source of the storage detection error, taught the detector to ignore `/dev/fd*`, and ensured VM tests print `journalctl -u pre-nixos.service` on provisioning failures; see `docs/work-notes/2025-10-07T03-58-17Z-pre-nixos-storage-detection.md`.
- 2025-10-07T03-11-58Z - Hardened BootImageVM login handling against ANSI escape sequences; see `tests/test_boot_image_vm.py` and regression log `docs/test-reports/2025-10-07T03-11-58Z-boot-image-vm-test.md` for details (remaining provisioning/network issues persist).
- 2025-10-07T02-11-38Z - Audited boot-image VM prerequisites; see `docs/test-reports/2025-10-07T02-11-38Z-boot-image-prereq-audit.md` for detailed pass/fail outcomes and recommended follow-ups.
- 2025-10-07T01-11-00Z - Identified root cause of boot-image VM login failure: colourised Bash prompt emits ANSI escapes that our regex does not match, preventing `_login` from issuing `sudo -i`. See `docs/work-notes/2025-10-07T01-11-00Z-boot-image-vm-root-prompt-analysis.md`.
- 2025-10-06T15-54-30Z - Captured baseline boot-image VM test output, timings, and serial log for reference.
