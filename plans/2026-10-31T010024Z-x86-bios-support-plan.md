# x86 legacy-BIOS installs: plan (design debate, unknowns, work items)

_2026-10-31T010024Z. User request (2026-10-31): "I have a couple of old machines to install. Implement the guard first, then plan full support." Earlier: "BIOS is obsolete, so not worth a lot of effort."_

The guard (0.23.1, task queue item 33) refuses an auto-install on a legacy-BIOS machine before provisioning. This plan replaces that refusal with a working install, where the hardware allows one.

## 1. Requirements (proposed; need the user's approval)

- **R-B1 (amend):** x86_64 installs boot with **UEFI or legacy BIOS**, matching the mode the installer was booted in. Secure Boot stays out of scope (reqs §7).
- **R-B4 (new):**
  - On a legacy-BIOS machine, the installed system boots through GRUB (i386-pc) from the disks that hold `main`.
  - Its `/boot` is the same FAT partition as on UEFI (R-B3 size), so a disk moved between machines boots either way.
  - Disks the BIOS cannot boot from are refused before provisioning; NVMe is the expected case (see U2).
- **Unchanged:**
  - GPT only (reqs §2.3, §4: "No DOS/MBR");
  - the ISO boots both ways (it already does);
  - AArch64 is unaffected.

## 2. Facts (verified 2026-10-31)

| # | Fact | Evidence |
|---|---|---|
| F1 | The ISO is BIOS-bootable, and the installer, planner and provisioning already run under BIOS. | `isoImage.makeBiosBootable = true`; all x86 VM tests boot under QEMU's default SeaBIOS (`tests/vm/boot_medium.py`). |
| F2 | On BIOS, `nixos-generate-config` writes `boot.loader.grub.enable = true` with the device commented out. Our rendered configuration then fails: "You must set the option 'boot.loader.grub.devices' or 'boot.loader.grub.mirroredBoots'". | `tests/fixtures/nixos-generate-config/grub/`; the rendered configuration evaluated for x86_64 through `eval-config.nix`. |
| F3 | The layout has no BIOS boot partition (GPT type EF02), which GRUB needs for its core image on a GPT disk under BIOS. | `planner._plan_to_disko_devices`: only EF00 plus data. |
| F4 | On arrays, only the first member's ESP (`EFI`) is mounted, on `/boot`. `EFI2`, … are formatted but never kept in sync, on UEFI too. | `planner.py`: only `label == "EFI"` gets a mountpoint. |
| F5 | The ISO's store has `grub2_efi`, but not BIOS GRUB (`grub2`, i386-pc). | `iso-image.nix:880` `system.extraDependencies = [ grubPkgs.grub2_efi ]`; `installation-device.nix` adds stdenvNoCC, busybox, makeInitrdNGTool and jq. |

## 3. Design debate

### D1. How the installer knows the firmware mode
- **(a) Runtime detection: `/sys/firmware/efi` present or not.** Chosen. The same ISO boots both ways, so the image cannot declare it. The Pi's build-time declaration (item-8 design D4) still stands for the Pi.
- **(b) A site setting `x86Firmware = "uefi" | "bios"`.** Rejected: one ISO could no longer serve both kinds of machine, and a mismatch would install an unbootable system.
- The mode is still made explicit **after** detection: `InstalledBoot` gains `X86_BIOS_GRUB`, chosen when the setup is `nixos-default` and there is no EFI. Everything downstream (layout, loader module, checks) then follows the declared kind, not the probe.

### D2. Partition layout
- **(a) Always add a 1 MiB EF02 BIOS boot partition on `main` disks, UEFI installs included.** Chosen (proposed).
  - One layout boots both ways. The cost is 1 MiB, and an unused EF02 does nothing under UEFI.
  - It changes every new UEFI layout, so the user must agree.
- **(b) Add EF02 only on BIOS installs.** Smaller change to UEFI layouts; a disk moved to a UEFI machine still boots (the ESP is there), but one moved to BIOS does not.
- **(c) An MBR/DOS table on BIOS machines.** Rejected: reqs §2.3 and §4 require GPT.
- Order: EF02 first (sectors 2048–4095), then the ESP, then data. This keeps the ESP's size rule (R-B3) unchanged.

### D3. GRUB's target disks and redundancy
- **(a) `boot.loader.grub.devices` = every `main` disk's `/dev/disk/by-id/…` path.** GRUB's core image goes on each disk, but every copy reads `/boot` from the first member's ESP (F4). That is the same single point of failure as on UEFI today.
- **(b) `boot.loader.grub.mirroredBoots`:** mount `EFI2`, … as `/boot2`, …, and give each its own device, for true redundancy. Larger. It also fixes F4 for BIOS, but not for UEFI.
- **Proposal:** (a) now, which matches UEFI's current behaviour. Make (b) a separate item covering both firmware modes.

### D4. Where the loader settings live
- As on the Pi (#320): a module of its own, written by pre-nixos and imported from `configuration.nix`. It forces `grub.enable = true`, `grub.efiSupport = false`, `systemd-boot.enable = false`, and sets `grub.devices = [ … ]`. The generator's GRUB lines merge; they cannot clash.
- Unlike the Pi's static template, the device list is computed at install time, so pre-nixos renders it. The paths are escaped like the managed block's strings. The flake check then evaluates a rendered example.

### D5. Offline installs
- **(a) Add `grub2` (i386-pc) to the ISO's `system.extraDependencies`.** Chosen. A BIOS install then needs no network for its boot loader, as #311 required for disko. Covered by the offline-closure test (`tests/vm/offline_closure.py`).
- **(b) Rely on the binary cache.** Rejected: the installer must work offline.

## 4. Unknowns and experiments

| # | Unknown | Experiment |
|---|---|---|
| U1 | Some old BIOSes refuse to boot a GPT disk unless its protective MBR has the boot flag set (`pmbr_boot`). Do the user's machines? | On the user's old machines: install, then if it does not boot, set the flag (`parted <disk> disk_set pmbr_boot on`) and retry. If needed, the planner sets it. |
| U2 | Old BIOSes cannot boot NVMe. Which disks do the user's machines have, and are any NVMe? | Ask the user. Design: refuse (R-B4) when a `main` disk is NVMe and the mode is BIOS. |
| U3 | Does GRUB on a GPT EF02 with a FAT `/boot`, plus our LVM/md root, boot under SeaBIOS? | The VM test below (task queue item 12, now for BIOS): install in the VM, reboot from the target disk, check the root login. |
| U4 | Can `nixos-install` run offline in the VM, under TCG, in reasonable time? | Measure. This is item 12's own unknown. If too slow, mark the test `slow`, like the AArch64 ones. |
| U5 | Does the ISO's offline closure, with D5, cover a BIOS install's GRUB? | The offline-closure test, extended to a BIOS install's loader. |

## 5. Work items (in order)

1. **User decisions:** approve R-B1/R-B4, and choose between D2 (a) and (b). Answer U2 (disk types in the old machines).
2. **`InstalledBoot.X86_BIOS_GRUB`:** chosen at run time (D1). The guard's refusal narrows to the cases R-B4 refuses (U2).
3. **Planner:** an EF02 BIOS boot partition (D2), with unit tests and a disko dry run (`EF02`, 1 MiB).
4. **The loader module, rendered** (D4): unit tests, and a flake check that evaluates the GRUB fixture with the module. That check fails today with F2's assertion.
5. **ISO:** add `grub2` to `extraDependencies` (D5), plus the offline-closure test.
6. **End-to-end VM test under SeaBIOS** (U3, U4; item 12): auto-install, reboot from the target, root SSH. This is the largest item.
7. **Hardware test** on the user's old machines (U1). It decides whether `pmbr_boot` is needed.
8. **Docs:** reqs, design §7.6.0 and the README. Version 0.24.0.

Effort: items 2–5 are small, about one PR. Item 6 is most of the work. Item 7 needs the user.

## 6. User answers (2026-10-31) and the resulting changes

1. **R-B1/R-B4 approved.**
2. **D2:** the user asked for a recommendation. They used to add the 1 MiB partition always, "just in case"; the downside is "its increasing irrelevance in the future". **Proposed: D2 (a) on x86 only.**
   - EF02 on every x86 install, BIOS or UEFI, so a disk boots after moving between machines or modes, at a cost of 1 MiB.
   - **Order:** ESP partition 1, EF02 partition 2, data partition 3. The ESP stays partition 1, as the docs and the Pi chain assume, and nothing depends on partition numbers.
   - **Not on the Pi:** it has no BIOS. Its EEPROM finds the boot partition by the ESP's type GUID ("Matched GUID bootable-part-idx 0", attempt-4 log), and its layout has just passed acceptance (plan item 10).
3. **U2 answered:** the old machines have SAS/SATA disks and NVMe on PCIe carrier cards, and **cannot boot from NVMe**. The planner prefers NVMe for `main`, so refusing an NVMe `main` (the first R-B4 draft) would refuse exactly these machines. Hence D6.

### D6. Where `/boot` goes on a BIOS machine whose `main` is NVMe
- **(a) Refuse.** Rejected: it excludes the user's machines.
- **(b) Put `main` on SATA instead.** Rejected: it gives up the NVMe for the root, against the planner's tiering (reqs §2.2).
- **(c) Keep `main` on NVMe, and put `/boot` (ESP and EF02) and GRUB on a SATA/SAS disk.** Chosen (proposed). GRUB needs only `/boot` on a BIOS-readable disk; it loads the kernel and initrd from there, and the initrd has `nvme` to mount the root. The user must set that SATA disk first in the BIOS boot order.
  - **Which disk:** a small fixed partition set (ESP plus EF02) at the **start** of a non-NVMe disk the plan already uses, before its own data partition.
    - Preference: a non-rotational SATA/SAS disk, else the first rotational one. Ties are broken by device name, so the result is deterministic.
    - If that disk is an md array member, its partners get the same partitions, so the members stay the same size.
  - **No non-NVMe disk at all:** refuse before provisioning, as now (`REASON=bios-unsupported`), with the message naming the reason.
  - **R-B4 (revised):** on legacy BIOS, `/boot` and GRUB go on a BIOS-bootable (non-NVMe) disk; `main` may still be NVMe.
- **New unknown U6:** the SATA/SAS disks in the user's machines (SSD or HDD, how many, part of an array?). This decides which D6 branch they exercise. Asked.

## 7. Implementation status (0.24.0, 2026-10-31)

- **User decisions:** D2 (a) on x86 only, and D6 (user: "In the past I have used the swap disk(s) for this purpose"). The machines have probably one NVMe SSD and a pair of HDDs for swap; that case has its own test.
- **Change to D2's order, found by disko's dry run:** disko gives EF02 priority 100, before every other partition, because "some BIOS implementations require it". So on x86 the order is **EF02 partition 1, ESP partition 2, data partition 3**. The plan's names follow it (`test_plan_partition_numbers_match_disko`). The Pi has no EF02, so its ESP stays partition 1.
- **Done:**
  - work item 2: `InstalledBoot.X86_BIOS_GRUB` and `boot_platform.effective_setup`;
  - work item 3: `boot_layout.py` and the planner;
  - work item 4: `templates/boot-x86-bios-grub.nix`, rendered with by-id paths, plus the flake check `installed-bios-boot-loader`. Without the module the check fails, as today's installs do;
  - work item 5: `pkgs.grub2` in the ISO, checked by the same flake check;
  - the refusal narrowed to "no BIOS-bootable disk".
- **Verified:**
  - unit tests;
  - the flake checks: `installed-bios-boot-loader`, and `installed-configuration-parses` with the new kind;
  - a disko dry run of the user's shape, NVMe plus two HDDs: `sda1`/`sdb1` EF02 1M, `sda2`/`sdb2` EF00 4G, `sda3`/`sdb3` the mirror;
  - the x86 VM tests (SeaBIOS, so they now plan the BIOS layout). At 4759880: 7 passed, 1 failed. The RAID test hard-coded `main`'s physical volume on `/dev/sda2`, but the BIOS layout puts it on `sda3`. The test now asserts the x86 layout, with type GUIDs for EF02 on `sda1` and the ESP on `sda2`. Re-run at 5a3a1e5: **passed** (12 min 38 s).
- **Codex review on #330 (fixed in 5a3a1e5):** a group can mix NVMe and SATA disks of similar size. The boot partitions now go on its BIOS-bootable members only.
- **Not done:**
  - work item 6, the end-to-end install VM test (task queue item 12);
  - work item 7, the hardware test on the user's machines, which also settles U1 (`pmbr_boot`);
  - keeping the other boot disks' ESPs in sync (D3 (b), `mirroredBoots`).
