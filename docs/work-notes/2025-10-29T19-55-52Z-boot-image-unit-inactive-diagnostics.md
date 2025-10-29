# BootImageVM unit inactivity diagnostics (task queue item 1)

- **Objective:** Extend the BootImageVM timeout diagnostics so unit inactivity
  failures report both the active job queue and any failed units registered in
  systemd.
- **Changes:**
  - Taught `BootImageVM.wait_for_unit_inactive` to run `systemctl list-units
    --failed --no-legend` when the timeout triggers, logging the output and
    storing it as a labelled diagnostic artifact referenced in `metadata.json`.
  - Added a regression test that forces the inactivity timeout path and asserts
    the failure message, metadata catalogue, and on-disk artifacts include the
    failed-unit snapshot.
- **Result:** When a service refuses to become inactive the harness now captures
  the systemd failed-unit list alongside existing job and journal diagnostics,
  accelerating root-cause analysis.
- **Verification:**
  - `pytest tests/test_boot_image_vm.py -k unit_inactive_timeout_records_failed_units -vv`
