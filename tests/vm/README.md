# VM integration test layout

This directory collects the VM-based integration tests that exercise the boot
image end-to-end. The code is being split out of `tests/test_boot_image_vm.py`
into focused modules so fixtures, helpers, and scenarios can be maintained
separately.

## Modules (planned)
- `fixtures.py` – host/tool checks, ISO build helpers, disk/SSH fixtures
- `metadata.py` – utilities for collecting logs and diagnostics from VM runs
- `controller.py` – `BootImageVM` controller and interaction helpers
- `cleanup_plan.py` – reusable RAID/LVM seeding and teardown checks
- `test_pre_nixos_vm.py` – main pre-nixos integration scenarios
- `test_pre_nixos_cleanup.py` – RAID/LVM residue regression scenario

## Running the VM tests
- All VM scenarios should be marked with `@pytest.mark.vm` and `@pytest.mark.slow`.
- Do not skip VM tests silently; missing tools or timeouts should surface as
  failures so they can be addressed.
- Useful environment variables:
  - `BOOT_IMAGE_VM_SPAWN_TIMEOUT` (default: 900 seconds) — maximum time to wait
    for QEMU to boot and expose its console.
  - `BOOT_IMAGE_VM_LOGIN_TIMEOUT` (default: 300 seconds) — maximum time to wait
    for SSH connectivity inside the VM once the console is available.
- Prefer fewer VM boots per session. If projected runtime exceeds 45–50 minutes,
  queue additional runs for a fresh session instead of pushing through a single
  long execution.

## Logging and artifacts
- For every VM run, capture console output, `dmesg`, and `/tmp/pre-nixos*.log`
  into a run-specific directory under `notes/` with a UTC timestamp.
- Record three timings per run: boot-image build duration, VM boot-to-SSH time,
  and total test wall-clock time. Include the commands and any environment
  overrides used so runs remain reproducible.

## Status
The modules here are scaffolding for the migration. Functionality remains in
`tests/test_boot_image_vm.py` until helpers are extracted incrementally.
