# Boot image VM test attempt (2025-10-10T00:47:08Z)

## Context
- Objective: validate the login harness fixes and honour the 30-minute no-interruption policy while running `pytest tests/test_boot_image_vm.py -vv`.
- Prerequisites: reused the previously built ISO at `/nix/store/7rbj2zzm56pip0dyh8hhwzj7jf8j8r8w-nixos-24.05.20241230.b134951-x86_64-linux.iso` and the `pexpect` installation performed earlier.

## Execution timeline
- 00:24Z: launched pytest; `nix build` reused cached artefacts so setup proceeded directly to VM boot.
- 00:24Z-00:47Z: tests exercised provisioning/network flows for 22m51s without intervention.
- 00:47Z: both tests failed after exhausting storage-status and IPv4 polling timeouts.

## Observations
- `test_boot_image_provisions_clean_disk` timed out waiting for `/run/pre-nixos/storage-status`; fallback journal/systemctl commands only echoed the polling commands, suggesting the service may not have started correctly.
- `test_boot_image_configures_network` timed out waiting for an IPv4 lease on `lan`; the captured commands again only returned the polling command text, indicating the helper could not retrieve journal output via SSH shell before teardown.
- Harness logs and serial capture paths: `/tmp/pytest-of-root/pytest-1/boot-image-logs0/harness.log` and `/tmp/pytest-of-root/pytest-1/boot-image-logs0/serial.log`.

## Follow-up actions
- Inspect the collected harness and serial logs to determine why `journalctl` invocations returned the literal command instead of service output.
- Confirm that `pre-nixos.service` is started and emitting logs; consider increasing verbosity or fetching logs from the VM via `scp` before shutdown.
- Continue running the full test after addressing service start/network issues, maintaining the 30-minute minimum observation window unless tests fail earlier on their own.
