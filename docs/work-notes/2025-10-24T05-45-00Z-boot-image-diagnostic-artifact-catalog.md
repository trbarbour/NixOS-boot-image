# BootImageVM diagnostic artifact catalogue (task queue item 1)

- **Objective:** Extend the diagnostics hardening so every artifact emitted by
  the BootImageVM harness is traceable through `metadata.json`, and capture
  additional context for storage, network, and unit timeout scenarios.
- **Changes:**
  - Taught `write_boot_image_metadata` to declare an empty `artifacts` array and
    added `record_boot_image_diagnostic` so each diagnostic export is catalogued
    inside `metadata.json`. 【F:tests/test_boot_image_vm.py†L249-L307】
  - `_write_diagnostic_artifact` now records friendly labels for exported logs
    and tolerates metadata write failures gracefully, ensuring downstream tools
    can enumerate the collected evidence. 【F:tests/test_boot_image_vm.py†L359-L381】
  - Storage, IPv4, and unit inactivity timeout handlers persist `lsblk`,
    `networkctl status`, and `systemctl list-jobs` outputs alongside the existing
    journal/systemctl captures, with every artifact mirrored in metadata.
    【F:tests/test_boot_image_vm.py†L739-L847】
  - Added targeted unit tests that validate the metadata helper exports a
    diagnostics directory and registers artifacts without duplication.
    【F:tests/test_boot_image_metadata.py†L1-L76】
- **Result:** When the harness raises an assertion, the metadata file now lists
  all diagnostics produced during the session, and the additional system probes
  give immediate clues about storage and networking state.
- **Verification:** `nix develop .#bootImageTest -c pytest tests/test_boot_image_vm.py tests/test_boot_image_metadata.py -vv`
  (pending).
