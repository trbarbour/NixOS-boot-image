# 📜 Changelog — Automated Pre-NixOS Setup Design

### v0.1 — 2025-08-31
- Initial draft created from requirements (`automated-pre-nixos-setup.md`) via design-debate template.  
- Included baseline goals: deterministic RAID/LVM setup, ext4 everywhere, serial console output, NIC rename to `lan`.  
- Style: fully detailed, explanatory sections.

### v0.2 — 2025-09-01
- Added **equal-size RAID set requirement**: no truncation of larger disks, no mismatched arrays.  
- Clarified RAID heuristics (SSD pair RAID0 by default, HDD RAID1/5/6 depending on count).  
- Expanded pseudocode for inventory and RAID grouping.

### v0.3 — 2025-09-03
- Refined **swap policy**:  
  - Default: **VG `swap`** on HDD RAID1 mirror.  
  - Fallback: if no `swap` VG possible, create swap LV on **VG `large`** (HDD only).  
  - Never use SSD/NVMe for swap.  
- Adjusted LVM layout to include `swap/swap` LV, with fallback to `large/swap`.

### v0.4 — 2025-09-05
- Added **serial-console resilience**:  
  - All serial writes best-effort and non-blocking, wrapped in timeouts.  
  - Absence or disconnection of serial console must not cause hangs/failures.  
  - Logs always duplicated to journald and `/var/log`.  
- Expanded **State Machine / Flow** to detail non-blocking log fan-out and serial handling.  
- Enhanced **Risks & Mitigations** with explicit coverage of serial device failures.  
- Expanded **Test Plan** with T9 (no serial console scenario).  
- Corrected and fully expanded document back into original detailed style (no “unchanged” placeholders).  
- Header updated to **Draft v0.4**, dated 2025-09-05.

### v0.5 — 2025-09-08
- Added Python project skeleton with inventory, planner, apply, network modules and CLI.
- Implemented disk enumeration, grouping heuristics, basic plan generation, and stub application.
- Introduced pytest test suite covering inventory, planning, apply, network, and CLI behaviour.

### v0.6 — 2025-09-09
- Added Nix flake packaging with dev shell and packaged runtime dependencies.

### v0.7 — 2025-09-09
- Added NixOS module and flake export for optional service.

### v0.8 — 2025-09-09
- Defined ISO configuration in flake and documented build instructions.

### v0.9 — 2025-09-09
- Clarified volume group naming: only the largest SSD/HDD bucket uses `main` or `large`; smaller buckets get suffixed names and remain unmounted.

### v0.10 — 2025-09-09
- Replaced assumption of external `authorized_keys` with built-in root SSH key.
- Documented key-only login and requirement to replace the embedded key when building images.

### v0.11 — 2025-09-10
- Clarified serial-console login: bootloader and kernel configured for serial, serial `getty` started.
- Root password remains usable for console logins while SSH password auth is disabled.
- Logging fan-out writes to the kernel console instead of a hardcoded serial device.

### v0.12 — 2025-09-11
- Deferred OpenSSH startup until after `secure_ssh` hardens configuration, preventing password-logins during boot.
- Documented manual disk provisioning workflow via interactive `pre-nixos-tui`.

### v0.13 — 2025-09-11
- Extended the TUI to display the machine's current IP address.

### v0.14 — 2025-09-11
- TUI now reports when the embedded SSH key is missing or no IP address is
  assigned.

### v0.15 — 2025-09-11
- Documented a pictorial TUI layout with four-column disk→array→VG→LV flow.
- Added design for zoomable overview/detailed modes driven by terminal size.
- Captured requirement to toggle between existing storage state and planned
  layout, highlighting differences directly in the UI.

### v0.16 — 2025-09-11
- Refined the TUI density handling to probe the layout off-screen and choose the
  richest profile that fits the current terminal instead of relying on a static
  80×24 cutoff.
- Clarified that manual zoom is anchored on the focused branch so comparisons
  keep the same subtree centred when switching views.

### v0.17 — 2025-09-11
- Published detailed ASCII mock frames under `docs/tui-mockups/` covering mixed
  SSD/HDD plans, the auto-scaled 80×24 minimal profile, and side-by-side
  existing-versus-planned comparisons.
- Linked the main design doc to those mocks so implementers have copy-ready
  targets for rendering behaviour.

### v0.18 — 2025-09-11
- Synced main design doc to Draft v0.18 with storage erasure notes matching the
  recent cleanup flow changes.

### v0.19 — 2025-09-12
- Documented the limitation of pre-apply storage erasure (only existing
  descendants are visible pre-partition) and the new cheap follow-up scrub that
  zeros planned md member metadata and retries Disko once after a failure.

### v0.20 — 2025-12-12
- Updated the main design to the global graph-based cleanup (lsblk + LVM +
  losetup), leaf-to-root teardown with explicit LV/VG deactivation, resilient
  metadata wiping even after partial teardown, and richer diagnostics for wipe
  and partition-refresh failures.

### v0.21 — 2025-12-13
- Clarified that storage cleanup now deletes LVM metadata (lvremove/vgremove/
  pvremove) before zeroing md superblocks and wiping residual signatures.

### v0.22 — 2026-10-19
- Added §7.6.1, the AArch64 (Pi 4 / CM4) installed bootloader:
  - the Pi firmware with an NVMe-capable U-Boot and extlinux on the shared FAT `/boot`;
  - the platform is declared by the image.
- This follows finding E9a: stock U-Boot has no NVMe driver.

### v0.23 — 2026-10-20
- §7.6.1: added the Raspberry Pi `BOOT_ORDER` check (R-B2). Installation is refused unless NVMe boots before SD; the EEPROM is read only.

### v0.24 — 2026-10-21
- Added §7.8.1, site settings: the root key and auto-install are supplied purely, from a directory outside git, as the flake input `site` or through `lib.mkBootImage`. This covers the ISO and the SD image.

### v0.25 — 2026-10-22
- §7.6.1: the Pi's loader settings moved from the managed block to a separate, imported module with `mkForce`. In the managed block they duplicated `nixos-generate-config`'s lines, which is a parse error (#320, found by CM4 acceptance).

### v0.26 — 2026-10-23
- Added the primary console (R-C2): the site setting `primaryConsole`, serial by default on AArch64 and display on x86. Serial primary appends the serial console once more. R-P2 is amended so that the order of the SD image's consoles may change, but not their set.
- §7.6.1: the Pi boot module also puts `pcie-brcmstb` and `nvme` in the installed initrd (#323).

### v0.27 — 2026-10-30
- §5, §7.3, §7.6.1: the ESP is sized at 3% of its disk, clamped to [1 GiB, 4 GiB], instead of a fixed 1 GiB (R-B3). Array members share one size, from the smallest member. The boot image's SD layout is unchanged (R-P2); its FAT partition holds no generations.
- §7.3: the ESP labels are `EFI`, `EFI2`, …, as the planner has always made them (the text said `ESP`).

### v0.28 — 2026-10-31
- §7.6.0: x86 installs under legacy BIOS (R-B1 amended, R-B4).
  - The firmware mode is detected at install time.
  - The x86 boot disks get a BIOS boot partition (EF02, partition 1).
  - Under BIOS, `/boot` and GRUB go on the first non-NVMe disk set (main, other SSDs, swap, large).
  - GRUB targets the boot disks by `by-id`.
  - With no bootable disk, the install is refused before provisioning.
- §7.3: the per-disk layout notes the EF02 partition.
