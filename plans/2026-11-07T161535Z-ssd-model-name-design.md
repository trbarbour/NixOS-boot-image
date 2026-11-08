# Disks whose model name contradicts the kernel's "rotational" (design)

_2026-11-07T16:15:35Z. Task queue item 34._

**User report (2026-11-06):** a 128 GB SATA SSD (`G.SKILL 128GB SSD`) was planned as an HDD. The kernel reports `rotational = 1` because the drive reports no rotation rate (`hdparm -I` prints no rotation line).

**User decision (2026-11-06):**
1. "The first should not assume, but it could ask if an apparent HDD has SSD in its name. This will block auto-installation, but it should block in this case."
2. A per-disk SSD/HDD toggle in the TUI. "I don't expect many of these."

**Decisions (user, 2026-11-07):** R-S3 and R-S4 approved; D2 (b), blocking provisioning and auto-install. Implemented in 0.26.0.

## 1. Facts

| # | Fact | Evidence |
|---|---|---|
| F1 | pre-nixos classifies a disk only by `/sys/block/<d>/queue/rotational`. | `inventory.py:52`; `planner.group_by_rotational_and_size` keys `hdd`/`ssd` on `Disk.rotational`. |
| F2 | The kernel reports `rotational = 1` when an ATA drive gives no rotation rate (IDENTIFY word 217 = 0). | The user's drive: `rotational = 1`, no rotation line from `hdparm -I`. |
| F3 | **On blank disks the boot service provisions storage even when auto-install is off.** It passes `--plan-only` only when existing storage is found or detection fails; `PRE_NIXOS_EXEC=1` is always set. | `modules/pre-nixos/service-script.nix` (`plan_flag`); `modules/pre-nixos.nix:34`; `pre_nixos.main` (`will_modify_storage`). |
| F4 | On disks with existing storage the boot run is plan-only, so neither provisioning nor auto-install happens. | Same. This was the user's PC (its disks had `bios_grub` partitions). |
| F5 | The boot run is non-interactive. Its outcomes go to `/run/pre-nixos/storage-status` and `auto-install-status` (`STATE`, `REASON`), the console and the log. | `service-script.nix`; `install._record_result`. |
| F6 | The TUI plans once at start (`tui.run`). It can edit the plan as JSON (`e`), but has no notion of a disk's class. | `tui.py:1241–1327`. |
| F7 | The VM harness can attach SCSI disks with a chosen `rotation_rate` (`tests/vm/scsi_disks.py`). QEMU's `scsi-hd` also takes `product=` (the model name). | `scsi_disks.py:46`. |

Consequence of F3: if only auto-install were blocked, a blank machine with such a drive would still have its disks laid out wrongly at boot. The harm the user wants to avoid (a wrong layout done unattended) comes from the provisioning step, not only from the install.

## 2. Requirements (proposed)

- **R-S3 (new, §2.1):** a non-NVMe disk that the kernel reports as rotational, but whose model name contains "SSD", has an **unconfirmed class**.
  - No unattended run classifies it: the boot service neither provisions storage nor auto-installs while any planned disk's class is unconfirmed (see D2). It reports why, with `REASON=disk-class-unconfirmed`.
  - The user confirms the class in the TUI or on the `pre-nixos` command line.
- **R-S4 (new, §2.1):** the TUI lets the user set any disk's class (SSD or HDD), and re-plans.

## 3. Design debate

### D1. The detection rule
- **(a) The model contains "ssd", case-insensitively, and the kernel says rotational.** Chosen (proposed).
  - Catches `G.SKILL 128GB SSD`, `Samsung SSD 850 EVO` and Intel's `INTEL SSDSC2BB120G4`.
  - Does not catch hybrid drives (`ST1000LM014-1EJ164` with an "SSHD" label; "SSHD" does not contain "SSD"), which are rotational.
  - NVMe is already solid-state (reqs §2.1), so the rule never applies to it.
- **Correction (2026-11-08, #336):** "the model" must be the full ATA model. For SATA disks, sysfs `device/model` is the 16-character SCSI product field (`G.SKILL 128GB SS`), so 0.26.0 never asked on the user's PC. Since 0.26.1 the model comes from `device/vpd_pg89` (ATA IDENTIFY words 27–46) when present. Experiment: `notes/2026-11-08T003000Z-u2-sata-model-truncation.md`.
- **(b) A word match ("SSD" as a whole word):** misses Intel's `SSDSC…` model numbers.
- **(c) Also the reverse case (a non-rotational disk named "HDD"):** not requested, and no such report; left out.

### D2. What an unconfirmed class blocks
- **(a) Auto-install only** (the user's words). Under F3, a blank machine would still be provisioned wrongly at boot.
- **(b) Everything unattended: the boot run's provisioning and the auto-install.** Recommended.
  - The boot run then behaves as if `--plan-only`. It prints the plan and a message naming the disk and how to answer, and records `STATE=plan-only`, `DETAIL=disk-class-unconfirmed` and `AUTO_INSTALL_REASON=disk-class-unconfirmed`.
  - It is the same rule as the BIOS guard (item 33): refuse before any disk is touched.
- Manual runs are not blocked: they must answer first (D3), or they get the same refusal.

### D3. How the question is asked and answered
- **(a) The TUI asks at start**, one dialog per unconfirmed disk: "`sda` (`G.SKILL 128GB SSD`) reports itself as rotating, but its name says SSD. Treat it as [s]SD or [h]DD?". Then it plans with the answers. Chosen.
- **(b) The TUI toggle (R-S4):** a key (`t`) on a focused disk switches SSD↔HDD and re-plans. This also covers any other misreported disk. Chosen.
- **(c) `pre-nixos --ssd sda` / `--hdd sda`:** for command-line runs, including `--plan-only` to preview. Without an answer, a run that would provision refuses (D2). Chosen; it is small, and the CLI is the other manual entry point.
- **(d) A site setting listing disks (by serial) to treat as SSD,** so that auto-install works unattended on such hardware. Deferred: not many such drives are expected, and serial numbers would go in the site file.
- **(e) A kernel command-line option:** rejected; device names are not stable, and boot-menu editing is awkward headless.

### D4. Representation
- `inventory.Disk` keeps the kernel's report (`rotational`), unchanged.
- A new module `disk_class.py`:
  - `DiskClass` (an enum: `SSD`, `HDD`);
  - `unconfirmed(disks) -> list[Disk]` (the D1 rule);
  - `apply_classes(disks, answers: Mapping[str, DiskClass]) -> list[Disk]`, a pure function returning new `Disk` values (`dataclasses.replace`), for the planner;
  - a precondition that every answer names a known disk.
- The planner is unchanged: it plans the disks it is given.
- The plan records the user's answers, as `plan["disk_classes"] = {"sda": "ssd"}`, so the log and the saved plan show why `sda` is in `main`. (Implemented: every answer is recorded, including one that agrees with the kernel, since it records a confirmation.)
- (Implemented) A refused run exits 3 (`pre_nixos.EXIT_NEEDS_ANSWER`). The service script maps that to `STATE=plan-only`, `DETAIL=disk-class-unconfirmed` and succeeds, rather than reading the reason back from a status file. The flake check `boot-service-status` runs the real service script with stub commands for exits 3, 0 and 1.

## 4. Unknowns

| # | Unknown | Experiment |
|---|---|---|
| U1 | Does a QEMU `scsi-hd` with `rotation_rate=0` and `product="TEST SSD"` show `rotational = 1` and model `TEST SSD` in the guest? | Boot the VM with that disk and read sysfs. If so, it is a faithful stand-in for the user's drive. |

## 5. Tests
- **Unit:**
  - the D1 rule on real model strings (`G.SKILL 128GB SSD`, `INTEL SSDSC2BB120G4`, `ST1000LM014-1EJ164`, `QEMU HARDDISK`, an NVMe);
  - `apply_classes` is pure, and rejects an unknown disk name;
  - CLI: with the user's three disks, `--ssd sda` puts `sda` in `main`;
  - CLI: an unanswered unconfirmed disk refuses provisioning and auto-install before `apply_plan`, with `REASON=disk-class-unconfirmed`;
  - TUI: the start-up questions and the toggle re-plan (on the state functions, without curses).
- **VM (U1):** a blank machine with a "TEST SSD" disk reported as rotating. The boot run must not provision, and `storage-status` shows `disk-class-unconfirmed`.

## 6. Work items
1. User: approve R-S3/R-S4, and choose D2 (a) or (b).
2. `disk_class.py`, with its unit tests.
3. CLI: `--ssd`/`--hdd` and the D2 guard. Service script: report the plan-only outcome.
4. TUI: the start-up questions and the toggle.
5. VM test (U1).
6. Docs: reqs §2.1, design, README. Version 0.26.0 (a feature).
