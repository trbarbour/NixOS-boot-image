# BootImageVM QEMU command provenance (task queue item 1)

- **Objective:** Ensure BootImageVM failures and logs clearly state the disk
  image and exact QEMU command used for the session so provenance is preserved
  even outside the metadata JSON.
- **Changes:**
  - Extended the harness metadata formatter to include the disk image path and
    a shell-quoted QEMU command, normalising inputs during initialisation so
    every assertion replays the same provenance details.【F:tests/test_boot_image_vm.py†L368-L428】
  - Updated the automated fixture and manual debugging scripts to pass the
    computed QEMU command and disk image through to the harness, aligning both
    paths with the enriched provenance logging.【F:tests/test_boot_image_vm.py†L1870-L1914】【F:scripts/manual_vm_debug.py†L213-L225】【F:scripts/collect_sshd_pre_nixos_debug.py†L252-L264】【F:scripts/collect_sshd_dependency_audit.py†L128-L140】
  - Tightened the regression coverage so `_raise_with_transcript` assertions now
    verify the emitted diagnostics mention both the disk image and QEMU command,
    preventing regressions that would drop the provenance lines.【F:tests/test_boot_image_vm.py†L1512-L1538】
- **Result:** Harness logs and failure messages now display the exact VM launch
  command alongside the disk image path, making it trivial to reproduce a
  failing session without scraping the metadata file.
- **Verification:**
  - `pytest tests/test_boot_image_vm.py -k "escalation_failure_artifact_and_raise or raise_with_transcript_includes_qemu_version or run_command_eof_records_diagnostics or run_ssh_failure_records_diagnostics" -vv`
