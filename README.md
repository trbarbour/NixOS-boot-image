# Pre-NixOS Setup

This project contains tools to prepare bare-metal machines for a NixOS installation. It discovers hardware, plans a storage layout, configures the active network interface for DHCP (renaming it to `lan`), and can apply that plan. The boot image only generates the plan; run `pre-nixos-tui` to partition disks. When multiple disk groups qualify for the same tier, only the largest is mounted as `main` or `large`; smaller groups receive suffixed VG names and are left unmounted for manual use after installation.

Storage execution is delegated to [disko](https://github.com/nix-community/disko). The planner emits a `disko.devices` description alongside the traditional RAID/VG/LV view, and the applier writes `/var/log/pre-nixos/disko-config.nix` before inspecting `disko --help`. Newer disko releases expect the combined `--mode destroy,format,mount` entry point (and support `--yes-wipe-all-disks`), while older packages only recognise `--mode disko`. Detecting the available mode at runtime keeps the same boot image compatible with both generations and still leaves an auditable config behind for reuse.

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

During the first boot the `pre-nixos` service copies the embedded public key to
`/root/.ssh/authorized_keys` and rewrites `/etc/ssh/sshd_config` to disable
password authentication. This hardening happens even if no network interface is
connected yet, so you can plug in the LAN cable afterwards and connect with the
prepared private key.

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

### Virtual machine integration tests

The test suite includes end-to-end checks that boot the generated ISO inside a
QEMU virtual machine, verify that `pre-nixos` provisions a blank disk, and that
the network interface is renamed to `lan` and receives a DHCP lease. These
tests require the `nix` CLI to build the boot image, `qemu-system-x86_64` to run
the VM, and the Python [`pexpect`](https://pexpect.readthedocs.io/) module for
console automation.

Before running the VM tests ensure your host `nix.conf` enables the flake
command set:

```bash
sudo tee -a /etc/nix/nix.conf <<'EOF'
experimental-features = nix-command flakes
EOF
```

Run only the integration tests after installing their dependencies:

```bash
pip install pexpect
pytest tests/test_boot_image_vm.py
```

The tests automatically skip when the required tooling is missing. Treat these
skips as warnings that the VM scenario was not validated; rerun the suite once
the prerequisites are available.

> **Network requirements:** the build must be able to reach
> `https://cache.nixos.org` for prebuilt binaries and the GNU mirrors for
> source fallbacks. If a corporate proxy blocks these domains Nix will fail
> while trying to download `bash-5.2.tar.gz`, preventing the VM tests from
> booting the image.

## Nix flake

Build a bootable ISO that prints the plan at boot. Run `pre-nixos-tui` manually
to apply it:

```bash
nix build
```

### Running flake checks locally

The flake defines a regression check that ensures `pre-nixos` continues to
propagate the storage and networking utilities it requires at runtime. When
using the single-user Nix installer, source the profile script and enable the
experimental command set before invoking the check:

```bash
. "$HOME/.nix-profile/etc/profile.d/nix.sh"
export NIX_CONFIG='experimental-features = nix-command flakes'
nix flake check
```

The configuration environment variable is optional when `nix.conf` already
enables flakes and the modern CLI.

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
