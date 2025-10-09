# Task Queue

_Last updated: 2025-10-09T15-30-00Z_

## Active Tasks

1. **Harden BootImageVM root escalation and capture richer failure context.**
   - Extend the login helper with step-by-step logging, fail fast when `sudo -i` does not yield a root shell, and surface the captured transcript in assertion messages so we can observe why escalation stalls.
   - Automatically collect `journalctl -u pre-nixos.service -b` and `systemctl status pre-nixos` whenever storage provisioning or DHCP waits time out, ensuring every failure includes the relevant journal excerpts.
   - Emit the booted ISO derivation path, hash, and embedded root key fingerprints in the harness logs to rule out stale artefacts or mismatched images during investigations.
   - 2025-10-09T15-30-00Z - BootImageVM harness now records step-by-step transcripts, journals on storage/network timeouts, and ISO metadata (`tests/test_boot_image_vm.py`). `pytest tests/test_boot_image_vm.py` was interrupted after 4m46s because `nix build .#bootImage` continued compiling dependencies; rerun once the derivation has finished building to validate the changes end-to-end.
2. **Validate host-side assumptions with a known-good ISO and add an interactive debug mode.**
   - Boot a minimal reference NixOS ISO with the current QEMU invocation (`-netdev user,hostfwd=...`) to confirm DHCP/networking work outside the custom image.
   - Provide a `pytest --boot-image-debug` or similar flag that drops into `pexpect.interact()` so we can manually inspect the guest before teardown when future regressions appear.
3. **Instrument pre-nixos internals for precise progress tracking.**
   - Add structured logging around `pre_nixos.network.configure_lan`, `pre_nixos.apply.apply_plan`, and related steps so journals clearly mark start/end of each action and record command exit codes.
   - Build focused unit tests (using fake sysfs/device trees) that exercise the LAN identification and storage planning paths to catch regressions without full VM boots.
4. **Run targeted in-VM experiments to converge on the provisioning stall.**
   - Re-run `pre-nixos` manually inside the VM (`systemd-run` or direct execution) while tailing its journal to pinpoint the exact blocking operation.
   - Capture `networkctl status lan`, `systemctl status systemd-networkd`, and compare the generated storage plan with the virtual devices (`/dev/vda` vs `/dev/sda`) to confirm naming matches expectations.
5. **Rebuild the boot image with the network fixes and rerun the VM regression.**
   - 2025-10-08T13-51-16Z run (`pytest tests/test_boot_image_vm.py`) still fails: `test_boot_image_provisions_clean_disk` flagged `disko`, `lsblk`, and `wipefs` as missing and `test_boot_image_configures_network` timed out without an IPv4 lease. The captured journal shows `pre_nixos.network.identify_lan` raising `OSError: [Errno 22] Invalid argument` when reading the NIC carrier file (see `docs/test-reports/2025-10-08T13-51-16Z-boot-image-vm-test.md`).
   - Prior run (2025-10-08T07-36-29Z) exhibited the same symptoms on the earlier ISO build; see `docs/test-reports/2025-10-08T07-36-29Z-boot-image-vm-test.md` for historical context.
   - Implement a fix for the carrier read failure (e.g. guard `identify_lan` against `OSError` and confirm the interface detection logic tolerates virtio NICs without link state).
   - Stabilise the command-availability probe so the first `command -v` execution does not race the prompt update.
   - Rebuild the ISO, rerun the VM regression, and confirm provisioning, DHCP, and SSH succeed. Promote fresh serial/journal logs to `docs/boot-logs/` together with an updated test report when the run passes.
   - 2025-10-09T01-32-01Z run exercised the updated carrier handling and command probe (`pytest tests/test_boot_image_vm.py`). Command checks now report `OK`, and `identify_lan` no longer crashes, but provisioning still timed out waiting for `pre-nixos` to populate `/run/pre-nixos/storage-status` and no IPv4 lease appeared on `lan`. See `docs/test-reports/2025-10-09T01-32-01Z-boot-image-vm-test.md` and the new serial log at `docs/boot-logs/2025-10-09T01-32-01Z-serial.log`.
6. **Capture follow-up boot timings after configuration adjustments.**
   - The latest run (2025-10-08T00-41-32Z) still failed after 1000.26s because provisioning aborted; rerun once the networking fix is validated to measure meaningful timings.
7. **Ensure the full test suite runs without skips (especially `test_boot_image_vm`).**
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
