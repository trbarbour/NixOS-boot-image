# Automated Pre‑NixOS Setup — Design (per Design‑Debate Template)

**Doc status:** Draft v0.1  
**Date:** 2025‑08‑31 (America/New_York)  
**Author:** ChatGPT  
**Based on:** `generic‑debate‑design‑prompt‑template.md` → applied to `automated‑pre‑nixos‑setup.md` requirements

---

## 1) Problem Statement (What we must achieve)
Provision bare‑metal servers to a **known, repeatable disk + network baseline** *before* running `nixos-install`. The process must be **non‑interactive until SSH is available** over a **serial‑console‑friendly boot image**, discover heterogeneous storage/NICs, and apply **deterministic RAID + LVM heuristics** with **UEFI + GPT** and **ext4** filesystems (with dense inode options where indicated). NIC with physical link should be identified and **renamed to `lan`**. Outcome: a mounted `/mnt` target with labeled filesystems and a generated NixOS config stub, ready for hand‑off or automated install.

---

## 2) Goals (Success criteria)
- **G1. Non‑interactive boot to SSH:** From power‑on of removable media to an SSH server reachable on the cabled NIC (renamed `lan`), with IP announced on serial console.
- **G2. Deterministic disk layout:** Auto‑discovery builds an explicit **plan** (printed + logged) then applies: GPT, ESP, mdadm arrays, LVM VGs (`main`, `large`), ext4 FS, labels, mount under `/mnt`.
- **G3. Requirements‑compliant storage heuristics:**
  - SSD pair ⇒ **RAID0** by default (or **RAID1** in “careful” mode).
  - Rotational pair ⇒ **RAID1**.
  - Rotational 3–5 ⇒ **RAID5**; rotational ≥6 ⇒ **RAID6**.
  - Prefer **LVM over partitions** for all data (special partitions excepted).
- **G4. UEFI + GPT:** Bootable on modern firmware using systemd‑boot (or GRUB‑UEFI as fallback if required).
- **G5. Ext4 everywhere:** Tuned mount options and **dense inode profile** for paths prone to many small files (e.g., `/nix`).
- **G6. Repeatable & idempotent:** Running twice is safe; decisions are logged; same hardware ⇒ same results.
- **G7. Team‑usable artifacts:** Machine‑readable **plan JSON**, **audit log**, and generated **NixOS config stubs** for later automation.

---

## 3) Non‑Goals
- Full OS provisioning beyond the pre‑install baseline (the final `nixos-install` run may optionally be triggered, but is out of scope for *design guarantees*).
- Advanced crypto (e.g., LUKS), ZFS/btrfs, or multi‑boot support.
- NIC bonding/VLANs or complex network topologies.

---

## 4) Context & Constraints (Reality we must respect)
- **Hardware variety:** EPYC servers, variable SSD/HDD/NVMe counts and sizes; some hosts have only SSDs, others add HDD groups for bulk storage or swap.
- **Boot path:** Removable media → serial console available (e.g., `console=ttyS0,115200n8`), graphics optional.
- **Networking:** One or more NICs; must **identify the cabled NIC** and rename it to `lan` deterministically.
- **Filesystems:** **ext4** required; use **GPT** partitioning; **UEFI** boot; mount **by label**.
- **Preference:** **LVM** over partitions (except ESP and, if needed, BIOS‑GRUB padding).

---

## 5) Definitions
- **ESP:** EFI System Partition (FAT32), default 1 GiB.
- **main / large:** LVM **Volume Groups**. `main` on SSD tier; `large` on rotational tier.
- **Careful mode:** Safety‑biased decisions (e.g., SSD pair as RAID1, `discard` off by default, conservative `mkfs` options).
- **Plan:** The computed, human‑readable + JSON‑serializable description of intended storage and network actions.

---

## 6) Inputs & Configuration Surfaces
1. **Kernel parameters** (read from `/proc/cmdline`):
   - `pre.mode={fast|careful}` (default: `fast`).
   - `pre.autoinstall={0|1}` (default: `0`; if `1`, proceed to `nixos-install` after staging `/mnt`).
   - `pre.host=NAME` (optional, used for labels/hostname).
   - `pre.plan.only={0|1}` (compute/print plan; do not apply).
2. **USB config file** (YAML/TOML at `/pre/config.{yml,toml}` on the boot media):
   - Overrides for RAID level decisions, ESP size, LV sizes, dense‑inode targets, swap policy, etc.
   - SSH public keys path(s) to authorize.
3. **Host fingerprint** (optional) to pin known devices (e.g., by disk serial or NIC MAC) for deterministic naming or explicit overrides.

---

## 7) Discovery & Heuristics (Core logic)
### 7.1 Disk inventory
- Enumerate block devices excluding removable boot media (`/sys/block/*/removable`), CDROMs, and dm‑crypt.
- For each disk: `model`, `size`, `rotational` (from `/sys/block/X/queue/rotational`), `logical/physical` sector size, `serial`, and whether NVMe.
- Group **SSDs** and **HDDs** by `(rotational flag, size within tolerance, type)`; prefer arrays of identical sizes; if mixed, **truncate to min size** for RAIDs.

### 7.2 RAID plan selection
- **SSD group**:
  - If **count ≥2**: default **RAID0**; in `careful` ⇒ **RAID1** (if exactly 2) or **RAID10** (if ≥4 even). If odd and `careful`, prefer RAID1 across two + hot‑spare.
  - If **count =1**: no md, single PV.
- **HDD group**:
  - **2 ⇒ RAID1**.
  - **3–5 ⇒ RAID5**.
  - **≥6 ⇒ RAID6**.
  - Hot spare if count allows (`careful` mode preference).
- Create md arrays with 1 MiB alignment and metadata 1.2; choose `chunk=512K` for SSD RAID0/10; appropriate for ext4/LVM.

### 7.3 Partitioning scheme (GPT)
- On **SSD boot device(s)** (single or md):
  1. **`ESP`** FAT32, 1 GiB, `EF00` GUID, label `ESP`.
  2. **`PV_main`** consuming remainder for LVM PV → `VG main`.
- On **HDD group** (if present): entire md device as single **`PV_large`** → `VG large`.

### 7.4 LVM layout
- **VGs:** `main` (SSD tier), `large` (HDD tier if present).
- **LVs (defaults, configurable):**
  - `main/root` 20 GiB (ext4) — minimal root.
  - `main/nix` 100–200 GiB or `%FREE` if only SSDs present.
  - `main/var` 20–50 GiB (logs/pkg DBs) as needed.
  - **Swap:**
    - If **HDD pair** exists: create `large/swap` with **RAID1** underlying; size from config (e.g., 16–64 GiB).
    - Else: `main/swap` LV.
  - **Bulk storage:** if **HDD group** exists, `large/data` uses remaining; ext4.

### 7.5 Filesystems (ext4)
- **Dense inodes** for `/nix`: `mkfs.ext4 -T news` (or `-i 4096`) to raise inode count; explicit `-L` labels.
- Mount options defaults: `noatime`, `commit=30`. For SSDs, optional `discard=async` (omit in `careful`).
- Labels (examples, adjustable): `ROOT`, `NIX`, `VAR`, `DATA`, `SWAP` — referenced by **LABEL=** in fstab.

### 7.6 UEFI bootloader
- Install **systemd‑boot** into ESP by default. Fallback to GRUB‑UEFI if firmware quirks detected.

### 7.7 NIC identification & rename to `lan`
- Detect interfaces with **carrier=1** via `/sys/class/net/*/carrier`; rank by **speed** (ethtool), then by **PCI order**.
- Select top candidate; create persistent **udev .link** and `.rules` mapping **that NIC’s MAC** to name `lan`.
- Bring `lan` up with DHCP; print **assigned IP** to serial console.

### 7.8 SSH exposure
- Load **authorized_keys** from boot media (`/pre/authorized_keys` or directory), start OpenSSH; disable password auth; announce IP + fingerprint on serial.

### 7.9 Outputs
- `/var/log/pre‑nixos/plan.json` — full machine‑readable plan.
- `/var/log/pre‑nixos/actions.log` — stepwise logs.
- `/mnt/etc/nixos/pre‑generated/` — config snippets:
  - `hardware‑disk.nix` (by‑label mounts, mdadm arrays, LVM VGs/LVs).
  - `network‑lan.nix` (udev rename → `lan`, DHCP on `lan`).
  - `bootloader.nix` (systemd‑boot config).

---

## 8) State Machine / Flow
1. **Early boot:** set serial console, mount boot media read‑only; parse kernel args; import config file if present.
2. **Network stage:** probe carriers; choose NIC; write persistent rename → `lan`; start DHCP; start sshd; print IP to serial.
3. **Discovery:** enumerate disks; compute candidate RAID groups; dry‑run `plan` if `pre.plan.only=1`.
4. **Apply plan:**
   - Confirm boot target (SSD/NVMe); wipe signatures (configurable safety).
   - Partition with `sgdisk`.
   - Create md arrays; wait for sync (background) or `--assume-clean` if blank disks.
   - Create PVs/VGs/LVs; format ext4 with labels; create swap.
5. **Mount target:** `/mnt` tree; generate NixOS config stubs; install bootloader into ESP (if `pre.autoinstall=1`, also run `nixos-install`).
6. **Ready:** leave SSH up; write artifacts; emit summary on serial.

---

## 9) Detailed Algorithms (pseudocode)
```text
function choose_lan():
  candidates = []
  for if in list_interfaces():
    if carrier(if) == 1:
      candidates.append((speed(if), pci_path(if), mac(if), if))
  if empty(candidates): fallback = first_up_or_first()
  else: pick = max(candidates)  # speed then pci order
  write_udev_rules(mac(pick) -> name 'lan')
  ip = dhcp_up('lan')
  print_serial("LAN=lan IP=" + ip)

function plan_storage(mode):
  disks = enumerate_disks()
  groups = group_by_rotational_and_size(disks)
  ssd = groups.ssd; hdd = groups.hdd
  ssd_md = decide_ssd_array(ssd, mode)
  hdd_md = decide_hdd_array(hdd)
  return {ssd_md, hdd_md, partitions, vgs, lvs, fs}

function apply_plan(plan):
  for dev in plan.to_wipe: wipe_signatures(dev)
  for part in plan.gpt: sgdisk_create(part)
  for md in plan.md: mdadm_create(md)
  for pv in plan.pvs: pvcreate(pv)
  for vg in plan.vgs: vgcreate(vg)
  for lv in plan.lvs: lvcreate(lv)
  for fs in plan.fs: mkfs(fs)
  mount_all_by_label(plan)
  gen_nixos_stubs(plan)
```

---

## 10) Idempotency & Safety
- **Dry‑run (`pre.plan.only=1`)** prints plan and exits.
- **Guard rails:** refuse to operate on disks matching “boot media” or USB vendor IDs; require explicit `pre.mode=force` to touch nonempty arrays.
- **Re‑entrancy:** if md/VG/LV exist and match plan, skip creation; verify labels and mounts; regenerate stubs idempotently.

---

## 11) Risks & Mitigations
- **NIC mis‑selection:** multiple live links. *Mitigation:* speed‑first heuristic + optional `pre.lan.mac=` override.
- **Mixed disk sizes in RAID:** capacity loss. *Mitigation:* log truncation; allow override to JBOD via config.
- **UEFI quirks:** some firmware rejects 1 GiB ESP. *Mitigation:* configurable ESP size; GRUB fallback.
- **Ext4 inode pressure in `/nix`:** default insufficient. *Mitigation:* dense inode profile by default for `/nix`.

---

## 12) Alternative Framings (Problem) & Solution Structure
**Framings (problem‑space):**
- *F1.* "Zero‑touch base‑image bring‑up" — treat as appliance: network first, then storage.
- *F2.* "Deterministic storage compiler" — emphasize plan generation & reproducibility; apply step is mechanical.

**Solution structure via Separation of Concerns:**
- **SOC‑1 Network identity** (choose & persist `lan`).
- **SOC‑2 Storage planning** (pure decision engine from inventory → plan).
- **SOC‑3 Storage execution** (idempotent applier).
- **SOC‑4 System hand‑off** (mount + config stubs + optional autoinstall).

---

## 13) Implementation Outline
- **Language:** POSIX shell + small Go/Rust helper for robust discovery (JSON output); or Python 3 if available.
- **Artifacts:**
  - `/usr/local/sbin/pre‑nixos` (entrypoint)
  - `/usr/local/lib/pre‑nixos/plan` (planner)
  - `/usr/local/lib/pre‑nixos/apply` (applier)
  - `/etc/udev/rules.d/90‑lan‑rename.rules` + `.link`
  - `/mnt/etc/nixos/pre‑generated/*.nix`
- **Key commands:** `sgdisk`, `mdadm`, `lvm2` (`pvcreate/vgcreate/lvcreate`), `mkfs.ext4`, `mkswap`, `udevadm`, `ip`, `ethtool`.

---

## 14) Configuration Snippets (generated)
**`hardware‑disk.nix` (sketch):**
```nix
{ ... }:
{
  fileSystems."/" = { device = "LABEL=ROOT"; fsType = "ext4"; options = [ "noatime" ]; };
  fileSystems."/nix" = { device = "LABEL=NIX"; fsType = "ext4"; options = [ "noatime" ]; };
  swapDevices = [ { device = "/dev/disk/by-label/SWAP"; } ];
  boot.loader.systemd-boot.enable = true;
  boot.supportedFilesystems = [ "ext4" ];
}
```

**`network‑lan.nix` (sketch):**
```nix
{ ... }:
{
  networking.usePredictableInterfaceNames = true;
  systemd.network.enable = true;
  networking.interfaces.lan.useDHCP = true;
}
```

---

## 15) Test Plan / Matrix
- **T1:** Single NVMe only → `main` VG, root+nix LVs, DHCP on `lan`.
- **T2:** Two SSDs → RAID0 (fast) / RAID1 (careful) → `main`.
- **T3:** Two HDDs → RAID1 → `large` (swap+data), SSD single for `main`.
- **T4:** Four HDDs → RAID6 (careful) or RAID5 (fast) → `large`.
- **T5:** No cable on any NIC → fallback selection + visible serial warning; user override accepted.
- **T6:** Re‑run on already‑prepared host → no destructive actions; only verification.

---

## 16) Acceptance Criteria
- Booting the image on varied hardware automatically leads to: `lan` with DHCP; SSH reachable with provided keys; `/mnt` has labeled ext4 FS per plan; config stubs exist; serial console shows summary. No prompts before SSH.

---

## 17) Open Questions
- Preferred default sizes for `nix`/`var` LVs on small SSDs?
- Should we always allocate a tiny `/boot` ext4 partition in addition to ESP for kernels, or rely on ESP alone?
- Standardize on systemd‑networkd vs traditional `networking.*` (above sketch assumes either is acceptable).

---

## 18) Next Steps
- Validate discovery on 3–4 hardware profiles; adjust heuristics.
- Implement planner (JSON) and applier; wire into boot image.
- Author end‑to‑end CI scenario using QEMU to verify idempotency and acceptance criteria.

