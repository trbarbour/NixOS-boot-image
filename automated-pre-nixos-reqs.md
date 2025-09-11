# 📄 Requirements Specification: Automated Pre-NixOS Setup

**Project Name:** Automated Pre-NixOS Storage and Network Setup  
**Author:** [User]  
**Target Audience:** LLM-based system designer (e.g. GPT-4)  
**Purpose:** To automate the hardware initialization steps required before installing NixOS on bare-metal servers.  
**Scope:** Covers disk discovery, partitioning, RAID/LVM configuration, and minimal networking for remote access.

---

## 1. 📘 Overview

The system must automate the hardware setup process on new servers prior to NixOS installation. The process begins after booting from removable media and proceeds non-interactively until the user can access the machine remotely via SSH, and over a serial console. The result must be a fully initialized storage and networking environment ready for NixOS installation.

---

## 2. ✅ Functional Requirements

### 2.1 Disk Detection and Classification

- Detect all block devices present on the machine.
- Classify them by type, size and function:
  - SSD(s): designated for system/root volume.
  - For each group of (approximately) same-sized rotating disks:
    - If exactly two → use for swap on RAID-1.
    - If three or more → use for bulk storage on RAID-5 or RAID-6, depending on count.

### 2.2 RAID Configuration

- Create appropriate RAID arrays from disk groups, based on disk type and quantity:
  - **SSD pair** → RAID-0 (for performance), unless overridden for redundancy.
  - group of **2× HDDs** → RAID-1 (for swap).
  - group of **3–4× HDDs** → RAID-5.
  - group of **5+ HDDs** → RAID-6.
- RAID arrays must use `mdadm`.

### 2.3 Partitioning

- All disks must use a **GPT partition table**.
- On system (boot) disk or SSD array:
  - Create partitions for UEFI booting (EFI System Partition), and LVM usage.
  - UEFI booting is mandatory.

### 2.4 LVM Configuration

- Create one **LVM physical volume** per RAID array or standalone disk set.
- Create **LVM volume groups** corresponding to their class:
  - `main` for the system volume (on SSDs).
  - `swap` for swap (on rotating RAID-1), if present, otherwise put `swap` LV in `large` VG if present; no swap on SSD.
  - `large` for bulk storage (on RAID-5/6).
- LVM volumes should be used instead of bare partitions wherever possible and reasonable.

### 2.5 Filesystems

- Use **ext4** for all filesystems.
- When the target use is snapshot-style backups using hardlinks (e.g., `rsync --link-dest`), configure ext4 with high inode density (e.g., 1 inode per 2KB).
- All filesystems must be labeled and mounted by label (not by device path or UUID).

### 2.6 Network Interface Detection

- Detect all network interfaces.
- Identify which NIC is **physically connected to a live network**.
- Rename the active NIC to `lan` using a predictable naming mechanism (e.g., systemd link file or udev rule).

### 2.7 SSH Access

- Only public key authentication is permitted for the root account over SSH.
- Root login must be possible over the serial console (if functional).
- A default public key is embedded into `/root/.ssh/authorized_keys`.
- Builders must replace the embedded key with their own before creating an image.

---

## 3. ⚙️ Non-Functional Requirements

- The setup process must be **fully non-interactive** until remote access is available.
- Setup must proceed from **bootable removable media** (e.g., USB stick) with **serial console output**. This includes providing serial access to the **bootloader** and a login prompt on the serial console. The system must still work if a serial console is absent or disconnected.
- Setup must be **repeatable**, **deterministic**, and suitable for a **team-managed fleet**, though all installations will be performed by a single operator.

---

## 4. ⛓ Constraints

- **GPT partitioning** only. No DOS/MBR.
- **UEFI boot** is required. BIOS/Legacy mode is not supported.
- **ext4** must be used on all filesystems; other filesystems are out of scope.
- RAID levels are constrained to: **0, 1, 5, 6**.
- LVM must be used to abstract storage volumes except for boot partitions.
- The system must **not require local keyboard or display** access.

---

## 5. 📌 Assumptions

- Each machine has **at least one SSD**, either standalone or as a pair.
- Rotating disks may or may not be present.
- Boot media will be inserted manually at each machine.
- Machines may differ in disk count and NIC count, but these variations are detectable and predictable at runtime.

---

## 6. 🎯 Goals and Rationale

| Goal | Rationale |
|------|-----------|
| Repeatable setup | Avoids errors and enables rebuilds without variation. |
| Headless operation | Machines are in data center or remote rack environments. |
| Hardware-aware adaptation | Not all machines have the same layout; the setup must respond accordingly. |
| Ready for NixOS install | The final state must allow an automatic NixOS install to proceed immediately. |
| Efficient disk usage | Appropriate RAID level and inode density based on use-case. |
| Predictable networking | Simplifies NixOS config and remote management. |

---

## 7. 🚫 Out of Scope

- Post-setup configuration of NixOS itself.
- Deployment of NixOS configuration (handled separately via nixops-4 or deploy-rs).
- Graphical interfaces or physical user input devices.
- Support for btrfs, zfs, or filesystems other than ext4.

---

## 8. 🧩 Future Considerations (Not Required Now)

- Support for secure boot (UEFI signed bootloaders).
- Remote unlocking of encrypted volumes.
- Integration with deployment orchestration (e.g., nixos-anywhere, nixos-install-tools).
