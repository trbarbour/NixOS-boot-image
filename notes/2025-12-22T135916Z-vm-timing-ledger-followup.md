# VM timing and ledger follow-up — 2025-12-22T135916Z (UTC)

## What changed
- Marked the timing discipline and run-ledger milestones in the active plan now that instrumentation is live.
- Expanded `tests/vm/README.md` with explicit timing expectations, ledger fields, and the environment switches for recording or disabling entries.

## Next steps
- Execute the VM suites and capture ledger lines plus copied diagnostics under `notes/` to validate the instrumentation in practice.
- Add artifact-copy hooks so ledger entries can point at preserved `dmesg`/log captures when runs fail.
