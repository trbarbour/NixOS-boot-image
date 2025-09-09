# Pre-NixOS Setup

This project contains tools to prepare bare-metal machines for a NixOS installation. It discovers hardware, plans a storage layout, configures the active network interface for DHCP (renaming it to `lan`), and can apply that plan. When multiple disk groups qualify for the same tier, only the largest is mounted as `main` or `large`; smaller groups receive suffixed VG names and are left unmounted for manual use after installation.

> **Important:** Before building the boot image, place your SSH public key at `pre_nixos/root_ed25519.pub`. The build fails if the file is missing.

## Usage

Generate a storage plan without applying it:

```bash
python -m pre_nixos.pre_nixos --plan-only
```

The tool executes system commands only when `PRE_NIXOS_EXEC=1` is set. The
bootable image sets this variable automatically; set it manually if you want to
apply changes on a running system.

## SSH access

The boot image permits root login **only** via the public key at
`pre_nixos/root_ed25519.pub`. Generate a key pair and place the public key at
this path before building the image (the private key is ignored by git):

```bash
ssh-keygen -t ed25519 -N '' -f pre_nixos/root_ed25519
```

After generating the key pair, commit `pre_nixos/root_ed25519.pub` before
running `nix build`.

Keep `pre_nixos/root_ed25519` secure and uncommitted; its entry in `.gitignore`
prevents accidental check-in. Use the generated private key to connect once the
image boots:

```bash
ssh -i pre_nixos/root_ed25519 root@<ip>
```

## Development

The project uses [pytest](https://pytest.org) for tests.

```bash
pytest
```

## Nix flake

Build the CLI as a Nix package:

```bash
nix build
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

## ISO image

Build a bootable ISO that runs `pre-nixos` automatically:

```bash
nix build .#nixosConfigurations.pre-installer.config.system.build.isoImage
```
