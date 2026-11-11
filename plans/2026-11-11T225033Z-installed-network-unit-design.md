# One network unit for the installed system's lan (design)

_2026-11-11T22:50:33Z. Task queue item 52._

**Problem (found 2026-11-11, checking Codex's DNS finding on #351):** the managed block declares `lan` twice.
- `networking.interfaces.lan` (and, for a static address, `networking.defaultGateway`) makes NixOS generate `40-lan.network`.
- `systemd.network.networks."lan"` declares `lan.network`.
- networkd applies only the first unit, by name, whose `[Match]` fits, so `lan.network` is never used.
- The installed system works only because `40-lan.network` carries the same address and gateway. The DNS placed in `lan.network` in #351 was ignored until Codex noticed; it now goes in `networking.nameservers`.

Reproduced by the flake check `installed-network-units`. It evaluates the block as pre-nixos writes it (`tests/fixtures/managed-block`, kept equal by `tests/test_managed_block_golden.py`) and finds `["40-lan.network","lan.network"]`.

## 1. Requirement
- **R-N4:** the installed system configures `lan` with exactly one systemd-networkd `.network` unit. It holds the static address, gateway and DNS, or DHCP. The settings a reader sees in `configuration.nix` are the ones in effect.

## 2. Design debate
### Which declaration stays
- **(A) Chosen: NixOS's options.** Keep `networking.interfaces.lan` (`useDHCP`, `ipv4.addresses`), `networking.defaultGateway` and `networking.nameservers`; drop `systemd.network.networks."lan"`.
  - Idiomatic NixOS, and what NixOS documents for a static address.
  - Other modules see the address and gateway, e.g. `networking.defaultGateway`.
  - Already in effect today (it is the unit that wins), so the running behaviour does not change: the lowest-risk fix.
  - The network unit then matches by name (`Name=lan`), not by MAC address. That is no loss: the link unit `systemd.network.links."10-lan"`, which stays, matches the MAC address and names the NIC `lan`. The MAC match in `lan.network` only repeated it.
- **(B) Keep only a systemd-networkd unit**, e.g. `systemd.network.networks."40-lan"` with the MAC match, `Address`, `Gateway` and `DNS` (per-link DNS).
  - More direct, but it depends on NixOS's unit-name convention to avoid a clash.
  - It hides the settings from NixOS options.
  - It changes what is in effect today, so it needs more testing for no functional gain.
- **(C) Keep both, and name ours to sort first.** It keeps the duplication that caused the slip. Rejected.

### DNS
- Stays in `networking.nameservers` (#351), which reaches `resolved.conf` as global DNS. Per-link DNS (`networking.interfaces.lan` has no DNS option) would need (B).
- With one interface, global and per-link DNS behave the same.

### DHCP
- `networking.interfaces.lan.useDHCP = true` makes NixOS's `40-lan.network` run DHCP. Already in effect today.

## 3. Tests (first)
- `installed-network-units` (flake check): one `.network` unit; for the static variant `Name=lan`, `DHCP=no`, the address, the gateway, and the DNS server in `resolved.conf`; for DHCP, `Name=lan` and `DHCP=`. It fails before the fix (two units).
- `tests/test_install*.py`: the block has no `systemd.network.networks`, and still has the link unit and the NixOS options.
- The VM end-to-end install (the static-network one) is the final check that the installed system comes up with its address, if one exists for the static case; otherwise the flake check is the evidence, since the installed system's units are fixed at evaluation.
