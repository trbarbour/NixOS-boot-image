# VM integration test layout

This directory collects the VM-based integration tests that exercise the boot
image end-to-end. The code is being split out of `tests/test_boot_image_vm.py`
into focused modules so fixtures, helpers, and scenarios can be maintained
separately.

## Modules
- `fixtures.py` – host/tool checks, ISO build helpers, disk/SSH fixtures, timeout defaults
- `fixtures.py` also exposes the `boot_image_vm` session fixture and captures
  per-run timings for boot-image build, boot-to-login, boot-to-SSH, and total
  test wall-clock duration in `metadata.json`
- `metadata.py` – utilities for collecting logs and diagnostics from VM runs
- `controller.py` – `BootImageVM` controller and interaction helpers
- `cleanup_plan.py` – reusable RAID/LVM seeding and teardown checks
- `test_pre_nixos_vm.py` – main pre-nixos integration scenarios
- `test_pre_nixos_cleanup.py` – RAID/LVM residue regression scenario

### Fixture shim
Fixtures live in `tests/vm/fixtures.py` and are loaded via `pytest_plugins`
in `tests/conftest.py` so existing test files (including the legacy
`tests/test_boot_image_vm.py`) can continue using the same names while the
migration is in progress.

## Running the VM tests
- All VM scenarios should be marked with `@pytest.mark.vm` and `@pytest.mark.slow`.
- Do not skip VM tests silently; missing tools or timeouts surface as failures
  so they can be addressed.
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
- The VM fixture records timing data in `metadata.json` for each run:
  - `build_seconds` from the `nix build .#bootImage` invocation
  - `boot_to_login_seconds` when the serial console login prompt becomes
    available
  - `boot_to_ssh_seconds` when IPv4 and SSH are reachable inside the guest
  - `total_seconds` for the entire test, plus UTC `start`/`end` timestamps
- Include the commands and any environment overrides used so runs remain
  reproducible. If a run exceeds roughly one hour, the metadata will note that
  the session ceiling may have been hit.
- On failures, the fixture collects baseline diagnostics (dmesg,
  `pre-nixos.service` journal, `/tmp/pre-nixos*.log`) and records their paths
  in both `metadata.json` and the run ledger so they remain discoverable.
- A JSONL run ledger is written to `notes/vm-run-ledger.jsonl` by default
  with the above timings, pytest arguments, QEMU command/version, SSH host and
  port, and the measured session ceiling flag. Override the location with
  `BOOT_IMAGE_VM_LEDGER_PATH` or disable ledger writes via
  `BOOT_IMAGE_VM_DISABLE_LEDGER=1` when running purely ad-hoc experiments that
  should not touch the working tree.

## RAID/LVM residue recipe
- The regression scenario seeds `/dev/md127` backed by `/dev/vdb` and `/dev/vdc`,
  creates `vg_residue/lv_residue`, and writes a `residue-marker` sentinel.
- After running `pre-nixos`, the test should assert that the mdadm array, volume
  group, logical volume, and sentinel content are fully removed.
- The canonical command sequence lives in `cleanup_plan.py` so ad-hoc VM runs
  can reuse it without diverging from the regression case.

## Status
Core fixtures, timeout defaults, metadata helpers, and the `BootImageVM`
controller now live under `tests/vm/`. Integration scenarios have moved into
`tests/vm/test_pre_nixos_vm.py` and `tests/vm/test_pre_nixos_cleanup.py`.
