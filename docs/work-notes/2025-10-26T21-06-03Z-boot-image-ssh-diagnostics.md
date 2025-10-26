# BootImageVM SSH diagnostics hardening (task queue item 1)

- **Objective:** Extend the BootImageVM SSH helper so failed `ssh` invocations
  capture on-box evidence (service status and journal excerpts) alongside the
  existing host-side stdout/stderr artifacts.
- **Changes:**
  - Updated `BootImageVM.run_ssh` to record `systemctl status sshd` and
    `journalctl -u sshd.service -b` outputs whenever the retry loop exhausts
    without a successful login, persisting both artifacts via the diagnostics
    directory and metadata catalogue.
  - Extended the unit test covering SSH failures to assert the new diagnostics
    are written, surfaced in assertion messages, and logged through the metadata
    helper.
- **Result:** SSH connection failures now bundle the service state and journal
  evidence from inside the VM with the existing host command traces, speeding up
  postmortem analysis of networking or daemon issues.
- **Verification:** `pytest tests/test_boot_image_vm.py -k run_ssh_failure_records_diagnostics -vv`
