# Plan: AArch64 boot image for Raspberry Pi CM4 (microSD)

- Written 2026-10-18 14:21Z, on a branch at version 0.10.0.
- Status: **proposal for review.** Nothing below has been implemented.
- Method: top-down. The plan starts from requirements, then design decisions argued per choice, then unknowns, each with an experiment. Every work item cites the requirement it serves (`R-…`).

## 1. Goal

Build an AArch64 boot image that can be written to a microSD card, boots a Raspberry Pi CM4 (and similar boards such as the Pi 4), and runs pre-nixos as the x86 ISO does. **Base: the stock NixOS AArch64 SD image** (`sd-image-aarch64.nix`). The user has checked that it boots a CM4, serial console included.

### Decisions already made by the user (2026-10-18)

| # | Decision |
|---|---|
| U1 | The requirements were written for x86 only. They are to be **extended** to cover AArch64. |
| U2 | The boot image is the stock AArch64 image, which already has the right bootloader. |
| U3 | The planner's "at least one SSD" assumption is to be **removed**. |
| U4 | The stock image's serial setup is correct and should be used as it is. The NIC rename is expected to work unchanged. |
| U5 | The early boot chain (firmware → U-Boot → extlinux) need not be tested, **provided our changes do not alter it**. |

## 2. Requirements changes (proposed text; traceability anchors)

These amend `automated-pre-nixos-reqs.md`. That document has no IDs, so new IDs are introduced here and existing sections are cited by number.

| ID | Proposed requirement | Amends | Why |
|---|---|---|---|
| **R-P1** | The project supports two target platforms. **x86_64 UEFI** machines boot an ISO. **AArch64 Raspberry Pi 4-family** machines (CM4, Pi 4) boot a microSD image. | §1, §4 | U1 |
| **R-P2** | The AArch64 image is the stock NixOS AArch64 SD image plus pre-nixos. pre-nixos **must not change the stock image's boot chain or kernel console parameters.** | new | U2, U4, U5 |
| **R-B1** | Boot requirements are per platform. On x86_64, UEFI with an EFI System Partition is mandatory (unchanged). On AArch64 Pi, the installed system boots through the Raspberry Pi firmware, U-Boot and extlinux, as the stock image does. | §2.3 "UEFI booting is mandatory", §4 "UEFI boot is required" | U1, U2 |
| **R-S1** | pre-nixos **must never plan, wipe or provision the medium it booted from**, nor any disk that holds a filesystem the running system has mounted. | §2.3 (safety), new | §3.1 below |
| **R-S2** | Disk classification covers eMMC and SD (`mmcblk*`) and NVMe as solid-state devices. Machines **may have no SSD**; a single solid-state device is a valid system disk. | §2.1, §5 "at least one SSD" | U3 |
| **R-C1** | The installed system keeps every serial console the boot image was booted with (`ttyS*`, `ttyAMA*`, …) and keeps the same primary console. | §3 serial console | §3.6 below |
| **R-T1** | Every platform's image builds from this repository on an x86_64 build host, including a Claude Code cloud session. | new | §3.3 below |

**Anomaly for the user, independent of AArch64.**
- §2.3 says *"Disk layout changes must **never** be applied automatically at boot."*
- Every VM run on 2026-10-18 shows the boot-time run tearing down and provisioning all visible disks unattended (`notes/2026-10-18T044623Z-vm-run.md`). The queue history (`DETAIL=auto-applied`) suggests this behaviour was added deliberately.
- Either §2.3 or the behaviour needs updating. On a CM4 it also increases the risk addressed by R-S1.

## 3. Design decisions

### 3.1 Protecting the boot medium (R-S1), the top priority

- **Today:**
  - `storage_detection` excludes the disk that holds the boot media using ISO-specific probes (`/iso`, `/nix/.ro-store`, squashfs, iso9660 mounts) plus the `RM` (removable) flag.
  - On the SD image, root is a plain ext4 partition on the card, so none of the ISO probes match. SD and eMMC devices usually report `RM=0`, so the removable rule doesn't match either.
  - **Unless changed, the boot card is a candidate for wiping.**
- **Options:**
  - **(a)** Add an SD-specific probe for the `FIRMWARE`/`NIXOS_SD` labels. This is narrow, breaks if labels change, and only covers this one image.
  - **(b) Recommended:** exclude every disk that is the parent of any mounted filesystem of the running system (`findmnt -rno SOURCE`, then `lsblk -no PKNAME`). This is general: it covers the SD card, the ISO's medium, and anything else mounted. The ISO probes stay as a second check.
- **Tests:**
  - unit tests with a fake `DetectionEnvironment` for the SD layout (root on `mmcblk0p2`) and the ISO layout;
  - a VM test asserting the boot disk never appears in the plan.

### 3.2 Image definition in `flake.nix` (R-P1, R-P2)

- **Options:**
  - **(a)** Copy `preInstallerConfig` for AArch64. Simple, but not DRY.
  - **(b) Recommended:** one function, `mkPreInstaller { system, imageModules }`. x86 passes `iso-image.nix` and `installation-cd-minimal.nix`; AArch64 passes `sd-image-aarch64.nix`.
- **Outputs:**
  - `packages.aarch64-linux.bootImageSd`, which is `config.system.build.sdImage`, a `.img.zst`;
  - `nixosConfigurations.pre-installer-aarch64`.
- **Fact (E1):** our module **evaluates** on top of the stock SD image without errors. The derivation is `…nixos-image-sd-card-25.05…-aarch64-linux.img.zst.drv`.

### 3.3 Building on an x86_64 host (R-T1)

- **Options:**
  - **(a) Cross-compile** (`pkgsCross`). Rejected: cross-built packages miss the binary cache, so the kernel and everything else would be rebuilt.
  - **(b) Native AArch64 builder** (remote builder). Fast, but needs extra infrastructure. Keep it as an optional speed-up.
  - **(c) Recommended: emulation** with binfmt and `qemu-user-static`.
- **Facts:**
  - **E2.** In this cloud VM, `binfmt_misc` can be mounted, and registering `qemu-aarch64-static` with the `F` flag works inside the Nix sandbox. A trivial `aarch64-linux` derivation built in 14 s, and both `uname -m` and Python reported `aarch64`.
  - **E3.** The SD image needs only **44 small derivations built locally**: configuration glue, `pre-nixos`, `disko` and the image assembly. The other **643 paths (1.1 GiB) are substituted**, so there is no kernel build.
- **Work:**
  - Extend `.claude/hooks/session-start.sh` and `scripts/lib/dev_packages.sh` to install `qemu-user-static`, mount `binfmt_misc`, register the interpreter idempotently, and add `extra-platforms = aarch64-linux` to the Nix configuration.
  - Test the hook's no-op behaviour outside the cloud, as is done today.

### 3.4 Platform-conditional module settings (R-P2)

- **Today:**
  - The module unconditionally sets `boot.kernelParams = [ "console=ttyS0,115200n8" "console=tty0" ]`, GRUB serial `extraConfig`, and `memtest86`.
  - On AArch64 this **appends** a second `console=ttyS0,115200n8 console=tty0` to the stock `console=ttyS0,115200n8 console=ttyAMA0,115200n8 console=tty0`, which changes the stock command line (fact from E1's evaluation).
- **Decision:** guard these settings with `lib.mkIf pkgs.stdenv.hostPlatform.isx86`. On AArch64 nothing boot-related is added.
- **Test (a Nix evaluation check):** a flake check asserting that, for AArch64, `boot.kernelParams`, `boot.loader.*` and `sdImage.populateFirmwareCommands` with our module are **equal** to the stock image's. This mechanically enforces R-P2 and U5.

### 3.5 Storage planning on a CM4 (R-S2)

- **Partition naming bug:**
  - `planner._part_name` adds the `p` separator only for `nvme*`. Kernel naming adds it whenever the disk name ends in a digit (`mmcblk0p1`, `nvme0n1p1`, `loop0p1`).
  - Fix with that general rule, plus unit tests.
- **Classification:** `mmcblk*` and NVMe are solid-state (`rotational=0` already holds). Remove the "at least one SSD" assumption; a single eMMC or NVMe device becomes the `main` VG.
- **Partition layout on AArch64:** it differs (§3.7). Replace the planner's `with_efi` flag with a typed per-platform *boot partition kind* (`esp` | `rpi-firmware`), making the platform an explicit input rather than an implicit x86 default.

### 3.6 Installed-system console (R-C1)

- **Today:**
  - `install._installed_console_params` treats only `ttyS*` as serial, and falls back to `console=ttyS0,115200n8`.
  - With the stock AArch64 command line it would emit `console=ttyS0,115200n8 console=tty0` and drop `ttyAMA0`. Whether a CM4's usable UART is `ttyS0` (mini-UART) or `ttyAMA0` (PL011) depends on the board and `config.txt`.
- **Decision:** carry over **all** booted serial consoles (`ttyS*` and `ttyAMA*`) in their original order, keeping the booted primary console. Emit the GRUB serial lines only on x86.
- **Tests:** unit tests using the real stock AArch64 command line (captured in E1) as a fixture.

### 3.7 Installed-system bootloader on AArch64 (R-B1): the main open design question

The boot *image* brings its own bootloader (U2). An *installed* system on the CM4's eMMC or NVMe also needs one. The SD image's firmware partition is filled at **image-build time** (`sdImage.populateFirmwareCommands`), not by anything an installed system does.

- **Options:**
  - **(a) Recommended:**
    - The planned system disk gets a FAT `FIRMWARE` partition, filled with the same commands nixpkgs uses (`populateFirmwareCommands`, reused rather than copied, to stay DRY and match the stock image byte for byte).
    - It also gets `/boot` with `generic-extlinux-compatible`, plus root on LVM.
    - The installed configuration sets `boot.loader.grub.enable = false` and `boot.loader.generic-extlinux-compatible.enable = true`.
  - **(b)** Keep booting from the SD card, with the installed root on eMMC/NVMe. Fragile: the card stays a single point of failure.
  - **(c)** UEFI firmware for the Pi (the RPi4 UEFI project), reusing the x86 ESP path. Rejected: it diverges from the stock image (against U2) and adds a third-party firmware.
- **Questions for the user:**
  1. Install target: CM4 eMMC, NVMe on the carrier board, or both?
  2. CM4 variant: Lite (no eMMC) or eMMC?
  3. EEPROM `BOOT_ORDER`: who sets it, especially for NVMe boot? Proposed: document it, not automate it.

### 3.8 Network (§2.6, unchanged requirement)

The `lan` rename uses a MAC-matched systemd `.link` file, which doesn't depend on the architecture. The CM4's `bcmgenet` NIC usually appears as `end0`. **Verify on hardware (E8)**; the VM test (§4) covers the code path with virtio-net.

## 4. Testing strategy

| Layer | What | Covers |
|---|---|---|
| Unit | platform-parameterised tests for the planner, partition naming, storage detection with the SD layout, and console params with the stock AArch64 command line | R-S1, R-S2, R-C1 |
| Nix eval | the module adds nothing to the AArch64 boot settings; the image closure contains `pre-nixos` | R-P2 |
| Build | `nix build .#packages.aarch64-linux.bootImageSd` under emulation | R-T1 |
| VM (new) | `qemu-system-aarch64 -M virt` direct-kernel boot of the image's system, plus the existing harness. Covers the pre-nixos service, boot-medium exclusion, NIC rename, SSH and the TUI. It skips the Pi firmware chain, which U5 accepts. | R-S1, §2.6–2.8 |
| Hardware | a manual checklist run by the user on a CM4: boot, serial, `lan`, plan excludes the SD card, install to eMMC, reboot from eMMC | R-B1, R-C1, all |

## 5. Unknowns and experiments

| # | Unknown | Experiment | Status |
|---|---|---|---|
| E1 | Does our module evaluate on the stock SD image? | `nix eval …sdImage.drvPath` | **Yes** (2026-10-18 14:18Z, 33 s) |
| E2 | Can this x86_64 host build AArch64? | binfmt + `qemu-aarch64-static` (`F` flag), trivial derivation | **Yes**, 14 s |
| E3 | How much of the image must be built locally? | `nix build --dry-run` | **44 small derivations; 643 paths substituted** |
| E4 | Full SD image build time under emulation | build `bootImageSd` once and keep the store path for reuse | to do; not run alongside the VM suite (CPU contention) |
| E5 | Can `qemu-system-aarch64 -M virt` (TCG) boot the image's system directly, and how fast is boot→login? | spike, then timeout calibration | to do |
| E6 | What does `nixos-generate-config` emit on a non-EFI AArch64 system? (The installer builds on its output.) | run it inside the E5 VM | to do |
| E7 | CM4 facts: block devices and flags (`lsblk -o NAME,RM,ROTA,TYPE,SIZE,MODEL`), `/proc/cmdline`, which UART is live | **user runs these** on a CM4 booted from the stock image | needs the user |
| E8 | NIC name on a CM4 (`ip -br link`) | as E7 | needs the user |
| E9 | Can the installer fill a firmware partition reproducibly from `populateFirmwareCommands`? | build a firmware-partition derivation and compare its files with the stock image's FIRMWARE partition | to do |

## 6. Work breakdown (in order; each item cites its requirements)

1. **Requirements:** apply §2's text to `automated-pre-nixos-reqs.md` once approved, and decide the §2.3 auto-apply anomaly. *(R-P1, R-B1, R-S1, R-S2, R-C1, R-T1)*
2. **Boot-medium protection (§3.1)**, with unit and VM tests. Platform-independent and safety-critical, so it lands first and also benefits x86. *(R-S1)*
3. **Partition naming and storage classification (§3.5)**, with unit tests. *(R-S2)*
4. **Console parameters (§3.6)**, with unit tests. *(R-C1)*
5. **Build host support (§3.3):** hook and `dev_packages`; E4. *(R-T1)*
6. **Flake refactor (§3.2) and platform-conditional module (§3.4)**, with the Nix evaluation check. *(R-P1, R-P2)*
7. **AArch64 VM test (§4):** E5 and E6. *(R-S1, §2.6–2.8)*
8. **Installed-system bootloader (§3.7):** once the user has answered §3.7; E9. *(R-B1)*
9. **Hardware acceptance on a CM4** (user), recorded in `docs/test-reports/`. *(all)*

Version policy: each feature is a minor bump and each fix a patch bump (AGENTS.md).

## 7. Inputs needed from the user

1. Approve or amend the requirements text in §2.
2. Decide the §2.3 auto-apply anomaly: change the requirement or the behaviour.
3. Answer §3.7: install target, CM4 variant, EEPROM boot order.
4. Run E7 and E8 on a CM4 booted from the stock image, and paste the output:
   `lsblk -o NAME,RM,ROTA,TYPE,SIZE,MODEL; cat /proc/cmdline; ip -br link; ls /dev/ttyAMA* /dev/ttyS*`
