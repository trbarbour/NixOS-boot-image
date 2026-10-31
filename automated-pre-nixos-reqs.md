# 📄 Requirements Specification: Automated Pre-NixOS Setup

**Project Name:** Automated Pre-NixOS Storage and Network Setup  
**Author:** [User]  
**Target Audience:** LLM-based system designer (e.g. GPT-4)  
**Purpose:** To automate the hardware initialization steps required before installing NixOS on bare-metal servers.  
**Scope:** Covers disk discovery, partitioning, RAID/LVM configuration, and minimal networking for remote access.

---

## 1. 📘 Overview

The system must automate the hardware setup process on new servers prior to NixOS installation. It supports two target platforms (see §2.9). The process begins after booting from removable media and proceeds non-interactively until the user can access the machine remotely via SSH, and over a serial console. The result must be a fully initialized storage and networking environment ready for NixOS installation.

---

## 2. ✅ Functional Requirements

### 2.1 Disk Detection and Classification

- Detect all block devices present on the machine.
- Classify them by type, size and function:
  - SSD(s): designated for the system `slash` volume. NVMe, eMMC and SD
    (`mmcblk*`) devices count as solid-state. A machine **may have no SSD**,
    and a single solid-state device is a valid system disk. [R-S2]
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
- RAID arrays are created **without a write-intent bitmap** [R-R1]. An
  internal bitmap costs write performance, and an external one (e.g. on an
  SSD) is not supported by mdadm 4.4 and later. An internal bitmap can be
  added later, outside the boot image, with
  `mdadm --grow --bitmap=internal /dev/mdX`. (User decision, 2026-10-19.)

### 2.3 Partitioning

- Disks that contain data must **never** be modified automatically. Disk layout
  changes may be applied automatically at boot **only when every candidate disk
  is empty** (no partition table, filesystem, RAID or LVM metadata). This lets a
  quantity of new machines be installed efficiently.
- If any candidate disk contains data, the boot process only **generates a
  storage plan**. An operator must review and apply it (e.g., via the TUI), or
  explicitly request cleanup (e.g., the `pre-nixos-force-cleanup=1` kernel
  parameter).
- The medium holding the boot image, and any other disk backing the running
  system (holding a filesystem it has mounted or swap it uses), must **never**
  be planned, wiped or provisioned. It also does not count as existing storage
  when deciding whether automatic provisioning is allowed. [R-S1]
- All disks must use a **GPT partition table**.
- On system (boot) disk or SSD array, create partitions for booting and for
  LVM usage. Boot requirements are per platform [R-B1]:
  - **x86_64:** the installed system boots the way the installer was
    booted: **UEFI**, with an EFI System Partition, or **legacy BIOS**, with
    GRUB. (User decision, 2026-10-31.)
  - **AArch64 Raspberry Pi:** the installed system boots through the Raspberry
    Pi firmware, U-Boot and extlinux, as the stock NixOS SD image does.
- The installed system's boot partition (the EFI System Partition, which also
  holds the kernels and initrds of every generation kept) is sized at **3% of
  its disk, but at least 1 GiB and at most 4 GiB**. Each generation takes
  about 200 MB, so 1 GiB holds too few on a disk that can spare more. The
  boot image's own layout is unchanged (R-P2): its FAT partition holds only
  firmware, and its generations live on its root filesystem. [R-B3]
  (User decision, 2026-10-30.)
- On x86_64, every disk that holds boot partitions also gets a 1 MiB BIOS boot
  partition (GPT type EF02), whatever the firmware mode, so the disk boots
  under UEFI or legacy BIOS. The Raspberry Pi has none. Under **legacy BIOS**,
  `/boot` and GRUB go on a disk the BIOS can boot: the root's disks if they
  are not NVMe (old BIOSes cannot boot NVMe), otherwise another of the
  planned disks (the swap disks, for example), while the root stays on NVMe.
  With no such disk, an automatic install is refused before any storage is
  provisioned. [R-B4] (User decisions, 2026-10-31.)

### 2.4 LVM Configuration

- Create one **LVM physical volume** per RAID array or standalone disk set.
- Create **LVM volume groups** corresponding to their class:
  - `main` for the system volume (on SSDs).
  - `swap` for swap (on rotating RAID-1), if present. Otherwise put the swap LV in `large` VG if present, or in `main` (SSD/NVMe) when no rotating tier exists and capacity allows. If there is insufficient capacity anywhere, swap may be omitted.
  - `large` for bulk storage (on RAID-5/6).
- LVM volumes should be used instead of bare partitions wherever possible and reasonable.
- The logical volume layout must include:
  - `main/slash` as the root filesystem.
  - `main/home` mounted on `/home`, sized by default to **16 GiB or one quarter of the remaining free space** on `main` (after allocating `slash`), whichever is smaller.
  - `swap/swap` (or the fallback `large/swap` or `main/swap`) sized per the existing swap policy.
  - When a dedicated `swap` VG exists **and still has capacity after provisioning swap**, provision:
    - `swap/var_tmp` mounted on `/var/tmp`, default size equal to the allocated swap space, permissions `1777`.
    - `swap/var_log` mounted on `/var/log`, default size **4 GiB or the allocated swap size**, whichever is smaller.

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
- The `sshd` service must remain **disabled** during boot and is only enabled
  after its configuration is hardened (e.g., by `secure_ssh`).

### 2.8 User Interface

- Provide a curses-based TUI that allows operators to review and apply the
  storage plan.
- The TUI must display the machine's current IP address. If SSH was not
  secured due to a missing public key or the interface has no address, the
  TUI must indicate that state instead.

### 2.9 Target Platforms

- **x86_64 UEFI** machines boot an ISO; **AArch64 Raspberry Pi 4-family**
  machines (CM4, Pi 4) boot a microSD image. [R-P1]
- The AArch64 image is the stock NixOS AArch64 SD image plus pre-nixos.
  pre-nixos must **not change the stock image's boot chain or its set of
  kernel consoles**. Their order follows R-C2. [R-P2]
- Every platform's image builds from this repository on an x86_64 build host,
  including a Claude Code cloud session. [R-T1]

### 2.10 Boot Order (AArch64 Raspberry Pi)

- The board's EEPROM boot order (`BOOT_ORDER`) must make the **installed
  system boot after installation** without the installer running again,
  while still letting the installer boot on a machine with no installed
  system.
- pre-nixos must **verify** the effective boot order before it installs, and
  must **refuse to install** if the installed system would not be booted.
  [R-B2]

---

## 3. ⚙️ Non-Functional Requirements

- The setup process must be **fully non-interactive** until remote access is available.
- Setup must proceed from **bootable removable media** (e.g., USB stick) with **serial console output**. This includes providing serial access to the **bootloader** and a login prompt on the serial console. The system must still work if a serial console is absent or disconnected. The installed system keeps every serial console the boot image was booted with (`ttyS*`, `ttyAMA*`, …) and the same primary console. [R-C1]
- Each boot image's **primary console** (serial or display) is a build-time choice: most headless machines have only a serial console, and some mini-PCs have none. Defaults: **serial on AArch64**, **display on x86_64**. The installed system keeps the image's primary console (R-C1). [R-C2]
- Setup must be **repeatable**, **deterministic**, and suitable for a **team-managed fleet**, though all installations will be performed by a single operator.

---

## 4. ⛓ Constraints

- **GPT partitioning** only. No DOS/MBR.
- On x86_64, the installed system boots with **UEFI** or **legacy BIOS**, as the installer was booted (§2.3, R-B1, R-B4). AArch64 Raspberry Pi boots as in §2.3. [R-B1]
- **ext4** must be used on all filesystems; other filesystems are out of scope.
- RAID levels are constrained to: **0, 1, 5, 6**.
- LVM must be used to abstract storage volumes except for boot partitions.
- The system must **not require local keyboard or display** access.

---

## 5. 📌 Assumptions

- A machine may have no SSD (see §2.1). [R-S2]
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
