# Boot Image VM Prerequisite Audit

- **Timestamp:** 2025-10-07T02:11:38Z
- **Tester:** gpt-5-codex (interactive shell)
- **Scope:** Task queue item "Audit boot-image VM test prerequisites" following `docs/work-notes/2025-10-07T00-56-30Z-boot-image-vm-condition-plan.md`.
- **Artifacts:**
  - ISO build log: `docs/boot-logs/2025-10-07T01-58-56Z-bootImage-build.log`.
  - Resulting ISO: `/nix/store/vna6k78a0aw7ggdf3f28z2v1k7ljav01-nixos-24.05.20241230.b134951-x86_64-linux.iso` (symlinked at `./result`).

## 1. Host Tooling Readiness

| Condition | Command(s) | Result |
| --- | --- | --- |
| `nix` CLI available on `PATH` | `command -v nix` | ✅ `/root/.nix-profile/bin/nix` |
| Flake evaluation succeeds | `nix flake show` | ✅ Evaluated after fetching `flake-utils`/`nixpkgs`; `checks`, `devShells`, and `packages` enumerated. |
| Profile script present for new shells | `head ~/.nix-profile/etc/profile.d/nix.sh` | ✅ Script guards `HOME`/`USER`, matches expectations for automated shells. |
| QEMU version and virtio devices present | `qemu-system-x86_64 --version`; `qemu-system-x86_64 -device help \| grep -E 'virtio-(rng|net)'` | ✅ Reports QEMU 8.2.2 (Debian), virtio net/rng families available. |
| QEMU invocation smoke test | `timeout 5 qemu-system-x86_64 -S -display none -nodefaults -monitor none -serial none -parallel none` | ✅ Launches and exits cleanly on timeout signal (proves binary runs in container). |
| Python virtualenv exports deps | `./.venv/bin/python -c "import pexpect; import pytest"` | ✅ Both modules import without error. |
| Disk capacity check | `df -h /nix/store /tmp` | ✅ ~40 GiB free (63 GiB volume). |
| Memory cgroup limit | `cat /sys/fs/cgroup/memory.max` | ✅ 17 179 869 184 bytes (~16 GiB) available. |
| Nix download path reachable | `HELLO_PATH=$(nix build nixpkgs#hello --print-out-paths --no-link)`; `nix-store --realise "$HELLO_PATH"` | ✅ Build fetched 45 MiB archive and realised `/nix/store/b1ayn0l...-hello-2.12.2`. |
| Nix cache HTTP reachability | `curl -I https://cache.nixos.org/` | ✅ Returns `HTTP/1.1 200 OK` (HIT). |

### Observations

* `/dev/kvm` **absent** in container (`ls -l /dev/kvm` → ENOENT). `qemu-system-x86_64 -accel help` lists both `tcg` and `kvm`, so tests must assume software emulation with longer runtimes.
* User-mode networking allowed: `qemu-system-x86_64 -netdev user,id=test -device virtio-net-pci,netdev=test -S -display none -nodefaults -monitor none -serial none -parallel none` started successfully (terminated via `Ctrl+C`).

## 2. ISO Build Integrity

| Step | Command | Result |
| --- | --- | --- |
| Build boot image | `nix build .#bootImage --log-format raw --print-build-logs \| tee $BUILD_LOG` | ✅ Completed after materialising 239 derivations; log stored at `docs/boot-logs/2025-10-07T01-58-56Z-bootImage-build.log`. Result symlinked at `./result`. |
| Kernel serial console params | `nix eval .#nixosConfigurations.pre-installer.config.boot.kernelParams` | ✅ Includes `console=ttyS0,115200n8` and `console=tty0`. |
| System packages required by tests | `nix eval .#nixosConfigurations.pre-installer.config.environment.systemPackages --json` (+ `jq` filters) | ✅ Contains `disko`, `lvm2`, `mdadm`, `iproute2`, `util-linux`, `sudo`, etc. |
| Pre-NixOS systemd unit semantics | Inspected `modules/pre-nixos.nix` and `modules/pre-nixos/service-script.nix` | ✅ Unit is `Type=oneshot`, invoked with `PRE_NIXOS_EXEC=1`, writes `/run/pre-nixos/storage-status`, and surfaces plan-only vs applied states.

### Gaps & Risks

* `configure_lan` in `pre_nixos/network.py` aborts early when no root SSH key is embedded. With no `pre_nixos/root_key.pub` present and no `PRE_NIXOS_ROOT_KEY` override, the boot image **will not rename** the active NIC to `lan`, nor enable DHCP/SSH, although the service still attempts to secure SSH. This matches previous serial logs showing missing LAN configuration.
* Storage detection still defaults to plan-only on errors; journal capture is required in follow-up tasks (see queue item 3).

## 3. Virtual Machine Runtime Expectations

* **Serial console**: With the new ISO build, kernel parameters include the `ttyS0` console, satisfying the prerequisite for persistent serial output. Manual runtime validation is still pending under later queue items.
* **Automatic login & sudo**: `modules/pre-nixos.nix` ensures `environment.systemPackages` includes `sudo` and the `pre-nixos` CLI; however, regression testing will need to confirm prompt parsing once ANSI handling is hardened (see queue item 2).
* **Networking**: Because LAN provisioning is gated on the presence of a public key, rerunning the VM test without embedding a key will continue to leave networking unmanaged. A future test run must either supply `PRE_NIXOS_ROOT_KEY` or adjust the module to configure DHCP unconditionally.

## 4. Summary of Findings

1. Host tooling prerequisites **pass**, though lack of `/dev/kvm` enforces TCG-only QEMU; expect longer VM runtime.
2. ISO build completes with current flake inputs; log captured for reproducibility.
3. Serial console parameters are present, removing the prior bootloader-only console issue.
4. Networking automation depends on embedding a root SSH key; without it, tests cannot observe `lan` DHCP behaviour. This blocks end-to-end verification until addressed.

## 5. Recommended Follow-ups

* Embed a temporary root SSH key for automated tests (via `PRE_NIXOS_ROOT_KEY`) or refactor `configure_lan` to allow DHCP without SSH hardening; track under the task queue if not already covered.
* Proceed to queue item 2 (ANSI prompt hardening) now that prerequisites are documented.
* When addressing storage detection (queue item 3), capture `journalctl -u pre-nixos` during VM runs to illuminate plan-only fallbacks noted in prior logs.
