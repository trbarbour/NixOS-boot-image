# Task queue refresh and SSH key automation plan

## Context
- Date: 2025-10-07T12:57:57Z (UTC)
- Objective: Process the outstanding task queue items, record new requirements about SSH key handling, and outline next actions to unblock the boot-image VM test.

## Actions taken
- Reviewed the existing task queue and appended two new items:
  - Automating ephemeral SSH key generation/injection for the VM integration test.
  - Ensuring the full test suite runs without skips, with emphasis on `test_boot_image_vm`.
- Verified the presence of critical tooling on the host container (`ssh-keygen`, `nix`, and `qemu-system-x86_64`). All are available in PATH, so the test harness can generate keys and launch the VM without additional packages.
- Confirmed current VM integration test structure (`tests/test_boot_image_vm.py`) to identify where SSH key provisioning and future SSH login checks should be added.

## Next steps
- Extend the pytest fixtures to generate a disposable SSH key pair, set `PRE_NIXOS_ROOT_KEY` for the `nix build` invocation, and retain the private key for subsequent SSH login attempts once networking is up.
- Implement an SSH connectivity check in the VM test after `wait_for_ipv4`, using the generated key and `ssh` in batch mode; capture logs for troubleshooting failures.
- Run the full pytest suite (including the VM test) and capture results. If any test skips due to missing dependencies, investigate and resolve.
- Re-measure VM boot timing after networking succeeds to progress the original performance tracking task.
