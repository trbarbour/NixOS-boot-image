# Pre-NixOS Setup

This project contains tools to prepare bare-metal machines for a NixOS installation. It discovers hardware, plans a storage layout, configures the active network interface for DHCP (renaming it to `lan`), and can apply that plan. The boot image only generates the plan; run `pre-nixos-tui` to partition disks. When multiple disk groups qualify for the same tier, only the largest is mounted as `main` or `large`; smaller groups receive suffixed VG names and are left unmounted for manual use after installation.

Storage execution is delegated to [disko](https://github.com/nix-community/disko). The planner emits a `disko.devices` description alongside the traditional RAID/VG/LV view, and the applier writes `/var/log/pre-nixos/disko-config.nix` before inspecting `disko --help`. Newer disko releases expect the combined `--mode destroy,format,mount` entry point (and support `--yes-wipe-all-disks`), while older packages only recognise `--mode disko`. Detecting the available mode at runtime keeps the same boot image compatible with both generations and still leaves an auditable config behind for reuse.

> **Note:** To enable SSH access on the boot image, supply a public key via the
> `PRE_NIXOS_ROOT_KEY` environment variable before building **and** pass
> `--impure` to `nix build`. Without `--impure` the environment variable is
> ignored and the build prints a warning before falling back to the NixOS
> default of console-only access so automated builds still succeed.

## Usage

Generate a storage plan without applying it:

```bash
python -m pre_nixos.pre_nixos --plan-only
```

The default output shows the summarized arrays/VGs/LVs view. Request the rendered
`disko` configuration explicitly when you need to inspect the Nix expression:

```bash
python -m pre_nixos.pre_nixos --plan-only --output disko
```

The tool executes system commands only when `PRE_NIXOS_EXEC=1` is set. The
bootable image sets this variable automatically; set it manually if you want to
apply changes on a running system.

Structured JSON debug logs are now opt-in. Set
`PRE_NIXOS_LOG_EVENTS=1` in the environment before running the CLI to emit the
previous diagnostic stream to `stderr` during troubleshooting or test runs.

When a root SSH key is embedded via `PRE_NIXOS_ROOT_KEY`, the CLI can generate a
minimal NixOS configuration (firewall enabled with SSH + ping, root key
authorised, flakes enabled, and the `lan` interface managed by
systemd-networkd) and runs `nixos-install --no-root-passwd` after the storage
plan completes. Automatic progression now requires the boot image to have been
built with `PRE_NIXOS_AUTO_INSTALL=1`; otherwise the CLI leaves installation
disabled by default so you can adjust settings first. Toggle auto-install at
runtime with `--auto-install/--no-auto-install`.

For systems that should not use DHCP after installation, supply static network
details with `--install-ip-address`, `--install-netmask`, and
`--install-gateway`. Netmask and gateway default to the DHCP values obtained by
the boot image, so you only need to provide an IP address when the live network
matches the target install-time network. These options persist the chosen
network values for the next installation run and emit the equivalent static
`systemd.network` configuration in the generated NixOS config.

For an interactive review and to apply the plan manually, use the TUI helper,
which displays the current IP address or a diagnostic message when the
embedded SSH key is missing or no address was assigned:

```bash
pre-nixos-tui
```
Within the interface press `S` to save the current plan to a JSON file or `L`
to load an existing plan. The footer now shows an `I` toggle that controls
whether the TUI should launch the same minimal `nixos-install` workflow after
applying the storage plan; the header reflects the most recent auto-install
outcome. Press `C` to set static install-time network details, which default to
the network information assigned via DHCP so you can enter only the host
portion of the desired static address.

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
so that the key is embedded in the image. If `--impure` is omitted, Nix
evaluates the flake in a pure environment and silently drops
`PRE_NIXOS_ROOT_KEY`, resulting in a build that now emits a warning and ships
without the SSH key.

During the first boot the `pre-nixos` service copies the embedded public key to
`/root/.ssh/authorized_keys` and rewrites `/etc/ssh/sshd_config` to disable
password authentication. This hardening happens even if no network interface is
connected yet, so you can plug in the LAN cable afterwards and connect with the
prepared private key.

If the key is present, the new auto-install step drops a configuration that
keeps the firewall locked down to SSH and ICMP and ensures the root account is
reachable only via the authorised key. The generated `configuration.nix` also
enables flakes so remote tooling such as deploy-rs or NixOps can immediately
rebuild the machine.

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

> **Tip:** To ensure the boot image targets the newest stable NixOS release,
> run `scripts/update_nixos_stable.py` before building. The helper retargets
> `flake.nix` and refreshes the `nixpkgs` lock entry to the latest
> `nixos-YY.MM` channel available on GitHub.

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
