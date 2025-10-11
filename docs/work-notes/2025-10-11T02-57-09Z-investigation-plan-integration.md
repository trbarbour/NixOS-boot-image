# Investigation plan integration and kickoff

- **Timestamp:** 2025-10-11T02:57:09Z (UTC)
- **Context:** Align the troubleshooting queue with the new two-ended investigation plan for the stubborn boot-image VM regression and begin executing the first step (pre-building the ISO before test runs).

## Actions

1. Reviewed `docs/task-queue.md` and incorporated the latest investigation strategy so each queue item reflects the alternating "known-bad vs. known-good" workflow.
   - Added a new top-level task to pre-build the boot image prior to running pytest, per the latest guidance.
   - Folded the reproduction, storage, and networking evidence-gathering steps into dedicated tasks that explicitly call for the debug hook and archive requirements.
   - Introduced tasks for verifying the embedded SSH key, establishing a baseline with the upstream installer ISO, and comparing harness/service toggles to close in on the regression from both ends.
2. Confirmed that downstream tasks (harness hardening, rebuild-and-rerun, timing capture, and skip audits) remain relevant and retained their historical notes under the renumbered queue.
3. Prepared to execute Task 1 immediately by scheduling `nix build .#bootImage --impure --print-out-paths` so the subsequent pytest run can start without ambiguity about build progress.

## Next steps

1. Run `nix build .#bootImage --impure --print-out-paths` and capture the derivation path and completion timestamp in the follow-up notes.
2. Proceed to Task 2 (`pytest tests/test_boot_image_vm.py -vv --boot-image-debug`) once the ISO build finishes, gathering the requested in-VM artefacts while the debug hook is active.
3. Continue down the queue with SSH key verification, storage probing, and baseline ISO comparisons, updating work notes after each major milestone.

## Progress log

- 2025-10-11T03:04:56Z - Completed `nix build .#bootImage --impure --print-out-paths`; resulting ISO: `/nix/store/b1vnlg1rkdkyr50qc6fk6kqz9jscxbxx-nixos-24.05.20241230.b134951-x86_64-linux.iso`.
  - Captured the build output (chunk `02985d`) for reference ahead of the upcoming pytest debug run.
