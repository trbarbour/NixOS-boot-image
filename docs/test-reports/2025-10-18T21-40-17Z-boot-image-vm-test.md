# 2025-10-18T21:40:17Z Boot Image VM Regression

## Summary
- Rebuilt the boot image with an embedded temporary SSH key via `nix build .#bootImage --impure --no-link --print-out-paths`.
- Booted the resulting ISO inside QEMU through the BootImageVM harness and exercised `test_boot_image_configures_network`.
- Verified that the VM acquires an IPv4 lease on `lan`, the `pre-nixos` service reaches an `inactive` state, and SSH logins succeed as root using the generated key.

## Environment
- Repository revision: b97b3ac513ec34fae5abb8a49df852c8268983b0
- Command: `pytest tests/test_boot_image_vm.py::test_boot_image_configures_network -vv`
- Duration: 471.75s
- ISO store path: `/nix/store/ddwq1i37z5n89h73v1d2jrddppsfmicn-nixos-24.05.20241230.b134951-x86_64-linux.iso`
- Embedded root key fingerprint: `256 SHA256:MZD4jDAVQIrM3jd2nH3FDWqZIeDreYsFv5gCZ2WZ0qs boot-image-vm-test (ED25519)`

## Observations
- `lan` obtained `10.0.2.15/24` from QEMU's user-mode networking.
- `pre-nixos.service` transitioned to `inactive` after applying provisioning steps.
- SSH identity check returned `root` when connecting with the generated private key.

## Artifacts
- Harness log: `docs/work-notes/2025-10-18T21-40-17Z-boot-image-vm-regression/harness.log`
- Serial log: `docs/work-notes/2025-10-18T21-40-17Z-boot-image-vm-regression/serial.log`
