# BootImageVM QEMU exit status diagnostics (task queue item 1)

- **Objective:** Extend the BootImageVM diagnostics to capture and persist
  QEMU exit status details whenever the virtual machine process terminates
  unexpectedly.
- **Changes:**
  - Added `_record_vm_exit_status` to `BootImageVM` so `_raise_with_transcript`
    logs and stores a diagnostic artifact describing the QEMU PID, exit code,
    and signal information alongside existing transcripts and serial tails.
  - Updated the EOF regression unit test to ensure `metadata.json` now records
    the new "QEMU exit status" artifact and verifies the persisted exit code.
- **Result:** Harness failures caused by abrupt QEMU shutdowns now surface
  structured exit status evidence in both the assertion message and metadata
  catalogue, reducing turnaround time when triaging VM crashes.
- **Verification:** `pytest tests/test_boot_image_vm.py -k run_command_eof_records_diagnostics -vv`
