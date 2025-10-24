# BootImageVM metadata file export (task queue item 1)

- **Objective:** Extend the diagnostics work to persist BootImageVM harness
  metadata in a machine-readable file so post-run tools can reuse the same
  context without scraping the textual harness log.
- **Changes:**
  - Added `write_boot_image_metadata` and taught the fixture to emit a
    `metadata.json` file alongside the harness/serial logs, referencing the
    boot artifact, QEMU command, disk image, and SSH configuration.
  - Updated the manual VM debugging scripts to call the helper so ad-hoc
    captures copy the same metadata structure into their output directories.
  - Included the metadata path in raised assertions to highlight the JSON
    companion artefact when failures occur.
- **Result:** Both automated and manual harness flows now generate a stable
  `metadata.json` describing the session, simplifying provenance tracking and
  downstream evidence collection.
- **Verification:** `nix develop .#bootImageTest -c pytest
  tests/test_boot_image_vm.py -vv` (15m48s)【883522†L1-L4】
