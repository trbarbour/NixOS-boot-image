# VM Boot Image Test Log

## Context
- Task: exercise `tests/test_boot_image_vm.py` end-to-end, identify and resolve failures.
- Environment: containerized Linux dev shell where Nix is installed by automation but requires shell integration to expose the CLI.

## Test Sessions

### Session 1 - Repository Baseline (pytest)
- **Command:** `pytest`
- **Result:** All repository tests reported as passing without modification.
- **Notes:** Confirms non-VM suite health before focusing on VM scenario.

### Session 2 - Initial VM Test Attempt
- **Command:** `pytest tests/test_boot_image_vm.py -rs`
- **Result:** Skipped because Python dependency `pexpect` was missing.
- **Observation:** Test fixture `_pexpect` explicitly skips when `pexpect` cannot be imported.
- **Action:** Install development requirements via `pip install -r requirements-dev.txt` to provide `pexpect`.

### Session 3 - Post-Dependency Installation
- **Command:** `pytest tests/test_boot_image_vm.py -rs`
- **Result:** Still skipped, now reporting missing executable `nix`.
- **Observation:** Fixture `boot_image_iso` requires the `nix` CLI to build the boot image; the executable was absent from `$PATH` even though `/nix` and the user profile existed.
- **Investigation:** Discovered that the Codex maintenance script already installs Nix and advises sourcing `$HOME/.nix-profile/etc/profile.d/nix.sh`. The script early-outs when `USER` is unset, which occurs in non-login shells launched by the automation. As a result the PATH export never executes.
- **Action:** Patched `scripts/codex-maintenance.sh` so it always exports `USER=${USER:-$(id -un)}` before sourcing `nix.sh` by rewriting `~/.profile`. Running the maintenance script now injects the guard line ahead of the Nix profile sourcing, ensuring subsequent login shells load Nix onto the path.
- **Follow-up:** Opening a new login shell (e.g. `bash --login`) now reports `nix` on the PATH. Manual sessions can recover immediately by running `export USER=$(id -un); . "$HOME/.nix-profile/etc/profile.d/nix.sh"`.

### Session 4 - Python Dependency Check
- **Command:** `./.venv/bin/pip show pexpect`
- **Result:** Reports `pexpect 4.9.0` installed inside the project virtualenv, matching `requirements-dev.txt`.
- **Observation:** Prior skips stemmed from invoking `pytest` without activating the virtualenv. Use `source .venv/bin/activate` (or run tools via `./.venv/bin/...`) before executing the suite to guarantee dependencies resolve.

### Session 5 - Root Escalation Guardrails
- **Command:** `pytest tests/test_boot_image_vm.py -rs`
- **Result:** Still encountering timeouts while negotiating the automatic login prompt despite Nix and `pexpect` availability.
- **Action:** Reworked `BootImageVM._login` to detect the auto-login banner, skip issuing `root` when the `nixos` account is already authenticated, and add an explicit `id -u` probe that escalates to root with `sudo -i` whenever the shell remains a non-root user. The escalation path now verifies success and fails fast if root cannot be acquired.
- **Status:** The QEMU boot/build pipeline is lengthy (~10 minutes per attempt) and interrupts were required while iterating. A full green run is still pending and should be re-attempted once the nix build artefacts are cached for faster feedback.

### Session 6 - Full `time pytest tests/test_boot_image_vm.py -rs`
- **Date:** 2025-10-06
- **Command:** `time pytest tests/test_boot_image_vm.py -rs`
- **Result:** Both integration tests error during fixture setup. `pexpect` times out waiting for any of the login/banner prompts after 600s. The VM serial log captures the ISOLINUX menu, countdown, and kernel/initrd load acknowledgement, but no subsequent login shell output.
- **Durations:**
  - Wall clock for the full pytest invocation: 25m23s.
  - Approximate `nix build .#bootImage` time (from process start 06:25 to serial log birth 06:41): ~16m.
  - QEMU runtime before timeout: ~10m (process elapsed 06:41-06:51).
- **Artifacts:** Saved a cleaned serial log snapshot at `docs/boot-logs/2025-10-06T0641Z-serial-log.txt` for future comparison. The raw log lives under `/tmp/pytest-of-root/pytest-0/boot-image-logs0/serial.log` while the test is running.
- **Observations:** Kernel parameters may be missing a `console=ttyS0,115200` hand-off, so once control transfers from ISOLINUX to the NixOS kernel the serial output ceases. Without a serial console the login matcher cannot succeed. Need to confirm which profile the boot ISO selects and whether we can append serial console flags via `nix build` arguments or `grub.cfg` overlays.
- **Next Steps:**
  - Inspect the ISO's boot loader configuration to confirm kernel append parameters include serial console redirection.
  - Identify a hook (e.g., `extraKernelParams` or `boot.loader.grub.extraEntries`) we can modify in the NixOS configuration to guarantee serial console output.
  - Re-run the test after adjusting the boot parameters; expect QEMU boot logs to include systemd and login messages.

## Conclusions
- Progressed from generic skip to identifying missing shell integration for preinstalled tooling (`nix`).
- Resolved the `nix` visibility issue by patching the maintenance script; future shells expose the CLI automatically, and manual recovery steps are documented.
- Clarified that Python dependencies are present inside `.venv` and must be consumed by activating the virtual environment before running the VM suite.
- Hardened the VM login routine with an `id -u` guard so that future debugging operates from a guaranteed root shell; further end-to-end validation is outstanding because of long-running nix builds.

### Session 7 - Baseline with Serial Capture and Timing Metrics
- **Date:** 2025-10-06
- **Command:** `time ./.venv/bin/pytest tests/test_boot_image_vm.py -rs`
- **Result:** Both tests error during `BootImageVM` login. The shell remains the auto-logged-in `nixos` user; `_login` never matches a root prompt within 600s and aborts.
- **Durations:**
  - Wall clock for full pytest invocation: 10m21s (`real 10m21.327s`).
  - Observed `nix build` phase (PID 5477) ran for ~8m before QEMU launched (`mksquashfs` CPU time peaked around 9m elapsed).
  - QEMU stayed up for ~10m until the login timeout triggered.
- **Artifacts:**
  - Pytest transcript stored at `docs/test-reports/2025-10-06T15-54-30Z-boot-image-vm-test.log`.
  - Serial console log archived as `docs/boot-logs/2025-10-06T15-54-30Z-serial.log` showing automatic login, failed root escalation, and pre-nixos storage warning.
- **Observations:**
  - Serial log includes banner `[nixos@nixos:~]$` after automatic login and prints `__USER__`, confirming we never acquire root.
  - The image emits `pre-nixos: Storage detection encountered an error; provisioning ran in plan-only mode.` indicating provisioning did not run fully.
- **Next Steps:**
  - Inspect sudo availability and prompt handling to ensure `_login` escalates successfully.
  - Review pre-nixos systemd journal to understand the storage error and why provisioning stops early.
  - Audit boot configuration for serial console persistence beyond login to aid future captures.

### Session 8 - Prompt Regex Root-Cause Analysis
- **Date:** 2025-10-07
- **Method:** Offline analysis of archived serial log and pytest failure buffer.
- **Findings:** Serial bytes surrounding the `_login` timeout contain ANSI colour and bracketed-paste escape sequences (`\x1b[1;32m`, `\x1b]0;...`, `\x1b[?2004h`). These wrappers prevent the existing regex `nixos@.*\$ ` from matching, so the fixture never executes `sudo -i`.
- **Artifacts:** Investigation notes recorded at `docs/work-notes/2025-10-07T01-11-00Z-boot-image-vm-root-prompt-analysis.md`.
- **Follow-up:** Implement the prompt-handling fix, then re-run the VM test to validate the hypothesis. If timeouts persist, resume the serial-console and storage-provisioning investigations documented in earlier sessions.
