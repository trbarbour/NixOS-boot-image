# Boot image VM debug reproduction — 2025-10-12T01:03:38Z

## Test execution

- Command: `pytest tests/test_boot_image_vm.py -vv --boot-image-debug`
- Result: both integration tests timed out waiting for `/run/pre-nixos/storage-status`; `pre-nixos.service` remained `activating` after more than 7 minutes and the suite aborted with an additional teardown error because `pexpect.interact` requires a controlling TTY in this environment (`termios.error: (25, 'Inappropriate ioctl for device')`).
- The pytest output is archived in the session transcript (`chunk f6e21a`). Key failure lines:
  - `timed out waiting for pre-nixos storage status` (storage detection stalled)
  - `assert status == "inactive"` (service still `activating`)
  - teardown `termios.error` while attempting to enter the interactive debug shell.

## Captured artefacts

All captured material for this run is stored under this directory:

- `pytest-harness.log` — harness log emitted by the BootImageVM fixture (serial highlights, command invocations, metadata).
- `pytest-serial.log` — raw serial console transcript from the failing pytest session (includes the `systemctl status pre-nixos`, `journalctl -u pre-nixos.service`, and repeated `/run/pre-nixos/storage-status` polls).
- `manual-run-pexpect/serial.log` — serial console from a follow-up BootImageVM session launched via `scripts/manual_vm_debug.py`. This captures `networkctl status lan`, DHCP assignment (`10.0.2.15`), and the same `pre-nixos` service stall. The accompanying `manual-capture.md` records the commands issued (note: ANSI cleanup is imperfect because the shell remained on the auto-logged-in `nixos` account).

These logs provide the requested evidence:

| Evidence | Location |
| --- | --- |
| `systemctl status pre-nixos` | `pytest-serial.log` (lines around the first failure) and `manual-run-pexpect/serial.log` |
| `journalctl -u pre-nixos.service -b` | `pytest-serial.log`, repeated near the timeout |
| `networkctl status lan` | `manual-run-pexpect/serial.log` (toward the end of the file) |
| `ip -o link` / `ip -o -4 addr show dev lan` | `manual-run-pexpect/serial.log` (immediately before the `networkctl` output) |
| `/run/pre-nixos/storage-status` contents | `pytest-serial.log` (multiple `cat` attempts returning nothing) |

## Limitations

- The `--boot-image-debug` interactive hook could not be exercised directly because `pexpect.interact` fails when STDIN is not a TTY (see teardown error). Any future debugging that depends on interactive control will require running the tests from a real TTY.
- Additional attempts to run a lightweight BootImageVM harness (targeted command capture) also terminated early when the controlling shell sent SIGTERM to QEMU. The partial artefacts were discarded to avoid confusion; the full `manual-run-pexpect` logs remain available and contain the required diagnostics.

