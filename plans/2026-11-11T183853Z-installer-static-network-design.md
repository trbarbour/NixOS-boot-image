# The installer adopts the static network settings (design)

_2026-11-11T18:38:53Z. Task queue item 41._

**User request (2026-11-08):** with no DHCP server, `[C]` in the TUI set only the installed system's static address, and the user had to configure the installer's `lan` by hand. "When the installer has no address from DHCP, adopt the same static configuration, unless told otherwise."

**User decisions (2026-11-11):** D1, D2(a), D3(a) and D4, as below.

## 1. Requirements
- **R-N1:** when the static settings for the installed system are saved (TUI `[C]`, or `pre-nixos --install-ip-address …`) and the installer's `lan` has no IPv4 address, the installer adopts the same settings.
  - The TUI asks first, with "yes" as the default.
  - The CLI applies them unless given `--installer-network no`. `--installer-network yes` applies them even when DHCP gave an address.
- **R-N2:** the static settings include DNS servers, defaulting to the gateway. They go to the installer and to the installed system: without them, `nixos-install` cannot resolve the binary cache, and the installed system cannot resolve anything.
- **R-N3:** going back to DHCP (a blank address in `[C]`) removes the installer's static settings and reconfigures `lan`.

## 2. Facts
- The installer runs `systemd-networkd` and `systemd-resolved`, and its `lan` is configured by `/etc/systemd/network/20-lan.network` (DHCP), written at boot by `network.configure_lan`. Evaluated 2026-11-11: `networking.useNetworkd = true`, `services.resolved.enable = true`.
- networkd applies the first `.network` file, in lexical order of names across `/etc`, `/run` and `/lib`, whose `[Match]` fits.
- `InstallNetworkConfig` had no DNS field.

## 3. Design
- **D2(a), the mechanism:** `pre_nixos/installer_network.py` writes `/run/systemd/network/10-lan-static.network`, then runs `networkctl reload` and `networkctl reconfigure lan`.
  - The unit has `[Match]` (the NIC's MAC address when known, else `Name=lan`) and `[Network]` with `DHCP=no`, `Address=`, `Gateway=` and one `DNS=` per server.
  - The name sorts before `20-lan.network`, so it wins. It is gone at reboot (`/run`).
- **D3(a), DNS:** `InstallNetworkConfig.dns` is a tuple of IPv4 addresses, defaulting to `(gateway,)`.
  - Saved settings without DNS load with the gateway as DNS.
  - The managed block writes `networkConfig.DNS`, which `systemd-resolved` on the installed system uses (NixOS enables it with networkd).
- **D1, when:** `installer_network.decide(mode, readiness)` (pure) returns apply or skip.
  - `auto` applies only when the installer has no IPv4 address; `yes` always applies; `no` never does.
  - The TUI asks in `auto`'s case, defaulting to yes.
- **D4, undo:** `installer_network.remove()` deletes the unit if present, then reloads and reconfigures `lan`.

## 4. Tests (written first)
- `tests/test_installer_network.py`:
  - the rendered unit, matched by MAC address or by name;
  - apply and remove, with a fake command runner and a temporary unit directory;
  - `decide` for each mode and readiness.
- `tests/test_install*.py`:
  - DNS validation, the default and the payload round trip;
  - an old payload without DNS;
  - the managed block's `networkConfig.DNS`.
- The CLI: `--install-dns` and `--installer-network`.
- A VM test: `pre-nixos --install-ip-address 10.0.2.20 … --install-dns 10.0.2.53 --installer-network yes --plan-only` in the booted image.
  - `lan` must then have 10.0.2.20/24, a default route via 10.0.2.2, and DNS 10.0.2.53 in `resolvectl dns lan` (not QEMU's DHCP DNS server, 10.0.2.3, which must be gone). `--dry-run` only prints what it would do.
  - QEMU's network always offers DHCP, so this proves the mechanism and its precedence over DHCP, not the no-DHCP trigger (covered by `decide`'s unit tests).
