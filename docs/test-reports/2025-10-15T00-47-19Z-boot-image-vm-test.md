# Boot image VM regression - 2025-10-15T00:47:19Z

## Environment
- Command: `TMPDIR=/tmp nix develop .#bootImageTest -c pytest tests/test_boot_image_vm.py -vv`
- Host nix version: 2.32.1 (`nix --version`)
- Devshell nix version: `/nix/store/l9xhiy5wqs3cflxsfhxk0isbjv96rhd1-nix-2.18.8/bin/nix`
- PRE_NIXOS_ROOT_KEY generated under `/tmp/nix-shell.qywJXF/pytest-of-root/pytest-0/`

## Result
| Test | Status | Notes |
| --- | --- | --- |
| `test_boot_image_provisions_clean_disk` | ❌ Error | Fixture fails: `nix build .#bootImage --impure --no-link --print-out-paths` exits 1 before VM boots. |
| `test_boot_image_configures_network` | ❌ Error | Same fixture failure prevents execution. |

Pytest aborts after ~31 seconds because `/nix/store/sxdfwpm10pwks6cppwbk2w9vqyxk8dpg-nixos-24.05.20241230.b134951-x86_64-linux.iso.drv` fails to build. No harness or serial logs were produced.

## Follow-up
- Capture the failing derivation log during the pytest run (e.g., by teeing `stderr` to a file) to understand why the impure build dies inside the fixture.
- Compare with manual invocations of the same build (which currently succeed) to isolate the environment difference.
