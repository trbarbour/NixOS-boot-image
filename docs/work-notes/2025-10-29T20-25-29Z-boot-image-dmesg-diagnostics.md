# BootImageVM kernel ring buffer diagnostics (task queue item 1)

- **Queue context:** Harden BootImageVM diagnostics by extending automated captures during provisioning failures.
- **Change summary:** Added a reusable helper that snapshots the kernel ring buffer via `dmesg` after storage status timeouts, IPv4 acquisition failures, and unit inactivity waits. Each capture is logged, persisted as a labelled artifact, and catalogued in `metadata.json` for postmortem review.
- **Rationale:** Kernel messages often reveal low-level device and driver faults that are not present in service journals. Capturing them alongside existing systemd diagnostics closes a gap observed in recent regression triage sessions.
- **Follow-up:** None required; the helper can be reused for future failure modes as needed.
