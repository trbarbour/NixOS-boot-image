# BootImageVM QEMU version diagnostics (task queue item 1)

- **Objective:** Extend the BootImageVM diagnostics so metadata and failure
  reports preserve the exact QEMU build used during a session.
- **Changes:**
  - Added a reusable `probe_qemu_version` helper that captures the first line of
    `qemu --version` output and taught the fixture plus debug scripts to record
    it in `metadata.json` and the harness log metadata block.
  - Persisted the QEMU version alongside existing provenance details in
    `write_boot_image_metadata` and surfaced it via `_raise_with_transcript`
    assertions for faster crash triage.
  - Introduced unit coverage to assert both the metadata write path and
    assertion output include the probed QEMU version.
- **Result:** BootImageVM sessions now leave behind explicit QEMU provenance,
  simplifying comparisons across hosts and making abrupt exit diagnostics more
  actionable.
- **Verification:**
  - `pytest tests/test_boot_image_metadata.py -k qemu_version -vv`
  - `pytest tests/test_boot_image_vm.py -k qemu_version -vv`
