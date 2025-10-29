# BootImageVM failed-unit diagnostics (task queue item 1)

- **Objective:** Expand the timeout diagnostics so that systemd failures are
  surfaced alongside job listings when storage provisioning or IPv4 detection
  stalls.
- **Changes:**
  - `BootImageVM.wait_for_storage_status` and `BootImageVM.wait_for_ipv4` now
    run `systemctl list-units --failed --no-legend` after capturing job queues
    and preserve the output as labelled diagnostic artefacts.
  - The harness log and raised assertion now mention the failed-unit snapshot,
    and `metadata.json` catalogues the new artefact for both timeout paths.
  - Extended the storage and IPv4 timeout regression tests to assert the new
    command runs, the failure message surfaces it, and the metadata entries
    point at on-disk captures.
- **Result:** Timeout investigations now reveal whether any services are
  already marked failed, making it easier to pinpoint the unit that blocked
  provisioning without manually re-running the VM.
- **Verification:**
  - `pytest tests/test_boot_image_vm.py::test_storage_timeout_records_systemd_jobs -vv`
  - `pytest tests/test_boot_image_vm.py::test_ipv4_timeout_records_systemd_jobs -vv`
