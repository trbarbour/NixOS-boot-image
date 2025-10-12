# 2025-10-12 boot-image VM run after removing sshd dependency cycle

* Command: `pytest tests/test_boot_image_vm.py -vv --boot-image-debug`
* Result: both VM tests still fail. `pre-nixos.service` now reports `STATE=applied` / `DETAIL=auto-applied` in `/run/pre-nixos/storage-status` and eventually transitions to `inactive`, but the harness still fails assertions:
  * `test_boot_image_provisions_clean_disk` cannot find the `main` volume group because `vgs` reports permission errors even after provisioning completes.
  * `test_boot_image_configures_network` captures the `ip -o -4` probe output alongside the `systemctl is-active pre-nixos` result, so the assertion for a clean `inactive` status fails.
* Harness and serial logs: see `harness.log` and `serial.log` in this directory.
* ISO built during the run: `/nix/store/wa0h4fac7pnn6g1310kg18ichymn2j6d-nixos-24.05.20241230.b134951-x86_64-linux.iso`.
