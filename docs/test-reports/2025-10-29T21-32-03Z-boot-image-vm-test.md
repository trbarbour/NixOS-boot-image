# 2025-10-29T21:32:03Z Boot Image VM Regression

## Summary
- Rebuilt the boot image with current diagnostics and exercised the complete VM regression suite.
- Verified the boot ISO remains provisionable end-to-end after the latest harness hardening.

## Environment
- Command: `nix develop .#bootImageTest -c pytest tests/test_boot_image_vm.py -vv`
- Duration: 524.10s
- ISO store path: `/nix/store/z2xmivlsz663qx6k1b01pxyx9ygrbdja-nixos-minimal-25.05.20251022.c8aa8cc-x86_64-linux.iso/iso/nixos-minimal-25.05.20251022.c8aa8cc-x86_64-linux.iso`

## Result
- All nine test cases passed, including both VM provisioning scenarios and the SSH/diagnostic regressions.【ffd346†L1-L13】【c4589c†L1-L2】
