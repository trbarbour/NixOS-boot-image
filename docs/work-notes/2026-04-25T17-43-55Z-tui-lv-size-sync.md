# TUI LV size sync investigation

- **Timestamp (UTC):** 2026-04-25T17:43:55Z
- **Objective:** Reproduce and fix a TUI bug where editing an LV size changed the displayed plan but `apply` still provisioned the old size.

## Reproduction

1. Confirmed `_edit_plan` mutated `plan["lvs"]` but did not rebuild `plan["disko"]`.
2. Confirmed `apply.apply_plan` provisions from `plan["disko"]`, so stale derived data can persist old LV sizes.

## Root cause

`plan["disko"]` is derived data generated during planning, but TUI edits only mutated the source fields (`arrays`/`lvs`) and left derived data stale.

## Fix

- Added `planner.refresh_disko_devices(plan)` to regenerate `plan["disko"]` from the edited plan.
- Updated `_edit_plan` to call the refresh helper whenever arrays/LVs are modified.
- Added regression coverage in `tests/test_tui.py` to ensure an LV rename/resize also updates the disko LV entry used during apply.
- Bumped patch version to `0.8.5`.
