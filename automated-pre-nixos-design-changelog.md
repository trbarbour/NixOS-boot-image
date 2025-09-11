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
