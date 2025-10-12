# Half-Splitting Investigation Plan for Boot Image Regression

## Context
- The boot-image VM regression persists: provisioning and LAN configuration tests time out because `/run/pre-nixos/storage-status` never appears and `lan` never acquires an IPv4 lease.
- Recent debug sessions reach the `PRE-NIXOS>` shell with root access, yet `pre-nixos.service` keeps waiting for storage status and shutdown handling still requests interactive confirmation.
- Journal excerpts show `pre_nixos.network.wait_for_lan` starting repeatedly while `networkctl` reports `Interface "lan" not found` even though `ens4` exists but remains down.

## Half-Splitting Plan
1. **Reproduce with maximum visibility (baseline).**
   - Rebuild the ISO and run `pytest tests/test_boot_image_vm.py -vv --boot-image-debug`, keeping the VM open to gather diagnostics.
   - Capture `systemctl status pre-nixos`, `journalctl -u pre-nixos.service -b`, `networkctl status`, `ip -o link`, `/run/pre-nixos/storage-status`, and the sudo transcript. Store harness, serial, and shell logs under `docs/work-notes/`.

2. **Split host vs. guest by booting an upstream ISO.**
   - Boot a known-good upstream NixOS minimal ISO with the same harness/QEMU settings.
   - If it fails similarly, investigate harness or host networking. If it succeeds, focus on our ISO and services.

3. **Validate ISO contents pre-boot.**
   - Inspect the ISO (`unsquashfs -ll` or mount) for `pre_nixos/root_key.pub`, the `pre-nixos.service` unit, and network/systemd overrides.
   - Missing assets imply a build pipeline issue; present assets shift focus to runtime debugging.

4. **Guest runtime split: network vs. downstream logic.**
   - During debug runs, confirm whether `pre_nixos.network.configure_lan` finishes and `_run` calls succeed.
   - If network bring-up still fails, inspect `systemd-networkd` status, interface state, and service environment (`PRE_NIXOS_EXEC`).
   - If network succeeds yet provisioning stalls, proceed to storage diagnostics.

5. **Guest runtime split: storage detection vs. apply.**
   - Run `pre-nixos-detect-storage` and `pre-nixos --plan-only` interactively to determine where storage handling stalls.
   - Examine generated configs/logs and rerun components with `PRE_NIXOS_EXEC=0` for verbose output without disk mutations.

6. **Harness interaction split.**
   - Monitor login automation and root escalation; adjust the harness if `sudo` never succeeds.
   - Compare shutdown pathways (`systemctl poweroff --no-wall` vs. `poweroff`) to capture full teardown logs.

7. **Documentation and iteration.**
   - After every branch decision, record commands, observations, and conclusions in timestamped notes so future efforts avoid rework.

## Progress So Far
- Drafted this plan after reviewing the persistent regression symptoms and prior investigations.
- Began Step 2 by drafting an upstream ISO probe harness outside the repository; the prototype currently hangs while waiting for the VM login prompt. It needs further work before it can validate the host environment.
- No additional steps have been executed yet. Next actions are to finish the upstream probe, re-run the baseline debug session with comprehensive logging, and continue down the split tree based on observed behaviour.
