# BootImageVM systemctl list-jobs diagnostics (task queue item 1)

- **Objective:** Extend timeout diagnostics so the harness records the active
  systemd job queue whenever provisioning or IPv4 detection stalls.
- **Changes:**
  - Added `systemctl list-jobs --no-legend` captures to the storage and IPv4
    timeout handlers so the harness log, metadata catalogue, and diagnostic
    artifacts preserve the outstanding systemd work alongside existing journal
    and unit status dumps.
  - Introduced focused regression tests that simulate the timeout paths and
    assert the new artifacts appear in assertion messages and `metadata.json`.
- **Result:** Storage and IPv4 waits now surface the systemd job backlog, making
  it easier to understand what work is blocking `pre-nixos` during automated
  runs.
- **Verification:** `pytest tests/test_boot_image_vm.py -k "storage_timeout_records_systemd_jobs or ipv4_timeout_records_systemd_jobs" -vv`
