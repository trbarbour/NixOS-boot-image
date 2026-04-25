# Boot image network-init delay root-cause and fix (task queue item 3)

- **Timestamp (UTC):** 2026-04-25T19:35:35Z
- **Objective:** Address feedback that early global DHCP may conflict with NIC rename/static configs and determine the actual cause of delayed network availability.

## Root-cause analysis

1. **Observation from existing captured logs:** `wait_for_lan` typically detects an interface quickly, so carrier discovery is not the long pole in normal runs.
2. **Observation from existing captured logs:** the `systemctl restart systemd-networkd` step can consume several seconds and is a blocking restart in the critical path after link rename.
3. **Conclusion:** the avoidable delay is primarily in the blocking daemon restart path, not in a need for global early DHCP defaults.

## Changes made

1. Reverted the global early-DHCP module stanza (`10-early-dhcp`) to avoid interfering with rename/static-network workflows.
2. Added `_refresh_networkd_configuration()` in `pre_nixos/network.py`.
   - Fast path: `networkctl reload` + `networkctl reconfigure lan`.
   - Fallback: retain `systemctl restart systemd-networkd` when reconfigure fails.
3. Updated `configure_lan()` to use `_refresh_networkd_configuration("lan")` instead of always restarting `systemd-networkd`.
4. Added permanent unit tests:
   - verifies configure_lan uses `networkctl reload/reconfigure` and does not request a networkd restart in the success path.
   - verifies fallback to `systemctl restart systemd-networkd` when `networkctl reload` fails.
5. Bumped patch version to `0.8.7`.

## Follow-up

- Run full VM timing regression (`pytest tests/test_boot_image_vm.py -vv`) against a rebuilt ISO to measure real boot-time latency changes on representative hardware/network environments.
