# VM diagnostics instrumentation follow-up — 2025-12-22T144931Z (UTC)

## Context
- Continuing the modular VM test plan by hardening diagnostics and enforcing the no-skip policy for required tools.

## Actions
- Added teardown diagnostics to the VM controller so dmesg, pre-nixos journal, and `/tmp/pre-nixos*.log` are copied out when a run fails.
- Wired the teardown diagnostics into the run ledger so artifact paths are discoverable alongside timing data.
- Made executable checks fail the suite when dependencies are missing instead of skipping.
- Installed `pexpect` from `requirements-dev.txt` to keep the VM controller unit tests runnable.

## Tests
- `pytest tests/vm/test_controller_unit.py -q` (pass)
