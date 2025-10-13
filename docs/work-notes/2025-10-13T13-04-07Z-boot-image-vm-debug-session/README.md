# 2025-10-13T13:04:07Z boot-image VM debug session

## Summary

`pytest tests/test_boot_image_vm.py -vv --boot-image-debug` still fails after ~10 minutes. Both tests exit with assertion failures and the teardown raises `termios.error` when attempting to enter interactive mode.

## Highlights

- `test_boot_image_provisions_clean_disk` captures `STATE=applied`/`DETAIL=auto-applied` but `vgs` output is polluted, yielding `{'STATE=applied', 'DETAIL=auto-applied'}` instead of the expected `main` volume group. 【F:docs/work-notes/2025-10-13T13-04-07Z-boot-image-vm-debug-session/serial.log†L70-L90】【cb6d90†L74-L89】
- `test_boot_image_configures_network` obtains an IPv4 lease (`10.0.2.15`) yet `systemctl is-active pre-nixos` returns the previous IP probe output rather than `inactive`, causing the assertion failure. 【F:docs/work-notes/2025-10-13T13-04-07Z-boot-image-vm-debug-session/serial.log†L70-L90】【cb6d90†L89-L104】
- Teardown hits `termios.error: (25, 'Inappropriate ioctl for device')` when `BootImageVM.interact()` tries to hand the PTY over for manual debugging. 【cb6d90†L16-L73】
- Harness and serial logs preserved under this directory for detailed step-by-step trace. 【F:docs/work-notes/2025-10-13T13-04-07Z-boot-image-vm-debug-session/harness.log†L1-L80】

