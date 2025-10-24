# BootImageVM diagnostics hardening (task queue item 1)

- **Objective:** Advance task queue item 1 by strengthening the BootImageVM
  fixture diagnostics so failure reports include serial output and
  systemd/journalctl evidence automatically.
- **Changes:**
  - Extended `_log_step` to stream optional multi-line payloads into the harness
    transcript without losing the timestamped header.
  - Added `_read_serial_tail` and taught `_raise_with_transcript` to capture and
    log the tail of the serial console when raising assertions.
  - Recorded `journalctl -u pre-nixos.service -b` and
    `systemctl status pre-nixos` outputs directly to the harness log whenever
    storage provisioning or IPv4 detection loops time out.
- **Result:** Harness failures now bundle the login transcript, a serial tail
  snapshot, and the relevant systemd diagnostics, satisfying the queue
  requirement to preserve root-escalation transcripts and serial output
  automatically.
- **Verification:** `nix develop .#bootImageTest -c pytest
  tests/test_boot_image_vm.py -vv` (16m18s) 【ca4524†L1-L3】
