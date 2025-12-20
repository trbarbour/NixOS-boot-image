# Pre-NixOS storage failure after PR #258 — plan and design/implementation check

## Context
- User report: `pre-nixos` now fails in a single pass after PR #258 when wiping and reprovisioning mixed SSD/HDD hardware; failure surfaces on the HDD-backed `md1`/`swap` stack before Disko completes.
- Goal: map the observed failure to the current design, identify where the implementation diverges, and sketch a fix that preserves idempotency.

## Where the implementation matches the design
- The design calls for a **global, graph-driven storage cleanup** that tears down descendants first, removes LVM/md metadata, wipes signatures, and finally zaps GPT on the root devices, capturing diagnostics on failures.【F:automated-pre-nixos-design.md†L138-L145】
- `perform_storage_cleanup` mirrors that flow: it builds a graph from `lsblk`/LVM/losetup, walks it leaf-to-root to unmount/swapoff/deactivate VGs/md/dm, removes LV/VG/PV and md metadata, wipes signatures, and zaps GPT on the requested root devices.【F:pre_nixos/storage_cleanup.py†L845-L924】

## Where the implementation diverges from the design
- The pre-Disko scrub inside `apply_plan` only deactivates VGs and zeroes md member metadata for the **planned devices**, skipping PV/LV removal and any descendants not listed in the plan.【F:pre_nixos/apply.py†L123-L166】【F:pre_nixos/apply.py†L258-L311】
- On a Disko failure, the retry path repeats only that narrow md/VG scrub instead of re-running the full graph-based cleanup that the design expects, so pre-existing or partially assembled stacks (e.g., an auto-assembled `md126` holding the old `swap` VG) remain active and block `pvcreate` on the next pass.【F:pre_nixos/apply.py†L151-L166】

## Plan to fix
1. **Add a regression test for stale md/LVM stacks**: use loopback devices to simulate an existing mirrored VG with LVs (e.g., `swap`) and verify that a Disko apply failure followed by a retry triggers complete teardown and succeeds. This guards the reported md126/swap scenario.
2. **Replace the narrow post-failure scrub with full graph cleanup**: when Disko exits non-zero, rebuild the storage graph and invoke `perform_storage_cleanup` (wipe-signatures) on the planned root devices before retrying. Preserve logging/diagnostics so we can see which nodes were torn down.
3. **Harden pre-run scrubbing**: reuse the same graph-based cleanup for the initial pass (instead of the current md/VG-only scrub) or at least extend the existing scrub to remove PV/LV metadata on planned devices so leftover volume groups cannot block `pvcreate`.
4. **Design doc touch-up**: clarify that the post-Disko retry path uses the full graph cleanup (not just md zeroing) to uphold the idempotency guarantee when residual metadata reassembles arrays between attempts.

## Validation approach
- Run the new regression alongside existing apply/cleanup tests to ensure we do not regress the current disko mode detection and plan rendering paths.
- Verify logs show the graph-driven cleanup before and after a failing Disko invocation, and that a second Disko run succeeds without manual intervention.
