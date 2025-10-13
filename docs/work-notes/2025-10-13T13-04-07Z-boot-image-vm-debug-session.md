# Boot-image VM pytest attempt (2025-10-13T13:04:07Z)

## Context
- Task queue item 1 follow-up: rerun `pytest tests/test_boot_image_vm.py -vv --boot-image-debug` after switching `secure_ssh` to `systemctl reload-or-restart --no-block`.

## Outcome
- Both integration tests failed after ~622s. Provisioning still reports `STATE=applied` but volume group detection and `systemctl is-active pre-nixos` validations see stale output, likely due to command transcript contamination. 【cb6d90†L74-L104】【F:docs/work-notes/2025-10-13T13-04-07Z-boot-image-vm-debug-session/serial.log†L70-L90】
- Teardown attempted to open an interactive console but crashed with `termios.error`, preventing manual inspection. 【cb6d90†L16-L73】
- Harness and serial logs archived under `docs/work-notes/2025-10-13T13-04-07Z-boot-image-vm-debug-session/`.

