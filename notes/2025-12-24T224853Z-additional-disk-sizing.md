# VM disk sizing adjustment — 2025-12-24T22:48:53Z (UTC)

## Context
- Latest VM run for the RAID/LVM residue scenario built an unexpected `large` VG instead of `main`.
- Root cause: pre-nixos grouped the two identically sized extra virtio disks (2 GiB each) into a RAID set and provisioned bulk storage on top (per storage grouping rules).
- The requirements specify that rotating disks of approximately the same size are combined into RAID-5/6 for bulk storage, so matching sizes made this behavior expected rather than a bug.

## Actions
- Adjusted the additional-disk fixture to provision two virtio disks with deliberately different sizes so pre-nixos will not treat them as a single group during planning.
- Updated the VM README to mention the mismatched sizing rationale.

## Next steps
- Re-run the VM residue scenario with the new disk sizing to confirm pre-nixos leaves the extra disks untouched until the test seeds the residue.
- Continue logging timings and artifacts in the run ledger and per-run log directories.
