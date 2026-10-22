# Pre-NixOS Setup

This project contains tools to prepare bare-metal machines for a NixOS installation. It discovers hardware, plans a storage layout, configures the active network interface for DHCP (renaming it to `lan`), and can apply that plan. The boot image only generates the plan; run `pre-nixos-tui` to partition disks. When multiple disk groups qualify for the same tier, only the largest is mounted as `main` or `large`; smaller groups receive suffixed VG names and are left unmounted for manual use after installation.

Storage execution is delegated to [disko](https://github.com/nix-community/disko). The planner emits a `disko.devices` description alongside the traditional RAID/VG/LV view, and the applier writes `/var/log/pre-nixos/disko-config.nix` before inspecting `disko --help`. Newer disko releases expect the combined `--mode destroy,format,mount` entry point (and support `--yes-wipe-all-disks`), while older packages only recognise `--mode disko`. Detecting the available mode at runtime keeps the same boot image compatible with both generations and still leaves an auditable config behind for reuse.

> **Note:** To enable SSH access or auto-install, give the build a *site*:
> a directory outside git holding your public key and settings, passed with
> `--override-input site path:<dir>`. No `--impure` is needed. See
> [Site settings](#site-settings).

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
previous diagnostic stream to `stderr` during troubleshooting or test runs. Log
entries are also appended to `PRE_NIXOS_LOG_FILE` (defaulting to
`/var/log/pre-nixos/actions.log`, which the boot image service creates) so they
persist outside of the journal.

When a root SSH key is embedded via `PRE_NIXOS_ROOT_KEY`, the CLI can generate a
minimal NixOS configuration (firewall enabled with SSH + ping, root key
authorised, flakes enabled, and the `lan` interface managed by
systemd-networkd) and runs `nixos-install --no-root-passwd` after the storage
plan completes. Automatic progression now requires the boot image to have been
built from a site with `autoInstall = true` ([Site settings](#site-settings)); otherwise the CLI leaves installation
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

## Site settings

A **site** is a directory with a `pre-nixos-site.nix` file. It supplies the settings an image needs, which are not stored in this repository:

```nix
# site/pre-nixos-site.nix
{
  rootKey = ./root_key.pub;   # your root SSH public key, next to this file
  autoInstall = true;         # install NixOS unattended (default: false)
}
```

Unknown settings and wrong types are evaluation errors. Keep the directory outside git: either anywhere on your machine, or as `site/` in your checkout, which `.gitignore` excludes.

**Build the one image you need, purely.** Each command builds only the image it names:

```bash
mkdir -p site && cp ~/.ssh/id_ed25519.pub site/root_key.pub   # plus pre-nixos-site.nix
nix build .#bootImageSd --override-input site path:./site     # only the AArch64 SD image (CM4)
nix build .#bootImage   --override-input site path:./site     # only the x86_64 ISO
```

The image is named after the pre-nixos version and git commit that built it, followed by nixpkgs' label and the system. For example, `result/sd-image/pre-nixos-0.21.0-g4852185-sd-card-26.05.20261015.26f4107-aarch64-linux.img.zst` (or `result/iso/pre-nixos-…-x86_64-linux.iso`). A build from uncommitted changes has `-dirty` after the commit.

`path:./site` is resolved against the current directory, and an absolute path always works. The override does not change `flake.lock`, and the repo's default site (`nix/site-default`) embeds no key.

**Or from a flake of your own**, which also pins this repository by commit. Each `mkBootImage` call is one image, so define only the ones you use:

```nix
# ~/cm4-site/flake.nix, next to pre-nixos-site.nix and root_key.pub
{
  inputs.pre-nixos.url = "github:trbarbour/NixOS-boot-image";
  outputs = { pre-nixos, ... }: {
    # The attribute set is the machine you build on (here x86_64); the image
    # itself is AArch64. Build it with: nix build .#cm4
    packages.x86_64-linux.cm4 = pre-nixos.lib.mkBootImage { format = "sd"; site = ./.; };
    # Add an ISO only if you need one:
    # packages.x86_64-linux.iso = pre-nixos.lib.mkBootImage { format = "iso"; site = ./.; };
  };
}
```

**Formats:** `"iso"` (x86_64-linux) and `"sd"` (aarch64-linux). Building the SD image on x86_64 needs AArch64 emulation (`boot.binfmt.emulatedSystems = [ "aarch64-linux" ];` on NixOS, or `scripts/lib/aarch64_emulation.sh`).

**Legacy:** `PRE_NIXOS_ROOT_KEY` and `PRE_NIXOS_AUTO_INSTALL` still work with `--impure`, but only for settings the site leaves unset. If both set the same thing differently, evaluation fails.

## SSH access

The boot image permits root login **only** via the supplied public key, given as the `rootKey` of a site ([Site settings](#site-settings)). Use an existing key pair, or make one for these machines outside the repository:

```bash
ssh-keygen -t ed25519 -f ~/.ssh/pre-nixos
mkdir -p site && cp ~/.ssh/pre-nixos.pub site/root_key.pub
printf '{ rootKey = ./root_key.pub; }\n' > site/pre-nixos-site.nix
nix build .#bootImage --override-input site path:./site
```

Without a key, `pre-nixos` leaves networking and SSH at the image's defaults: the NIC is not renamed to `lan`, and no key login is possible.

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

Keep the private key out of the repository. Connect with it once the image boots:

```bash
ssh -i ~/.ssh/pre-nixos root@<ip>
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

Build a bootable ISO. The storage plan no longer prints to the console at boot
unless `PRE_NIXOS_PLAN_STDOUT=1` is set for debugging. Run `pre-nixos-tui`
manually to apply the plan:

```bash
nix build
```

> **Tip:** To ensure the boot image targets the newest stable NixOS release,
> run `scripts/update_nixos_stable.py` before building. The helper retargets
> `flake.nix` and refreshes the `nixpkgs` lock entry to the latest
> `nixos-YY.MM` channel available on GitHub. To pin to the latest stable
> release tag instead (for a less frequently moving baseline), run
> `scripts/update_nixos_stable.py --latest-release`. It uses git only
> (`git ls-remote` and a git fetch), not the GitHub API or archive tarballs,
> so it also works in Claude Code cloud sessions. To move a single input to a
> given branch or tag, point its `url` in `flake.nix` at that ref and run
> `scripts/nix_git_inputs.py --update nixpkgs --ref nixos-26.05`.

### Claude Code cloud sessions

`.claude/hooks/session-start.sh` (registered in `.claude/settings.json`) runs
at the start of every cloud session and does nothing elsewhere. It installs any
missing APT packages from the shared list in `scripts/lib/dev_packages.sh`. It
creates or refreshes `.venv`, skipping that when `pyproject.toml`,
`requirements-dev.txt` and the Python version are unchanged. It also sets
`PRE_NIXOS_NIX_GIT_INPUTS=1` (see below). Run the tests with
`.venv/bin/pytest`.

The environment's own *Setup script* box is optional. It runs before the
repository is relied upon and its result is cached, so if you use it, put only
repository-independent package installs there, e.g.
`apt-get update && apt-get install -y --no-install-recommends qemu-system-x86 qemu-utils openssh-client`.
The hook fills any gaps.

### Hosts that block GitHub archive downloads

Nix fetches `github:` flake inputs as GitHub archive tarballs. Some hosts
(for example Claude Code cloud sessions) sit behind a proxy that allows
anonymous `git` reads but refuses those tarballs with HTTP 403. On such hosts,
`scripts/nix_git_inputs.py` fetches every locked `github` input over
`git+https` at its locked revision instead. It checks each fetched input's
`narHash` against `flake.lock` and refuses to continue on any mismatch:

```bash
scripts/nix_git_inputs.py build .#bootImage --impure   # runs nix with overrides
scripts/nix_git_inputs.py --print                       # just print the overrides
```

The VM test fixtures and the VM debug scripts apply the same overrides when
`PRE_NIXOS_NIX_GIT_INPUTS=1` is set. Any value other than unset, `0` or `1` is
rejected.

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
