# BootImageVM networkd diagnostics (task queue item 1)

- **Objective:** Capture systemd-networkd state whenever IPv4 acquisition
  stalls so network-related regressions can be triaged quickly.
- **Changes:**
  - On IPv4 timeouts the harness now records `systemctl status
    systemd-networkd` plus its journal output, logging the data and storing it
    as diagnostic artifacts surfaced through metadata and assertion payloads.
    【F:tests/test_boot_image_vm.py†L1148-L1187】
  - Extended the IPv4 timeout regression test to assert the new artifacts are
    catalogued, referenced in the failure message, and that the harness collects
    the systemd-networkd journal during diagnostics. 【F:tests/test_boot_image_vm.py†L2044-L2193】
- **Result:** IPv4 provisioning failures surface systemd-networkd status and
  logs alongside existing `networkctl` data, making it clearer whether
  `systemd-networkd` is the root cause.
- **Verification:** `pytest tests/test_boot_image_vm.py -k ipv4_timeout -vv`
