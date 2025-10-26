# BootImageVM EOF diagnostics hardening (task queue item 1)

- **Objective:** Continue task queue item 1 by ensuring unexpected `pexpect` EOF
  errors expose the same metadata and diagnostic artifacts as other harness
  failures.
- **Changes:**
  - Taught `BootImageVM.run`, `_expect_normalised`, and `_read_uid` to convert
    `pexpect.EOF`/`ExceptionPexpect` signals into `_raise_with_transcript`
    assertions so serial output and login transcripts are persisted alongside
    metadata entries.
  - Added a unit test that simulates an EOF during `run` without requiring the
    real `pexpect` dependency, verifying that login transcript artifacts are
    catalogued in `metadata.json`.
- **Result:** Harness sessions that terminate unexpectedly now leave behind the
  same structured evidence as timeout paths, improving diagnostics for abrupt VM
  exits.
- **Verification:** `pytest tests/test_boot_image_vm.py -k run_command_eof_records_diagnostics -vv`
