# Plan: AArch64 boot image for Raspberry Pi CM4 (microSD)

- Written 2026-10-18 14:21Z, on a branch at version 0.10.0.
- Status: **approved; implementation not started** (except §3.1, done for both platforms by #306, #308 and #309).
- 2026-10-18 22:03Z: the user's answers to §7 were received (verbatim copy: `plans/2026-10-18T220351Z-aarch64-user-answers.txt`) and are recorded in §8.
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
| U6 | §2's requirements text is **approved** (2026-10-18 22:03Z). |
| U7 | The §2.3 anomaly is resolved by **changing the requirement**. Done in #308: auto-provision only when every candidate disk is empty. |
| U8 | **Install target: NVMe.** eMMC is nice to have; only one of the user's CM4s has eMMC, and all the others are Lite. |
| U9 | Verifying `BOOT_ORDER` now and automating changes later is accepted. **The installer may refuse to install when the boot order is wrong.** |

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
| **R-B2** | On AArch64 Pi, the board's boot order must make the **installed system boot after installation**, without the installer running again, while still letting the installer boot on a machine with no installed system. pre-nixos must **verify** the effective boot order before it installs, and must **refuse to install** if the installed system would not be booted. | new | user, 2026-10-18; U9; §3.9 below |

**Anomaly for the user, independent of AArch64.** Corrected 2026-10-18 after the user's note. **Resolved (U7)** by the §2.3 amendment in #308.
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
| E7 | CM4 facts: block devices and flags (`lsblk -o NAME,RM,ROTA,TYPE,SIZE,MODEL`), `/proc/cmdline`, which UART is live | **user runs these** on a CM4 booted from the stock image | **Done** (§8.1) |
| E8 | NIC name on a CM4 (`ip -br link`) | as E7 | **Done**: `end0`, plus `wlan0` (§8.1) |
| E9 | Can the installer fill a firmware partition reproducibly from `populateFirmwareCommands`? | build a firmware-partition derivation and compare its files with the stock image's FIRMWARE partition | to do |
| E10 | The user's current EEPROM configuration and version | **user runs** `rpi-eeprom-config` and `vcgencmd bootloader_version` on the CM4 (nixpkgs `raspberrypi-eeprom`) | **Configuration: done.** Version: unknown, because `vcgencmd` fails (no `/dev/vcio`) (§8.2) |
| E11 | `BOOT_ORDER` digit meanings for the user's bootloader version (1 = SD/eMMC, 4 = USB, 6 = NVMe, f = restart?) | check the Raspberry Pi bootloader documentation for that version; confirm on hardware | **Partly done**: the board's own `boot.conf` comments say 1 = SD, 2 = network, 4 = USB over PCIe, 5 = BCM-USB-MSD (SoC XHCI), 6 = NVMe (§8.2). Still to check against the documentation. |
| E12 | Is the EEPROM configuration readable from the booted SD image without a reboot? | run `rpi-eeprom-config` and `vcgencmd bootloader_config` in the stock image | **Yes**, through `rpi-eeprom-config`, which reads the `blconfig` nvmem device. `vcgencmd` does not work (§8.2). |
| E13 | Can only `BOOT_ORDER` be changed, keeping the current EEPROM firmware version? (Which image does `rpi-eeprom-config --apply` use?) | read the tool's source in nixpkgs `raspberrypi-eeprom`, then try it on the user's CM4 | to do / user |
| E14 | Is the CM4's EEPROM write-protected (WP pin, `eeprom_write_protect`)? | user checks the carrier board and `config.txt` | not answered; needed only for the deferred option (c) |
| E15 | CM4 variant constraints: with eMMC fitted, can the carrier board's microSD slot boot at all (both share the SD interface)? If not, an eMMC CM4 cannot boot this image from a microSD card, and its install target is NVMe or USB. | Raspberry Pi CM4 documentation; the user's board | to do / user |
| E16 | The user's stock image is **NixOS 26.05**, while this flake pins **25.05**. Does our module, and does the x86 ISO, work on 26.05? | evaluate and build on 26.05 (this affects x86 too, so it is a separate task) | to do; queued |

## 6. Work breakdown (in order; each item cites its requirements)

1. **Requirements:** apply §2's text to `automated-pre-nixos-reqs.md` once approved, and decide the §2.3 auto-apply anomaly. *(R-P1, R-B1, R-S1, R-S2, R-C1, R-T1)*
2. **Boot-medium protection (§3.1)**, with unit and VM tests. Platform-independent and safety-critical, so it lands first and also benefits x86. *(R-S1)*
3. **Partition naming and storage classification (§3.5)**, with unit tests. *(R-S2)*
   - **2026-10-19: done (0.13.0)** except the typed boot-partition kind, which moves to item 8 because it depends on the §3.7 bootloader design.
     - New `pre_nixos/block_names.py`. `partition_name()` implements the kernel's rule (`p` when the disk name ends in a digit; `block/partitions/core.c:335-338`). `is_emmc_hardware_area()` recognises `mmcblkNbootM`/`mmcblkNgpM`, which are extra block disks of the same chip (`drivers/mmc/core/block.c:2525-2539, 2637-2638`); RPMB is a character device.
     - Used by the planner (partition names), `enumerate_disks` (eMMC hardware areas are never candidates) and the existing-storage scan (§2.3: only candidate disks count).
     - Classification needed no change: the user's CM4 `lsblk` shows `ROTA 0` for `mmcblk0` and `nvme0n1`. The no-SSD case was fixed by #313.
     - Tests: `tests/test_block_names.py` (16).
4. **Console parameters (§3.6)**, with unit tests. *(R-C1)*
   - **2026-10-19: done (0.14.0).** `install._select_console_kernel_params` keeps every booted `console=`, each at its last occurrence, so the booted primary stays primary.
     - Serial means anything but `tty<N>`, which covers `ttyAMA*`.
     - Both kinds are always present; a missing one is added in front.
     - Fixture: the user's real CM4 command line gives `ttyS0, ttyAMA0, tty0`, as booted. Previously `ttyAMA0` was dropped.
     - Existing x86 behaviour is unchanged (`tests/test_install.py`).
     - The GRUB serial lines (x86 only) move to item 8.
     - Tests: `tests/test_console_params.py`.
5. **Build host support (§3.3):** hook and `dev_packages`; E4. *(R-T1)*
6. **Flake refactor (§3.2) and platform-conditional module (§3.4)**, with the Nix evaluation check. *(R-P1, R-P2)*
7. **AArch64 VM test (§4):** E5 and E6. *(R-S1, §2.6–2.8)*
8. **Installed-system bootloader (§3.7):** once the user has answered §3.7; E9. *(R-B1)*
9. **Boot-order verification (§3.9):** parse and check `BOOT_ORDER`, refuse or warn before installing, and prevent re-provisioning after install; E10–E15. Automated `BOOT_ORDER` changes only after separate approval. *(R-B2)*
10. **Hardware acceptance on a CM4** (user), recorded in `docs/test-reports/`. It includes the reboot after installation booting the installed system, with the SD card still inserted. *(all)*

Version policy: each feature is a minor bump and each fix a patch bump (AGENTS.md).

## 7. Inputs needed from the user

**Answered 2026-10-18 22:03Z** (see §8). Items 1 to 4 are complete. Item 5 is partly complete: the bootloader version and write protection are still unknown, and neither blocks the work.


1. Approve or amend the requirements text in §2.
2. Decide the §2.3 auto-apply anomaly: change the requirement or the behaviour.
3. Answer §3.7 (install target, CM4 variant) and §3.9: accept or amend the recommendation to verify `BOOT_ORDER` now and automate the change later. Is it acceptable for the installer to refuse to install when the boot order is wrong?
4. Run E7 and E8 on a CM4 booted from the stock image, and paste the output:
   `lsblk -o NAME,RM,ROTA,TYPE,SIZE,MODEL; cat /proc/cmdline; ip -br link; ls /dev/ttyAMA* /dev/ttyS*`
5. Run E10, E12 and E14 on the CM4: `rpi-eeprom-config; vcgencmd bootloader_version; vcgencmd bootloader_config`. In the stock image these may need `nix-shell -p raspberrypi-eeprom libraspberrypi`.

## 8. User answers and findings (2026-10-18 22:03Z)

Verbatim answers: `plans/2026-10-18T220351Z-aarch64-user-answers.txt`. The board was booted from the stock NixOS **26.05** SD image (`nixos-sd-card-26.05.11985.26f4107e47e3`).

### 8.1 Hardware facts (E7, E8) and what they change

| Observation | Consequence |
|---|---|
| `mmcblk0` (238.8G SD card): **RM=0**, `p1` 30M (firmware), `p2` (root) | Confirms §3.1's premise: the RM flag cannot protect the card. The card is protected by the mount-table rule (root is on `mmcblk0p2`), already covered by `tests/test_protected_disks.py::test_sd_card_root_is_protected`. |
| `nvme0n1` (Samsung 512G) already has 4 partitions: 260M, 16M, 475.9G, 774M | The layout looks like a Windows install (ESP, MSR, data, recovery), but that is an inference, not checked. Either way it is existing storage, so at boot pre-nixos **only plans** (§2.3). Installing on this board needs `pre-nixos-force-cleanup=1` or the TUI. That is intended behaviour, but the hardware checklist (§4) must include it. |
| Kernel command line: `console=ttyS0,115200n8 console=ttyAMA0,115200n8 console=tty0`, but **no `/dev/ttyAMA*` exists**; `ttyS0` to `ttyS3` exist | The live UART is `ttyS*`, not `ttyAMA0`. R-C1's decision stands: copy every booted `console=` verbatim and in order, so the installed system matches the stock image. A console that names a missing device is harmless as long as it is not the last one (the last is primary; here that is `tty0`). Add the real command line as a unit-test fixture. |
| NICs: `end0` (UP), `wlan0` (DOWN, NO-CARRIER) | `end0` is as predicted (§3.8). New unit test: with `wlan0` present but without carrier, `end0` is the NIC renamed to `lan`. |
| CM4 Lite (SD card is `mmcblk0`, no eMMC device) | U8: the install target is NVMe. eMMC is deferred. E15 still matters for the user's one eMMC board. |

### 8.2 EEPROM (E10, E11, E12)

**The printed configuration:**
```
BOOT_UART=1  WAKE_ON_GPIO=1  POWER_OFF_ON_HALT=0  ENABLE_SELF_UPDATE=1
## Try SD first (1), followed by, USB PCIe, NVMe PCIe, USB SoC XHCI then network
#BOOT_ORDER=0xf25641
# Try NVMe PCIe first (6), followed by, SD, BCM-USB-MSD (SoC XHCI) then network
BOOT_ORDER=0xf2516
```
`vcgencmd` failed in both cases: `Can't open device file: /dev/vcio`.

**Where the configuration came from.** I checked the source of `rpi-eeprom-config` in nixpkgs `raspberrypi-eeprom` 2025.03.10. That is the version our pinned 25.05 has; the user ran the 26.05 one, which is not checked.
- With no arguments, `read_current_config()` first reads the **`blconfig` nvmem device**. That is the configuration the running bootloader used, which it exposes through the device tree (`/sys/firmware/devicetree/base/aliases/blconfig`).
- It falls back to `vcgencmd bootloader_config` only when that device is missing.
- Since `vcgencmd` failed but a configuration was still printed, the printed text most likely came from `blconfig`, so it is the board's effective configuration.
- **Consequence for §3.9:** the verification can read the configuration without `vcgencmd` or `/dev/vcio`.

**`0xf2516` versus the user's `0xf25146`.**
- Nibbles are read from the least significant end:
  - `0xf2516` = NVMe → SD → BCM-USB-MSD → network → restart;
  - `0xf25146` = NVMe → USB-over-PCIe → SD → BCM-USB-MSD → network → restart.
- **Both boot NVMe before SD**, so both satisfy R-B2, and the verification accepts both.
- The user suspects the NixOS installation changed the value. The evidence points elsewhere:
  - the text is a hand-edited configuration: the default line is commented out, and a new line with a comment explaining it was added;
  - nothing in a NixOS install writes the EEPROM unless asked to;
  - the bundled Pi 4 default `boot.conf` (extracted from `pieeprom-2025-02-11.bin`) has no `BOOT_ORDER` line and has `BOOT_UART=0`, so the board's text is not that default.

  Who edited it, and when, cannot be determined from here. It does not affect the design.
- **Correction (user, 2026-10-18 22:16Z).**
  - The user set `BOOT_ORDER` on all their CM4s, NVMe first, so the edit above is the user's own.
  - The user's records give `0xf25146` for this board too. The only open point is why the `4` (USB over PCIe) is missing; most likely a later change that was not recorded.
  - This does not affect the design: both values boot NVMe before SD.
- The digit meanings in the board's comments match the user's reading that 4 is "USB PCIe". That digit is useless on boards whose PCIe lane drives the NVMe.

**Still unknown, and not blocking:**
- The bootloader version (`vcgencmd` cannot run).
- Whether `/dev/vcio` can be created (`mknod /dev/vcio c 100 0`, as the tool suggests) on the NixOS kernel. That needs the `bcm2835` vcio driver, which is not checked.
- E14 (write protection), which matters only for the deferred option (c).

### 8.3 Effects on the work breakdown (§6)

- **Item 1 (requirements):** approved, and applied to `automated-pre-nixos-reqs.md` on 2026-10-18.
- **Item 2 (boot-medium protection):** done (#306, #308, #309).
- **Item 8 (installed bootloader):** design for an **NVMe** target first. eMMC is a later extension and needs E15.
- **Item 9 (boot order):**
  - read the configuration through `rpi-eeprom-config`, i.e. `blconfig`;
  - **refuse** to install unless the target class (6 for NVMe) comes before 1 (SD) in `BOOT_ORDER`;
  - unit-test fixtures: the board's configuration above, plus a `0xf25146` variant;
  - unit test: `0xf25641` (SD first) is refused for an NVMe target.
- **Item 10 (hardware acceptance):** includes forced cleanup of an NVMe that already holds data.
- **New, E16:** a nixpkgs 25.05 → 26.05 bump. The AGENTS.md policy prefers the newer version, and the user's stock image is 26.05. It affects x86 too, so it is queued as its own task.
  - **Decided** by the user (2026-10-18 22:16Z): update the pin, since 26.05 is now stable and 25.05 is simply out of date.

