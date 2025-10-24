# BootImageVM metadata logging improvements (task queue item 1)

- **Objective:** Continue hardening the BootImageVM diagnostics so failure
  reports include explicit ISO metadata alongside the root escalation
  transcript and serial tail captured earlier.
- **Changes:**
  - Added a `_format_artifact_metadata` helper that emits ISO, store path,
    deriver, NAR hash, and root key fingerprint details once per session and
    whenever `_raise_with_transcript` reports a failure. 【F:tests/test_boot_image_vm.py†L273-L305】【F:tests/test_boot_image_vm.py†L323-L343】
  - Updated the session bootstrap logging to write the metadata as a
    single structured harness entry so downstream tools no longer have to
    parse inline key/value pairs.
- **Result:** Harness logs now provide a consistent metadata block and the
  resulting AssertionError includes the same details, satisfying the task
  queue requirement to surface ISO provenance in diagnostic output.
- **Verification:** `pytest tests/test_boot_image_vm.py -vv` 【e2c4d8†L1-L3】
