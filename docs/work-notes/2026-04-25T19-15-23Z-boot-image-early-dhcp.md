# Boot image early DHCP startup (task queue item 3)

- **Timestamp (UTC):** 2026-04-25T19:15:23Z
- **Objective:** Reduce the delay between login prompt availability and usable LAN networking on boot-image systems.

## Tests, actions, observations, hypotheses, conclusions

1. **Action:** Reviewed the boot-image module network defaults in `modules/pre-nixos.nix`.
   - **Observation:** `systemd-networkd` is enabled and `networking.useDHCP` is forced off, while LAN DHCP setup is otherwise driven by the `pre-nixos` automation flow.
   - **Hypothesis:** Providing an early, generic networkd DHCP profile for Ethernet links allows DHCP discovery to start immediately during boot, instead of waiting for later provisioning steps.

2. **Action:** Added `systemd.network.networks."10-early-dhcp"` with `matchConfig.Type = "ether"` and `networkConfig.DHCP = "yes"`.
   - **Observation:** The module now expresses an explicit early DHCP policy for wired NICs while keeping networkd as the only network manager.
   - **Conclusion:** This should reduce perceived boot-time LAN delay by moving initial DHCP negotiation earlier in the boot sequence.

3. **Action:** Extended `tests/test_pre_nixos_module.py` with assertions for the new early-DHCP stanza.
   - **Observation:** Module wiring coverage now guards the regression surface for this behaviour.
   - **Conclusion:** Future changes that remove/alter the early DHCP policy will be caught by unit tests.

4. **Action:** Bumped patch version to `0.8.6` in `pre_nixos/VERSION`.
   - **Conclusion:** Versioning reflects a bug-fix level change.

## Follow-up

- Run the full boot-image VM regression (`pytest tests/test_boot_image_vm.py -vv`) after the next ISO build to capture updated boot/network timing data under task queue item 3.
