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
| **R-B2** | On AArch64 Pi, the board's boot order must make the **installed system boot after installation**, without the installer running again, while still letting the installer boot on a machine with no installed system. pre-nixos must **verify** the effective boot order before it installs, and must refuse to install, or warn, if the installed system would not be booted. | new | user, 2026-10-18; §3.9 below |

**Anomaly for the user, independent of AArch64** (corrected 2026-10-18 after the user's note).
- §2.3 says *"Disk layout changes must **never** be applied automatically at boot."*
- At boot, pre-nixos **provisions only when the existing-storage scan finds nothing**; otherwise it aborts. This is the safeguard in `_handle_existing_storage`.
- So the remaining gap is narrow: auto-apply onto empty disks. §2.3's wording should probably say "never modify disks that contain data".
- An earlier version of this plan said the image "tears down and provisions all visible disks unattended". That was wrong. Those log lines come from `apply_plan`'s pre-disko signature wipe, which prints "Tearing down existing storage" even for empty disks.

## 3. Design decisions

### 3.1 Protecting the boot medium (R-S1), the top priority

> **Also an x86 fault today**, tracked in trbarbour/NixOS-boot-image#306. The user notes the x86 image is usually written to a writable USB stick, and there is a mechanism to protect it: `resolve_boot_disk`. That mechanism covers only the **cleanup scan**. The **storage plan** (`enumerate_disks` → `plan_storage` → disko) excludes only `RM=1` devices, so a boot stick reporting `RM=0` is planned. Reproduced on 2026-10-18: `disko devices=['nvme0n1', 'sda']`. The fix below must therefore apply to **both** paths and both platforms.

- **Today:**
  - `storage_detection` excludes the disk that holds the boot media using ISO-specific probes (`/iso`, `/nix/.ro-store`, squashfs, iso9660 mounts) plus the `RM` (removable) flag.
  - On the SD image, root is a plain ext4 partition on the card, so none of the ISO probes match. SD and eMMC devices usually report `RM=0`, so the removable rule doesn't match either.
  - Consequences, after the user's note on the "only if empty" safeguard:
    - **At boot:** the card's partitions count as existing storage, so the run **aborts**. That is safe, but it blocks auto-provisioning on every CM4.
    - **In the TUI or forced-cleanup paths:** the card **is planned**, so it can be wiped.
  - **x86, at boot, is worse** (trbarbour/NixOS-boot-image#306): the scan *excludes* a correctly identified boot stick, so the safeguard passes, while the plan *includes* a stick reporting `RM=0`, which is then wiped.
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
  3. EEPROM `BOOT_ORDER`: now a requirement of its own (R-B2), designed in §3.9.

### 3.8 Network (§2.6, unchanged requirement)

The `lan` rename uses a MAC-matched systemd `.link` file, which doesn't depend on the architecture. The CM4's `bcmgenet` NIC usually appears as `end0`. **Verify on hardware (E8)**; the VM test (§4) covers the code path with virtio-net.

### 3.9 Boot order (R-B2)

The user's point (2026-10-18): on a Pi-family board, which device boots is decided **before** any of our software runs, by the bootloader in the board's EEPROM and its `BOOT_ORDER` setting. That setting must be right for an installation to succeed. Unlike the rest of the early boot chain (U5), this part does interact with what pre-nixos does.

**Why it matters, with the failure modes to design out:**

1. If the order prefers the SD card and the card is still inserted after installation, the board boots the installer again rather than the installed system. The "only if empty" safeguard then finds the new installation and stops. That is not destructive, but the board never runs its installed system unattended. (Corrected: an earlier version said this would re-provision the fresh install.)
2. Destruction remains possible only on paths that bypass the safeguard: forced cleanup (`PRE_NIXOS_FORCE_CLEANUP`) or an operator applying from the TUI.
3. If the order lacks the target device class (for example NVMe), the installed system never boots.

**Candidate order:** installed-system device first, then SD, then retry. For an NVMe target that would be `BOOT_ORDER=0xf16`; the digits are read from the least significant end, with 6 = NVMe, 1 = SD/eMMC and f = restart. An empty NVMe falls through to the SD installer; after installation the NVMe boots first. **One setting serves both phases.** The digit meanings must be confirmed against the Raspberry Pi bootloader documentation for the user's EEPROM version (E11).

**Design debate: where the boot order gets set.**

- **(a) Operator prerequisite, documented.**
  - The operator sets `BOOT_ORDER` once per board, using `rpiboot`/usbboot from a host or `rpi-eeprom-config` on a running system.
  - Pros: no EEPROM writes from our code, which keeps the risk of bricking or write-protection surprises out of it.
  - Cons: easy to forget, and on its own it doesn't meet R-B2's "verify".
- **(b) The boot image carries a prepared EEPROM update.**
  - Ship `pieeprom.upd` and `recovery.bin`, so the bootloader applies them at first boot.
  - Pros: automatic.
  - Cons: it also changes the EEPROM *firmware version* to whatever we ship, an uncontrolled side effect. It fires on every board the card is put into, and it is not idempotent unless the files are removed afterwards.
- **(c) pre-nixos changes only `BOOT_ORDER` at install time.**
  - Read the current configuration (`rpi-eeprom-config`, or `vcgencmd bootloader_config`), change just `BOOT_ORDER` for the planned target class, and stage the update for the next reboot.
  - Pros: changes exactly what installation needs, and only when installing.
  - Cons: depends on EEPROM tooling behaving as hoped (E12, E13) and on the EEPROM being writable (E14).
- **Recommended: (a)+(verify) now, (c) later if E12–E14 come out well.**
  - Always **read and check** the effective `BOOT_ORDER` before installing. If the target device class would not boot before the SD card, stop with a clear message naming the needed value, in the TUI and on the serial console. This meets R-B2 safely.
  - Automating the change (c) is a later, separately approved step.
  - Independent of both: after a successful install, make a second installer boot report clearly, on serial and in the TUI, that an installed system exists and the boot order is the likely cause. The safeguard already prevents re-provisioning.

**Tests:**

- Unit tests:
  - parse `BOOT_ORDER` (a hex nibble list) into an ordered list of device classes;
  - decide "does target class X boot before SD?";
  - check the refusal and warning messages.
- These unit tests use captured `rpi-eeprom-config` output from the user's CM4 (E10) as fixtures.
- Real EEPROM behaviour can only be checked on hardware (§4).

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
| E10 | The user's current EEPROM configuration and version | **user runs** `rpi-eeprom-config` and `vcgencmd bootloader_version` on the CM4 (nixpkgs `raspberrypi-eeprom`) | needs the user |
| E11 | `BOOT_ORDER` digit meanings for the user's bootloader version (1 = SD/eMMC, 4 = USB, 6 = NVMe, f = restart?) | check the Raspberry Pi bootloader documentation for that version; confirm on hardware | to do |
| E12 | Is the EEPROM configuration readable from the booted SD image without a reboot? | run `rpi-eeprom-config` and `vcgencmd bootloader_config` in the stock image | needs the user |
| E13 | Can only `BOOT_ORDER` be changed, keeping the current EEPROM firmware version? (Which image does `rpi-eeprom-config --apply` use?) | read the tool's source in nixpkgs `raspberrypi-eeprom`, then try it on the user's CM4 | to do / user |
| E14 | Is the CM4's EEPROM write-protected (WP pin, `eeprom_write_protect`)? | user checks the carrier board and `config.txt` | needs the user |
| E15 | CM4 variant constraints: with eMMC fitted, can the carrier board's microSD slot boot at all (both share the SD interface)? If not, an eMMC CM4 cannot boot this image from a microSD card, and its install target is NVMe or USB. | Raspberry Pi CM4 documentation; the user's board | to do / user |

## 6. Work breakdown (in order; each item cites its requirements)

1. **Requirements:** apply §2's text to `automated-pre-nixos-reqs.md` once approved, and decide the §2.3 auto-apply anomaly. *(R-P1, R-B1, R-S1, R-S2, R-C1, R-T1)*
2. **Boot-medium protection (§3.1)**, with unit and VM tests. Platform-independent and safety-critical, so it lands first and also benefits x86. *(R-S1)*
3. **Partition naming and storage classification (§3.5)**, with unit tests. *(R-S2)*
4. **Console parameters (§3.6)**, with unit tests. *(R-C1)*
5. **Build host support (§3.3):** hook and `dev_packages`; E4. *(R-T1)*
6. **Flake refactor (§3.2) and platform-conditional module (§3.4)**, with the Nix evaluation check. *(R-P1, R-P2)*
7. **AArch64 VM test (§4):** E5 and E6. *(R-S1, §2.6–2.8)*
8. **Installed-system bootloader (§3.7):** once the user has answered §3.7; E9. *(R-B1)*
9. **Boot-order verification (§3.9):** parse and check `BOOT_ORDER`, refuse or warn before installing, and prevent re-provisioning after install; E10–E15. Automated `BOOT_ORDER` changes only after separate approval. *(R-B2)*
10. **Hardware acceptance on a CM4** (user), recorded in `docs/test-reports/`. It includes the reboot after installation booting the installed system, with the SD card still inserted. *(all)*

Version policy: each feature is a minor bump and each fix a patch bump (AGENTS.md).

## 7. Inputs needed from the user

1. Approve or amend the requirements text in §2.
2. Decide the §2.3 auto-apply anomaly: change the requirement or the behaviour.
3. Answer §3.7 (install target, CM4 variant) and §3.9: accept or amend the recommendation to verify `BOOT_ORDER` now and automate the change later. Is it acceptable for the installer to refuse to install when the boot order is wrong?
4. Run E7 and E8 on a CM4 booted from the stock image, and paste the output:
   `lsblk -o NAME,RM,ROTA,TYPE,SIZE,MODEL; cat /proc/cmdline; ip -br link; ls /dev/ttyAMA* /dev/ttyS*`
5. Run E10, E12 and E14 on the CM4: `rpi-eeprom-config; vcgencmd bootloader_version; vcgencmd bootloader_config`. In the stock image these may need `nix-shell -p raspberrypi-eeprom libraspberrypi`.
