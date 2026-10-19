# AArch64 plan item 8: the installed system's bootloader (design)

Parent plan: `plans/2026-10-18T142135Z-aarch64-cm4-boot-image-plan.md` (§3.7 and §6, item 8).
Requirements: R-B1 (the installed system boots from its own disk) and R-B2 (it boots with the SD card still inserted, and the boot order is checked). Item 9 implements the R-B2 check.

## 0. Decision so far

- **2026-10-19:** the user chose option (a): a firmware partition on the NVMe target plus `generic-extlinux-compatible`.
- **Finding E9a (12:32Z):** nixpkgs' `ubootRaspberryPi4_64bit` (2026.04, plain `rpi_4_defconfig`) has no NVMe driver, and it scans `boot_targets=mmc usb pxe dhcp`.
  - Stock (a) therefore cannot see the NVMe disk.
  - With the card inserted, it would also boot the card.
- **The user then chose (a'):** (a) with a U-Boot that has `CONFIG_NVME_PCI=y` and scans `nvme` first. Option (d), the firmware loading the kernel directly, was rejected: it has no boot menu and no rollback.

## 1. The boot chain being built

1. **CM4 EEPROM bootloader:** follows `BOOT_ORDER` (NVMe before SD, checked by item 9) and reads the FAT partition on the NVMe disk.
2. **`start4.elf` and `config.txt`:** the stock files.
3. **`u-boot-rpi4.bin`:** **our** U-Boot (`nix/uboot-rpi4-nvme.nix`).
4. **U-Boot:** runs `bootflow scan`, which scans `nvme` first and finds `/extlinux/extlinux.conf` on the same FAT partition.
5. **The NixOS kernel and initrd:** the initrd assembles md and LVM, and root is `main/slash`.

## 2. Design choices (debate)

### D1. Partitions on the target: one FAT `/boot`, or a separate FIRMWARE partition plus `/boot`?

- **One FAT partition at `/boot`, holding the firmware, U-Boot and `extlinux/` with `nixos/`:**
  - It is the same shape as the x86 layout today: partition 1 is a 1 GiB vfat partition of type EF00 on `/boot`.
  - So the **planner and the disko output need no platform input**.
  - U-Boot and the EEPROM both read FAT.
  - The extlinux builder deletes only stale entries under `/boot/nixos/*` (`extlinux-conf-builder.sh`, line 164), so it leaves the firmware files alone.
- **A separate 30 MB FIRMWARE partition and `/boot` (as on the stock SD card, where `/boot` is on ext4 root):**
  - It mirrors the card.
  - But it needs a new partition kind in the planner, the TUI and disko, and U-Boot would need to find `/boot` on partition 2.
  - LVM root rules out keeping `/boot` on root as the card does, because U-Boot cannot read LVM.
- **Choice: one FAT `/boot`.**
  - The plan item 3 idea of a typed boot-partition kind (`esp` | `rpi-firmware`) is **withdrawn**: both platforms would get the same partition, so the type would have no consumer (YAGNI).
  - The label stays `EFI`. Nothing on the Pi reads it.
- **GPT and type EF00 on the Pi: unknown U7.** The EEPROM bootloader is believed to read a FAT partition from a GPT disk, as the RPi4 UEFI project's GPT ESP setups do. This must be confirmed on hardware (§4, E9c).

### D2. How the firmware gets onto `/boot`

- **(i) Build time: a derivation of the firmware files, copied by pre-nixos after disko mounts the target and before `nixos-install`:**
  - The derivation runs the stock `sdImage.populateFirmwareCommands` itself (reused, not copied: DRY, R-P2), then replaces `u-boot-rpi4.bin` with ours.
  - It goes into the image closure; that path is passed to pre-nixos in the environment.
- **(ii) Installed-system module: the installed configuration installs the firmware on every switch:**
  - Firmware updates would come with `nixos-rebuild`.
  - But `generic-extlinux-compatible` has no extra-install hook, so it needs a wrapper or a custom loader.
  - It is more code in the installed system, which pre-nixos otherwise leaves alone.
- **Choice: (i).**
  - It matches the stock card, whose FIRMWARE partition is also written once, at build time.
  - Updating the firmware is put on the task queue as a follow-up, not a requirement now.

### D3. The installed configuration's loader settings

- `nixos-generate-config` already writes `grub.enable = false` and `generic-extlinux-compatible.enable = true`. It does so because the **running** system has `/boot/extlinux`, which the SD image has (`nixos-generate-config.pl`, around line 689).
- That is a side effect of the host, not a statement of intent. pre-nixos's managed block therefore sets both **explicitly**. Equal boolean definitions merge, so the two do not conflict.
- The GRUB serial `extraConfig` lines stay x86 only. That moves item 4's leftover here.

### D4. How pre-nixos knows the platform

- **Runtime detection (`platform.machine()`, `/proc/device-tree/model`):** implicit, and a VM test on `-M virt` would take a different path from the CM4.
- **Build time: the image declares it.** The NixOS option `services.pre-nixos.installedBoot` is exported as `PRE_NIXOS_INSTALLED_BOOT`, and the firmware path as `PRE_NIXOS_RPI_FIRMWARE`.
  - The image's purpose already fixes the platform (traceable to R-B1).
  - The VM test exercises exactly the CM4 code path.
- **Choice: build time.**
  - Python parses the value once into an `enum` (`pre_nixos/boot_platform.py`, kept out of the 1182-line `install.py`).
  - An unknown value is an error.
  - An absent value means `nixos-default`, the x86 behaviour today (`nixos-generate-config` decides).

### D5. Which pkgs build our U-Boot

- **Native AArch64 under binfmt:** the same toolchain as the image and as the stock U-Boot. Its build time is measured in §3.
- **Cross from x86:** faster, but it brings a second toolchain into the image's closure.
- **Choice:** native, unless the measured build time is unacceptable.

## 3. Experiments

| ID | Question | Method | Status |
|---|---|---|---|
| E9a | Can stock U-Boot see NVMe? | `make rpi_4_defconfig`, then read `.config` and `rpi.env` | **done: no** (12:32Z) |
| E9 | Is our firmware directory the stock FIRMWARE partition with only `u-boot-rpi4.bin` changed? | extract the stock SD image's FAT with mtools, then diff | to do |
| E9b | Does our U-Boot see the CM4's NVMe? | **user, hardware:** put our `u-boot-rpi4.bin` on a stock SD card, then at the `U-Boot>` prompt run `pci enum; nvme scan; nvme info; bootflow scan -l` | to do |
| E9c | Does the EEPROM boot from a GPT disk with a FAT EF00 partition 1? | hardware acceptance (plan item 10) | to do |
| E9d | Does the installed system boot through extlinux (kernel, initrd, LVM root)? | VM: U-Boot for `qemu_arm64` with an NVMe disk; extlinux on the target's FAT partition | to do |

## 4. Unknowns

- **U7:** EEPROM and GPT (E9c).
- **U8:** U-Boot PCIe and NVMe on the user's carrier board and drive (E9b).
- **U9:** If NVMe fails at boot, `bootflow scan` falls back to `mmc` and boots the card, which would re-provision the machine. Item 9's "prevent re-provisioning after install" covers this.
