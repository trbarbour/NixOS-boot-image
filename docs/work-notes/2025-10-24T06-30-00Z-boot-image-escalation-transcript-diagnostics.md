# BootImageVM escalation transcript diagnostics (task queue item 1)

- **Objective:** Extend the BootImageVM login helper so failed privilege
  escalations automatically capture targeted transcript artifacts alongside the
  existing serial tail logging.
- **Changes:**
  - Recorded escalation transcript slices whenever `sudo -i` or `su -` fails and
    added the resulting artifacts to `metadata.json`, ensuring they appear in
    assertion diagnostics. 【F:tests/test_boot_image_vm.py†L360-L481】
  - Cleared stale escalation diagnostics after a successful root shell is
    established so unrelated failures do not reference obsolete transcripts.
    【F:tests/test_boot_image_vm.py†L639-L706】
  - Added a unit test that exercises the new capture path without launching the
    VM, verifying both the metadata entry and the assertion message payload.
    【F:tests/test_boot_image_vm.py†L1122-L1204】
- **Result:** BootImageVM now leaves behind explicit `sudo`/`su` transcript
  artifacts whenever privilege escalation fails, and those artifacts surface in
  harness assertion messages for faster debugging.
- **Verification:** `pytest tests/test_boot_image_vm.py -k escalation_failure_artifact_and_raise -vv`
  【2a5020†L1-L10】
