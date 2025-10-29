# BootImageVM IPv4 link statistics diagnostics (task queue item 1)

- **Objective:** Enrich the IPv4-timeout diagnostics with low-level link
  statistics so packet counters and carrier state are preserved alongside the
  existing address and routing captures.
- **Changes:**
  - `BootImageVM.wait_for_ipv4` now records `ip -s link show dev <iface>` when
    DHCP waits exhaust their timeout, logging the output, storing it as a
    labelled diagnostic artefact, and cataloguing it in `metadata.json`.
  - Extended the IPv4-timeout regression test to assert the new command runs,
    the harness failure message surfaces the link-statistics artefact, and the
    metadata entry points to an on-disk capture.
- **Result:** IPv4 timeout investigations now have the interface's packet and
  error counters available for triage, complementing the existing systemd,
  kernel address, and routing diagnostics.
- **Verification:**
  - `pytest tests/test_boot_image_vm.py::test_ipv4_timeout_records_systemd_jobs -vv`
