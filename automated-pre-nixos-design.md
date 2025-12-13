# Automated Pre-NixOS Setup — Design (per Design-Debate Template)

**Doc status:** Draft v0.21
**Date:** 2025-12-13 (UTC)
**Author:** ChatGPT  
**Based on:** `generic-debate-design-prompt-template.md` → applied to `automated-pre-nixos-setup.md` requirements

---

## 1) Problem Statement (What we must achieve)
Provision bare-metal servers to a **known, repeatable disk + network baseline** *before* running `nixos-install`. The process must be **non-interactive until SSH is available** over a **serial-console-friendly boot image**, discover heterogeneous storage/NICs, and apply **deterministic RAID + LVM heuristics** with **UEFI + GPT** and **ext4** filesystems (with dense inode options where indicated). NIC with physical link should be identified and **renamed to `lan`**. Outcome: a mounted `/mnt` target with labeled filesystems and a generated NixOS config stub, ready for hand-off or automated install.

---

## 2) Goals (Success criteria)
- **G1. Non-interactive boot to SSH:** From power-on of removable media to an SSH server reachable on the cabled NIC (renamed `lan`), with IP announced on serial console.
- **G2. Deterministic disk layout:** Auto-discovery builds an explicit **plan** (printed + logged); an operator can apply it via a TUI that displays the current IP address or a diagnostic message to create GPT, ESP, mdadm arrays, LVM VGs (`main`, `swap`, `large`), ext4 FS, labels, mount under `/mnt`.
- **G3. Requirements-compliant storage heuristics:**
  - **Equal-size RAID sets only** (tight tolerance, e.g., ≤1%). Do **not** truncate larger disks to smallest; leave mismatched disks unused unless explicitly configured.
  - SSD pair ⇒ **RAID0** by default (or **RAID1** in “careful” mode).
  - Rotational pair ⇒ **RAID1** (used for swap mirror partitions by default).
  - Rotational 3–5 ⇒ **RAID5** (bulk data tier).
  - Rotational ≥6 ⇒ **RAID6** (bulk data tier).
  - Prefer **LVM over partitions** for all data (special partitions excepted).
- **G4. UEFI + GPT:** Bootable on modern firmware using systemd-boot (or GRUB-UEFI as fallback if required).
- **G5. Ext4 everywhere:** Tuned mount options and **dense inode profile** for paths prone to many small files (e.g., `/nix`).
- **G6. Swap policy (with fallback):**
    - Prefer a dedicated **VG `swap`** backed by **HDD RAID1** (carved from small mirror partitions on two equal-size disks).
    - If **no `swap` VG** is present/possible, create a swap LV on **VG `large`** (rotating-disk only — RAID5/6 or single-HDD PV).
    - If no rotating tier exists, provision swap on the SSD-backed **VG `main`** when there is sufficient free capacity so the SSD swap can serve as a safety net when zram is exhausted. If free space is insufficient, omit swap entirely.
- **G7. Repeatable & idempotent:** Running twice is safe; decisions are logged; same hardware ⇒ same results.
- **G8. Team-usable artifacts:** Machine-readable **plan JSON**, **audit log**, and generated **NixOS config stubs** for later automation.
- **G9. Serial-console resilience:** All serial writes must be **best-effort and non-blocking**. If no serial console is present or if the device blocks writes, scripts must **never hang or fail**. Logging always falls back to journald, `/var/log`, and `dmesg`.

---

## 3) Non-Goals
- Full OS provisioning beyond the pre-install baseline (the final `nixos-install` run may optionally be triggered—and now defaults to running a minimal install when a root key is embedded—but it remains out of scope for *design guarantees*).
- Advanced crypto (e.g., LUKS), ZFS/btrfs, or multi-boot support.
- NIC bonding/VLANs or complex network topologies.

---

## 4) Context & Constraints (Reality we must respect)
- **Hardware variety:** EPYC servers, variable SSD/HDD/NVMe counts and sizes; some hosts have only SSDs, others add HDD groups for swap or bulk storage.
- **Boot path:** Removable media → serial console preferred (e.g., `console=ttyS0,115200n8`), but serial may be **absent or disconnected**. Scripts must not block on serial I/O.
- **Networking:** One or more NICs; must **identify the cabled NIC** and rename it to `lan` deterministically.
- **Filesystems:** **ext4** required; use **GPT** partitioning; **UEFI** boot; mount **by label**.
- **Preference:** **LVM** over partitions (except ESP and, if needed, BIOS-GRUB padding).

---

## 5) Definitions
- **ESP:** EFI System Partition (FAT32), default 1 GiB.
- **main / swap / large:** LVM **Volume Groups**. `main` on SSD tier; `swap` on HDD RAID1 (if present); `large` on HDD RAID5/6 or single-HDD PV (if present). When multiple SSD or HDD buckets exist, only the largest uses the base name (`main`/`large`); smaller buckets receive numeric suffixes (e.g., `main_1`) and are left unmounted.
- **swap (policy):** A dedicated **VG `swap`** on **HDD RAID1** when possible; **fallback** is a swap LV on **VG `large`** (HDD-backed). When no rotating storage is available, use **VG `main`** (SSD/NVMe) if it has enough capacity for the configured swap size; otherwise skip swap entirely.
- **Careful mode:** Safety-biased decisions (e.g., SSD pair as RAID1, `discard` off by default, conservative `mkfs` options).
- **Plan:** The computed, human-readable + JSON-serializable description of intended storage and network actions.

---

## 6) Inputs & Configuration Surfaces
1. **Kernel parameters** (from `/proc/cmdline`):
   - `pre.mode={fast|careful}` (default: `fast`).
   - `pre.autoinstall={0|1}` (default: `0`; if `1`, proceed to `nixos-install` after staging `/mnt`).
   - `pre.host=NAME` (optional, used for labels/hostname).
   - `pre.plan.only={0|1}` (compute/print plan; do not apply).
2. **USB config file** (YAML/TOML at `/pre/config.{yml,toml}` on the boot media):
   - Overrides for RAID level decisions, ESP size, LV sizes, dense-inode targets, swap policy, etc.
   - SSH public keys path(s) to authorize.
3. **Host fingerprint** (optional) to pin known devices (e.g., by disk serial or NIC MAC) for deterministic naming or explicit overrides.

---

## 7) Discovery & Heuristics (Core logic)
### 7.1 Disk inventory
- Enumerate block devices excluding removable boot media (`/sys/block/*/removable`), CDROMs, and dm-crypt devices.
- For each disk: gather `model`, `size`, `rotational` (from `/sys/block/X/queue/rotational`), `logical/physical sector size`, `serial`, and whether NVMe.
- Group disks into **SSDs** and **HDDs**, then bucket them by approximate size (≤1% tolerance).
- **Equal-size requirement:** Only disks in the same bucket form a RAID set. Larger disks are not truncated down; outliers are excluded unless explicitly overridden.

### 7.2 RAID plan selection
- **SSD group (per size bucket):**
  - If **count ≥2**: default **RAID0**; in `careful` mode ⇒ **RAID1** (if exactly 2) or **RAID10** (if ≥4 even). If odd and `careful`, prefer RAID1 across two + hot-spare; leave extras unused.
  - If **count =1**: no md, single PV for `main`.
  - **Naming:** the size bucket with the greatest total capacity becomes **VG `main`**; additional SSD buckets are named `main_1`, `main_2`, … and are left unmounted.
  - **Default tier:** SSD capacity drives `main`; when no rotating storage exists, `main` may also host the fallback swap LV if sufficient space remains after primary allocations.
- **HDD group (per size bucket):**
  - **Swap mirror first:** If **≥2** present, allocate **two equal-size disks** for a small **RAID1** md device dedicated to swap (capacity sized per config; defaults 2 x RAM). This device becomes **VG `swap`** (LV `swap`). Remaining capacity on those disks still contributes to data.
  - **Data array next:** With remaining disks, choose level: **2 ⇒ RAID1**, **3–5 ⇒ RAID5**, **≥6 ⇒ RAID6**. This md becomes PV for **VG `large`**.
  - **Naming:** the largest HDD bucket forms **VG `large`**; additional buckets are named `large_1`, `large_2`, … and remain unused.
  - **Fallbacks:** If insufficient HDDs for a swap mirror, create VG `large` from available HDDs and put the swap LV there. With no rotating tier available, place the swap LV on `main` provided it can accommodate the configured size; otherwise skip swap.

### 7.3 Partitioning scheme (GPT)
- **Per-disk layout:** every participating disk receives a GPT with a single data partition sized to the available capacity. When the disk underpins VG `main`, an additional 1 GiB EFI System Partition (label `ESP`, FAT32) is created before the data slice.
- **Partition types:** data partitions destined for md arrays are flagged `linux-raid`; others are marked `lvm`. The final partition on each disk feeds either a RAID array or an LVM PV directly.
- **Fallbacks:** if no rotating mirror exists for swap, the HDD capacity is assigned to VG `large` and swap falls back to that VG; with no rotating tier, swap may be placed on `main` when free space permits.

### 7.4 LVM layout
- **VGs:** `main`, `swap` (if present), `large` (if present). Additional SSD/HDD buckets are created as `main_1`, `large_1`, etc., and left without logical volumes.
- **LVs:**
  - `main/slash` sized at a fixed 50 GiB for the root filesystem.
  - `main/home`, created when `main` has free space, mounted on `/home` and sized to **16 GiB or one quarter of the remaining space**, whichever is smaller and extent-aligned.
  - Swap: `swap/swap` on VG `swap`; fallback hierarchy: `large/swap` on VG `large`, else `main/swap` on VG `main` when capacity permits.
  - When the dedicated `swap` VG still has extents free after provisioning swap, it also hosts:
    - `swap/var_tmp`, default size equal to the swap LV.
    - `swap/var_log`, default size 4 GiB or the swap LV size, whichever is smaller.
  - Bulk: `large/data` receives 100 GiB by default when a `large` VG exists.
- **Extent safety margin:** allocations avoid consuming the final one or two extents of a VG so follow-up provisioning remains possible.

### 7.5 Filesystems (ext4)
- Mount options: `relatime`. For SSDs, optional `discard=async`. `/var/tmp` inherits the default ext4 mount and is fixed to mode `1777` via a post-apply command.

### 7.6 UEFI bootloader
- Install **systemd-boot** into ESP by default. Fallback to GRUB-UEFI if firmware quirks detected.

### 7.7 NIC identification & rename to `lan`
- Detect interfaces with carrier=1 via `/sys/class/net/*/carrier`.
- Rank by **speed** (ethtool), then PCI order.
- Select top candidate; persist rename to `lan` via udev/systemd.
- Bring `lan` up with DHCP; log assigned IP.

### 7.8 SSH exposure
- Install built-in `authorized_keys` for root and harden `sshd_config` to disable password logins while preserving the root password for console access.
- The OpenSSH service remains disabled during boot and is started only after this hardening step.
- Announce IP + fingerprint via log fan-out.

### 7.9 Outputs
- `/var/log/pre‑nixos/plan.json` — full machine‑readable plan.
- `/var/log/pre‑nixos/disko-config.nix` — declarative layout for the disko CLI (generated from the plan's `disko.devices`).
- `/var/log/pre‑nixos/actions.log` — stepwise logs.
- `/mnt/etc/nixos/pre‑generated/` — config snippets:
  - `hardware‑disk.nix` (by‑label mounts, mdadm arrays, LVM VGs/LVs).
  - `network‑lan.nix` (udev rename → `lan`, DHCP on `lan`).
  - `bootloader.nix` (systemd‑boot config).
- Optional `post_apply_commands` list to capture follow-up shell commands (e.g., `chmod 1777 /mnt/var/tmp`) executed immediately after Disko completes.

### 7.10 Disko orchestration
- The planner promotes its internal partition/array/VG/LV graph into a `disko.devices` attrset. Physical disks become `disk.<name>` entries with GPT partitions; EFI partitions gain FAT32 filesystems and only the primary ESP is mounted at `/boot`.
- RAID sets map to `mdadm.<name>` with integer `level` values and `content = { type = "lvm_pv"; vg = "…"; }` so Disko turns arrays directly into PVs. Single devices stay as `lvm_pv` content on their partitions.
- LVM volume groups surface as `lvm_vg.<name>.lvs`. Logical volumes render as either `filesystem` (ext4, `relatime`, mountpoints such as `/`, `/home`, `/var/tmp`, `/var/log`, and `/data`) or `swap` content. This mirrors today's manual mkfs/mkswap labelling policy.
- After Disko runs, the applier iterates over any `post_apply_commands` and executes them in order, logging each invocation.
- The applier serialises the structure via `builtins.fromJSON` to keep the config legible, then shells out to Disko to execute the destroy/format/mount pipeline in one idempotent step.
- **Storage erasure + metadata handling:** The pre-confirmation storage cleanup now builds a single global graph from `lsblk` (plus `pvs/vgs/lvs` and `losetup`) so shared stacks (md/LVM/loops) are handled once. It walks the reachable forest **leaf-to-root**, unmounting/swapoff → LV deactivate → VG deactivate → md stop → dm/crypt/loop detach, and then **destroys LVM metadata** (`lvremove -fy`, `vgremove -ff -y`, `pvremove -ff -y`), **md metadata** (`mdadm --zero-superblock`), and remaining signatures (`wipefs`). Root devices then receive GPT zap + reread + optional discard/shred + final `wipefs`. Partition refresh failures and wipefs errors capture diagnostics for RCA instead of silently skipping work.

---

## 8) State Machine / Flow
1. **Early boot:**
   - GRUB and the kernel are configured with `console=ttyS0,115200n8 console=tty0` so serial output is available with a local fallback.
   - Parse kernel args; detect available consoles from `/proc/consoles` and `/proc/cmdline`.
   - Start a `getty` on the primary serial console to allow logins.
   - Establish **non-blocking log fan-out**: log to journald, append to `/var/log/pre-nixos/actions.log`, send to `dmesg`, and write to the kernel console (e.g., `printf ... > /dev/console` with timeouts).
   - If no serial console is present/connected, skip console writes silently; never fail the step on serial errors.
   - Mount boot media read-only; import config file if present.
2. **Network stage:** probe carriers; choose NIC; write persistent rename → `lan`; start DHCP; if a root key is present, run `secure_ssh` to harden configuration and start `sshd`; otherwise leave `sshd` disabled; print IP via logging fan-out (serial best-effort/time-bounded).
3. **Discovery:** enumerate disks; compute candidate RAID groups, and write a plan without modifying any disks.
4. **Apply plan (manual):**
   - After operator review (e.g., via `pre-nixos-tui`, which shows the current IP or a status message), confirm boot target (SSD/NVMe) and acknowledge the wipe gate.
   - The planner's `disko.devices` map is rendered to `/var/log/pre-nixos/disko-config.nix` using `builtins.fromJSON` so humans can audit the intended layout.
   - `pre-nixos` probes `disko --help` to decide between the legacy `--mode disko` path and the newer combined `--mode destroy,format,mount` invocation (adding `--yes-wipe-all-disks` only when supported) before running the command against `/var/log/pre-nixos/disko-config.nix`. Disko orchestrates GPT creation, mdadm arrays, LVM VGs/LVs, filesystem formatting, swap provisioning, and mounts everything relative to `/mnt`.
   - Disko's stdout/stderr are streamed through the usual log fan-out; failures bubble up as a single error surface.
5. **Mount target:** `/mnt` tree; generate NixOS config stubs; install bootloader into ESP (if `pre.autoinstall=1`, also run `nixos-install`).
6. **Ready:** leave SSH up; write artifacts; emit summary through log fan-out (serial best-effort/time-bounded).

---

## 9) Detailed Algorithms (pseudocode)
```text
function choose_lan():
  candidates = []
  for if in list_interfaces():
    if carrier(if) == 1:
      candidates.append((speed(if), pci_path(if), mac(if), if))
  if not candidates:
    pick = first_available()
  else:
    pick = max(candidates)  # by speed, then pci order
  write_udev_rules(mac(pick) -> name 'lan')
  ip = dhcp_up('lan')
  print_log("LAN=lan IP=" + ip)

function plan_storage(mode):
  disks = enumerate_disks()
  groups = group_by_rotational_and_size(disks)
  ssd_md = decide_ssd_array(groups.ssd, mode)
  hdd_md = decide_hdd_array(groups.hdd)
  plan = {ssd_md, hdd_md, partitions, vgs, lvs}
  plan.disko = plan_to_disko_devices(plan)
  return plan

function apply_plan(plan):
  cfg_path = "/var/log/pre-nixos/disko-config.nix"
  write_file(cfg_path, render_disko(plan.disko))
  mode, can_wipe = detect_disko_mode()
  cmd = ["disko", "--mode", mode, "--root-mountpoint", "/mnt", cfg_path]
  if can_wipe and mode == "destroy,format,mount":
    cmd.insert(3, "--yes-wipe-all-disks")
  run(" ".join(cmd))
  gen_nixos_stubs(plan)
```

---

## 10) Idempotency & Safety
- **Dry‑run (`pre.plan.only=1`)** prints plan and exits.
- **Guard rails:** refuse to operate on disks matching “boot media” or USB vendor IDs; require explicit `pre.mode=force` to touch nonempty arrays; serial I/O always non-blocking.
- **Re‑entrancy:** if md/VG/LV exist and match plan, skip creation; verify labels and mounts; regenerate stubs idempotently.

---

## 11) Risks & Mitigations
- **NIC mis‑selection:** multiple live links. *Mitigation:* speed‑first heuristic + optional `pre.lan.mac=` override.
- **Mixed disk sizes:** arrays only with equal-size disks.
- **No HDDs:** swap falls back to SSD (VG `main`) if capacity allows; otherwise swap is omitted.
- **UEFI quirks:** some firmware rejects 1 GiB ESP. *Mitigation:* configurable ESP size; GRUB fallback.
- **Serial issues:**  all serial writes wrapped in timeouts and error-ignored; logging always has alternative sinks (journald/file/dmesg).

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
- **Key commands:** `disko` (destroy/format/mount), `udevadm`, `ip`, `ethtool`.

### TUI visualisation & interaction

- **Data sources:**
  - `planned` lane renders straight from the planner output (current behaviour) so the operator sees the intended end state.
  - `existing` lane is populated by extending `inventory` with a `describe_existing_layout()` helper that walks `lsblk`, `mdadm --detail`, and `lvs` to build the same disk→array→VG→LV hierarchy for already-present storage. When no layout exists the view collapses to “(no recognised storage)” so the toggle remains usable on blank hosts.
  - Both snapshots share a normalised schema (disks, partitions, arrays, VGs, LVs) so the UI can diff them cheaply and highlight mismatches.
- **Screen anatomy:** retain the top status bar (`IP: <value>` or diagnostic) and bottom action strip, and insert a two-line legend just under the header with glyph/colour hints (■ SSD, ● HDD, ☐ EFI, ≡ RAID, underline = live device).
- **Four-column canvas:** centre of the screen shows a left-to-right flow — `Disks/Partitions → md arrays → VGs → LVs`. Each disk row nests partition blocks like `[☐ EFI][■ nvme0n1p2]`; md boxes sit in the second column with connectors (`┐┴┘`) leading to their source partitions; VGs and LVs indent accordingly. This matches the textual sketch shared during design debate and keeps relationships obvious even without vertical pipes.
- **Adaptive density & layout probe:**
  - Each refresh runs the layout engine once off-screen to discover the bounding box (required width and height) for the current dataset and focus state. The renderer picks the richest profile that fits inside the live `curses.getmaxyx()` result, so the decision accounts for both terminal size and how much storage hierarchy needs to be drawn.
  - Profiles degrade progressively: **detailed** renders per-partition blocks and every LV row; **compact** collapses partitions into single-segment summaries and abbreviates LV metadata; **minimal** collapses non-focused subtrees into counts ("VG main → 3 LVs"). The dry-run buffer is reused for the final paint to avoid duplicate work.
  - If even the minimal profile would overflow, the view automatically elides the lowest-priority rows (e.g., non-focused offline disks) and surfaces a status hint so the operator knows detail was suppressed. Manual resizing triggers a re-probe, letting detail reappear when space allows.
- **Existing vs planned toggle:**
  - `Tab` (or `v`) switches between `Existing` and `Planned` snapshots; the header shows the active state (`View: Planned` / `View: Existing`).
  - When a component differs between states (e.g., md level mismatch, missing LV, stale partition), the planned view annotates it with a right-margin badge (`← missing on disk`, `← level differs`). The existing view shades non-planned components dimly so the operator can spot cruft before applying.
  - The toggle preserves the current focus anchor and any enforced zoom on that branch so operators can compare the same subtree across states even on constrained consoles.
- **Focus, pan, and zoom:** arrow keys move a focus cursor and pan the canvas to keep the focused row visible; `Enter` toggles expansion of that subtree. Pressing `z` zooms relative to the focus by forcing the detailed profile for the focused branch (and its ancestors) or returning it to the automatic profile, so operators zoom on top of the current pan position instead of flipping the entire screen at once.
- **Action integration:** existing hotkeys remain (`E` edit plan, `S` save, `L` load, `A` apply, `Q` quit). Apply always works on the planned snapshot; attempting to apply while the existing view reveals blockers (e.g., foreign md arrays) prompts the operator to wipe/resolve them first.
- **Colour/signalling:** degrade states (md arrays rebuilding, missing members) inherited from inventory are rendered in yellow/red. Planned-only items render in cyan so operators can tell they do not yet exist. When the plan matches reality the two views converge, reinforcing idempotency.
- **Reference mocks:** Concrete ASCII frames for detailed, compact, and minimal layouts live under `docs/tui-mockups/`. They cover mixed-tier plans, 80×24 minimal rendering, and existing-vs-planned toggles with mismatch cues, giving implementers copy-ready targets.

---

## 14) Configuration Snippets (generated)
**`hardware‑disk.nix` (sketch):**
```nix
{ ... }:
{
  fileSystems."/" = { device = "LABEL=slash"; fsType = "ext4"; options = [ "relatime" ]; };
  fileSystems."/home" = { device = "LABEL=home"; fsType = "ext4"; options = [ "relatime" ]; };
  fileSystems."/var/log" = { device = "LABEL=var_log"; fsType = "ext4"; options = [ "relatime" ]; };
  fileSystems."/var/tmp" = { device = "LABEL=var_tmp"; fsType = "ext4"; options = [ "relatime" ]; };
  fileSystems."/data" = { device = "LABEL=data"; fsType = "ext4"; options = [ "relatime" ]; };
  swapDevices = [ { device = "/dev/disk/by-label/swap"; } ];
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
- T1: NVMe only → `main`; swap LV on `main` if capacity meets configured size, otherwise omit.
- T2: Two same size SSDs → RAID0/1; swap LV on `main` if capacity meets configured size, otherwise omit.
- T3: Two same size HDDs + SSD → HDD RAID1 → VG `swap`; SSD → `main`.
- T4: Four same size HDDs + SSD → HDD RAID6 → `large`; SSD → `main`.
- T5: Four same size HDDs + two smaller (like-size) HDDs + SSD → HDD RAID6 → `large`; HDD RAID1 → `swap`; SSD → `main`.
- T6: Heterogeneous HDD sizes → only disks in the same size bucket are assembled; others left unused. Verify planner refuses mixed-size arrays.
- T7: Re-run → no destructive actions.
- T8: No NIC cable → fallback + log warning.
- T9: No serial console present or disconnected/blocked serial device → all steps complete without hang; logs present in journald and file; serial emits skipped or time-bounded.

---

## 16) Acceptance Criteria
- On supported hardware, booting the image automatically yields: lan with DHCP; SSH reachable with provided keys; /mnt has labeled ext4 FS per plan; swap provided when a rotating tier exists (VG `swap` preferred, fallback `large/swap`) or, if only SSD/NVMe are available and capacity allows, via `main/swap`; config stubs exist; serial console shows summary. No prompts before SSH.
- Serial-safe: absence of a serial console or a disconnected/blocked tty never causes a hang or failure; messages still reach journald and the action log.

---

## 17) Open Questions [answered]
- Need separate `/boot` ext4 partition? [no]
- Standardize on systemd-networkd? [yes]

---

## 18) Next Steps
- Validate planner on diverse hardware configurations (single SSD, SSD+HDD pairs, larger HDD farms).
- Implement reference plan generator (Go or Python).
- Implement apply with dry-run support and idempotency checks.
- Add CI integration with QEMU/KVM to validate on virtual hardware.
