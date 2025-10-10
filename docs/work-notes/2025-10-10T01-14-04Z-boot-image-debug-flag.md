# 2025-10-10T01-14-04Z Boot Image Debug Flag

## Summary
- Added a `--boot-image-debug` pytest flag so VM integration tests can drop into an interactive `pexpect` session when they fail.
- Logged the start and end of interactive sessions in the harness transcript for future analysis.
- Documented the new workflow in the test plan and task queue.

## Testing
- `pytest tests/test_boot_image_vm.py --collect-only`
- `pytest tests/test_imports.py`
