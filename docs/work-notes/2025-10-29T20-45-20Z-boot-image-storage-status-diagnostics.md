# BootImageVM storage status diagnostics (task queue item 1)

- **Objective:** Extend the storage timeout path so BootImageVM captures the raw `/run/pre-nixos/storage-status` snapshot alongside existing systemd logs.
- **Changes:**
  - After a provisioning timeout the harness now logs, persists, and catalogs the storage status file as a labelled diagnostic artifact, and includes the contents in the assertion message for direct visibility.【F:tests/test_boot_image_vm.py†L1080-L1159】
  - Updated the regression covering storage timeouts to assert the new command execution, metadata entry, and artifact persistence.【F:tests/test_boot_image_vm.py†L2036-L2177】
- **Result:** Storage stalls now retain the final status emitted by `pre-nixos`, closing a long-standing gap in postmortem evidence.
- **Verification:** `pytest tests/test_boot_image_vm.py -k storage_timeout_records_systemd_jobs -vv`【92d15e†L1-L10】
