# 2025-10-11T19:16:51Z Boot image VM test attempt

## Summary
- Built the boot ISO with `nix build .#bootImage`; the resulting path was `/nix/store/k3zdr950hk6yrv7hn6qqsvncjv3cfqff-nixos-24.05.20241230.b134951-x86_64-linux.iso`.
- Ran `.venv/bin/pytest tests/test_boot_image_vm.py -vv --boot-image-debug` and allowed it to run for just over 30 minutes.
- The VM booted and reached the `PRE-NIXOS>` shell with root privileges, but `pre-nixos` never populated `/run/pre-nixos/storage-status`; the harness looped on that file for the entire session.
- After >30 minutes without progress the run was interrupted with `KeyboardInterrupt`; pytest then hung while shutting down QEMU because the guest refused the non-interactive `poweroff` (serial log shows "Interactive authentication required").

## Evidence collected
- Copied the harness and serial logs to `docs/work-notes/2025-10-11T19-16-51Z-boot-image-vm-test-attempt/` for future analysis.
- The harness log captures the ISO metadata, embedded SSH key fingerprint, the successful login dialogue, and the repeated polling of `/run/pre-nixos/storage-status`.
- The serial log shows the same polling loop and the failed `poweroff` command the harness issued during teardown.

## Follow-up ideas
- Investigate why `pre-nixos` still fails to emit `storage-status`; compare with prior failures noted in `docs/task-queue.md` item 9.
- Ensure the teardown path escalates to root (or uses `systemctl poweroff --no-wall`) so that the harness can shut the guest down even when the provisioning loop stalls.
- Once storage provisioning is unblocked, re-run the pytest target to gather the requested journal and networking diagnostics from within the VM.
