# BootImageVM IPv4 link-state diagnostics (task queue item 1)

- **Objective:** Capture the link-layer view (`ip addr`/`ip route`) whenever
  `BootImageVM.wait_for_ipv4` exhausts its timeout so we can compare DHCP
  failures against the kernel's perspective on the interface.
- **Changes:**
  - After recording systemd/networkd status, the harness now snapshots
    `ip addr show dev <iface>` and `ip route show dev <iface>` into labelled
    diagnostic artefacts and mirrors the outputs in the harness log.
  - The metadata catalogue and assertion output list the new artefacts,
    ensuring postmortems see both the systemd view and the kernel interface
    state side-by-side.
  - Extended the IPv4-timeout unit test to assert the new commands run,
    diagnostics are stored on disk, and metadata includes the labelled
    artefacts.
- **Result:** IPv4 timeout triage now includes the kernel's address and routing
  tables, making it easier to spot DHCP races, stale leases, or miswired
  forwarding.
- **Verification:**
  - `pytest tests/test_boot_image_vm.py::test_ipv4_timeout_records_systemd_jobs -vv`
