# Pre-NixOS Setup

This project contains tools to prepare bare-metal machines for a NixOS installation. It discovers hardware, plans a storage layout, configures the active network interface for DHCP (renaming it to `lan`), and can apply that plan. The boot image only generates the plan; run `pre-nixos-tui` to partition disks. When multiple disk groups qualify for the same tier, only the largest is mounted as `main` or `large`; smaller groups receive suffixed VG names and are left unmounted for manual use after installation.

> **Note:** To enable SSH access on the boot image, supply a public key via the
> `PRE_NIXOS_ROOT_KEY` environment variable before building. If no key is
> provided—or the supplied path cannot be read—the image falls back to the
> NixOS default of console-only access so automated builds still succeed.

## Usage

Generate a storage plan without applying it:

```bash
python -m pre_nixos.pre_nixos --plan-only
```

The tool executes system commands only when `PRE_NIXOS_EXEC=1` is set. The
bootable image sets this variable automatically; set it manually if you want to
apply changes on a running system.

For an interactive review and to apply the plan manually, use the TUI helper,
which displays the current IP address or a diagnostic message when the
embedded SSH key is missing or no address was assigned:

```bash
pre-nixos-tui
```
Within the interface press `S` to save the current plan to a JSON file or `L`
to load an existing plan.

## SSH access

The boot image permits root login **only** via the supplied public key.
Generate a key pair and point `PRE_NIXOS_ROOT_KEY` at the public half before
building the image (the private key remains ignored by git):

```bash
ssh-keygen -t ed25519 -N '' -f pre_nixos/root_key
export PRE_NIXOS_ROOT_KEY=$(pwd)/pre_nixos/root_key.pub
nix build --impure
```

After generating the key pair, keep `PRE_NIXOS_ROOT_KEY` set (or provide an
absolute path directly in the environment) before running `nix build --impure`
so that the key is embedded in the image.

Keep `pre_nixos/root_key` secure and uncommitted; `.gitignore` prevents
accidental check-in of both halves. Use the generated
private key to connect once the image boots:

```bash
ssh -i pre_nixos/root_key root@<ip>
```

## Development

The project uses [pytest](https://pytest.org) for tests.

```bash
pytest
```

## Nix flake

Build a bootable ISO that prints the plan at boot. Run `pre-nixos-tui` manually
to apply it:

```bash
nix build
```

Build the CLI as a Nix package:

```bash
nix build .#pre-nixos
```

Enter a development shell with dependencies:

```bash
nix develop
```

## NixOS module

Expose the tool on a system via the flake's NixOS module:

```nix
{ inputs, ... }:
{
  imports = [ inputs.pre-nixos.nixosModules.pre-nixos ];
  services.pre-nixos.enable = true;
}
```

The explicit attribute paths remain available if needed:

```bash
nix build .#bootImage
nix build .#nixosConfigurations.pre-installer.config.system.build.isoImage
```
