# 2025-12-12T01:43:03Z — Storage cleanup redesign plan and progress

## Context
The pre-NixOS applier must reliably dismantle arbitrary storage stacks (filesystems, LVM, mdraid, partitions, loops) even when they form deep, mixed hierarchies. Previous cleanup skipped metadata wiping when teardown failed and operated per-device, leaving shared arrays active. This note records the corrected design, implementation plan, and progress.

## Design summary
- **Single global graph:** Build one deduplicated storage graph from `lsblk --json --paths --output-all`, augmented with LVM (`pvs/vgs/lvs --reportformat json`) and loop backing files (`losetup --list --json`). Represent every element (including pseudo VG nodes) with parent/child links so shared arrays are only processed once.
- **Leaf-to-root ordering:** Compute node depth within the reachable subgraph for all requested devices, then process from leaves upward to guarantee children are quiesced before their parents.
- **Teardown before wipes:** For each node, unmount/swapoff, deactivate LVs, deactivate VGs, stop md arrays, remove dm/crypt/loop devices—logging but continuing after failures to surface design issues without skipping work.
- **Metadata scrub:** After teardown, wipe descendant metadata (`mdadm --zero-superblock` + `wipefs`) in leaf-to-root order, then zap/refresh/zap-root metadata (plus discard/shred variants) per requested device.
- **Diagnostics:** Log stack snapshots on teardown failure, wipefs errors, and partition refresh failures to support root-cause analysis instead of guessing.

## Implementation plan
1. **Replace storage graph builder** with a global discovery function that merges lsblk/LVM/loop data into `StorageNode` objects, including pseudo VG nodes so VGs can be deactivated explicitly.
2. **Compute leaf-to-root ordering** for all nodes reachable from the requested devices (a forest), ensuring nodes are only processed once even when shared (e.g., md arrays spanning disks).
3. **Rewrite teardown** to walk the ordered nodes once, performing unmount→swapoff→LV/VG deactivate→md stop→dm/crypt/loop detach with tolerant logging instead of aborting.
4. **Rewrite metadata wiping** to scrub all descendants even if teardown partially failed, then apply root-level zap/refresh/discard/shred/wipe for each requested device.
5. **Expand tests** with nested md/LVM stacks and failure-resilience cases to verify global ordering, LVM deactivation, continued wipes after failures, and root-level operations.

## Progress log
- **2025-12-12T01:43Z:** Captured the redesigned graph-based approach, teardown + metadata passes, and diagnostics requirements in this note.
- **2025-12-12T01:46Z:** Replaced the storage cleanup implementation with the global graph workflow, including LVM/loop discovery, resilient teardown, and metadata scrubbing.
- **2025-12-12T01:46Z:** Added targeted tests covering leaf-to-root ordering across shared md/LVM stacks, continued wiping after teardown failures, and baseline root cleanup commands.
