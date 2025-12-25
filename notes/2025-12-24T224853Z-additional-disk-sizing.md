# VM disk sizing adjustment — 2025-12-24T22:48:53Z (UTC)

## Context
- Latest VM run for the RAID/LVM residue scenario built an unexpected `large` VG instead of `main`.
- Root cause: pre-nixos grouped the two identically sized extra virtio disks (2 GiB each) into a RAID set and provisioned bulk storage on top (per storage grouping rules).
- The requirements specify that rotating disks of approximately the same size are combined into RAID for bulk storage, with the level depending on disk count (RAID-1 for two, RAID-5 for three to four, RAID-6 for five or more). Matching sizes made this behavior expected rather than a bug.

## Actions
- Adjusted the additional-disk fixture to provision two equal-sized virtio disks (1.5 GiB each) that remain smaller than the 4 GiB boot disk so pre-nixos keeps the boot disk as the primary installation target while leaving the auxiliary pair available for residue.
- Updated the VM README to mention the equal-sized-but-smaller auxiliary sizing rationale.

## Next steps
- Re-run the VM residue scenario with the new disk sizing to confirm pre-nixos leaves the extra disks untouched until the test seeds the residue.
- Continue logging timings and artifacts in the run ledger and per-run log directories.
