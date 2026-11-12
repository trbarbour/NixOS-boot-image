# Task queue archive

Closed task-queue items, kept verbatim with their full history when they leave `docs/task-queue.md`. Each section says when and why it was closed; the reason is also in the queue's Recently Completed list.

## Closed by the queue audit of 2026-11-12

1. **Harden BootImageVM diagnostics.**
   - Keep improving the login helper so root escalation transcripts and serial output are captured automatically on failure.
   - Collect `journalctl -u pre-nixos.service -b` and `systemctl status pre-nixos` whenever provisioning or DHCP waits time out, and emit ISO metadata (store path, hash, root key fingerprint) in logs.
   - 2025-10-24T03-23-43Z session emits a structured metadata block at harness startup and mirrors it in assertion failures for provenance tracking.【F:docs/work-notes/2025-10-24T03-23-43Z-boot-image-vm-metadata-log.md†L1-L15】【F:tests/test_boot_image_vm.py†L273-L343】
   - 2025-10-24T03-50-00Z harness sessions now persist their metadata to `metadata.json`, and manual debug utilities reuse the same structure when exporting artefacts.【F:tests/test_boot_image_vm.py†L249-L395】【F:scripts/manual_vm_debug.py†L19-L218】【F:scripts/collect_sshd_dependency_audit.py†L18-L216】【F:scripts/collect_sshd_pre_nixos_debug.py†L183-L305】
   - 2025-10-24T04-30-00Z timeout handlers persist captured systemd and journal output as diagnostic artefacts and manual exports copy the diagnostics directory for postmortem analysis.【F:docs/work-notes/2025-10-24T04-30-00Z-boot-image-diagnostic-artifacts.md†L1-L18】【F:tests/test_boot_image_vm.py†L715-L833】【F:scripts/collect_sshd_pre_nixos_debug.py†L279-L312】
   - 2025-10-24T05-45-00Z metadata now catalogues every diagnostic artifact and timeout handlers collect `lsblk`, `networkctl status`, and `systemctl list-jobs` outputs for richer postmortems.【F:docs/work-notes/2025-10-24T05-45-00Z-boot-image-diagnostic-artifact-catalog.md†L1-L18】【F:tests/test_boot_image_vm.py†L249-L381】【F:tests/test_boot_image_metadata.py†L1-L76】
   - 2025-10-24T06-30-00Z root escalation failures now emit dedicated transcript diagnostics recorded in `metadata.json` and included in assertion output for postmortem triage.【F:docs/work-notes/2025-10-24T06-30-00Z-boot-image-escalation-transcript-diagnostics.md†L1-L16】【F:tests/test_boot_image_vm.py†L360-L706】【F:tests/test_boot_image_vm.py†L1122-L1204】
   - 2025-10-26T21-06-03Z SSH retry exhaustion now captures `systemctl status sshd` and `journalctl -u sshd.service -b` alongside host stdout/stderr diagnostics, and the unit test asserts the new artifacts surface in metadata and assertion messages.【F:docs/work-notes/2025-10-26T21-06-03Z-boot-image-ssh-diagnostics.md†L1-L16】【F:tests/test_boot_image_vm.py†L1068-L1211】
   - 2025-10-27T02-30-00Z unexpected `pexpect` EOFs now trigger the same structured diagnostics as other harness failures and a unit test verifies login transcripts are recorded in metadata.【F:docs/work-notes/2025-10-27T02-30-00Z-boot-image-eof-diagnostics.md†L1-L17】【F:tests/test_boot_image_vm.py†L520-L611】【F:tests/test_boot_image_vm.py†L1225-L1303】
   - 2025-10-27T04-00-00Z abrupt QEMU exits now capture exit status diagnostics that are logged, catalogued in `metadata.json`, and asserted by the EOF regression test.【F:docs/work-notes/2025-10-27T04-00-00Z-boot-image-qemu-exit-diagnostics.md†L1-L14】【F:tests/test_boot_image_vm.py†L417-L470】【F:tests/test_boot_image_vm.py†L1373-L1439】
   - 2025-10-27T13-04-29Z storage and IPv4 timeouts now record `systemctl list-jobs` outputs alongside existing diagnostics so metadata and failure messages surface the active job queue.【F:docs/work-notes/2025-10-27T13-04-29Z-boot-image-systemd-jobs-diagnostics.md†L1-L14】【F:tests/test_boot_image_vm.py†L1051-L1183】
   - 2025-10-27T13-39-46Z IPv4 timeouts additionally capture `systemctl status systemd-networkd` and its journal so diagnostics catalogue the service state when DHCP waits fail.【F:docs/work-notes/2025-10-27T13-39-46Z-boot-image-networkd-diagnostics.md†L1-L13】【F:tests/test_boot_image_vm.py†L1148-L1187】【F:tests/test_boot_image_vm.py†L2044-L2193】
   - 2025-10-27T23-08-26Z IPv4 timeouts now snapshot `ip addr show dev <iface>` and `ip route show dev <iface>` outputs so diagnostics catalogue link configuration alongside systemd state.【F:docs/work-notes/2025-10-27T23-08-26Z-boot-image-ip-diagnostics.md†L1-L18】【F:tests/test_boot_image_vm.py†L1136-L1188】【F:tests/test_boot_image_vm.py†L2044-L2209】
   - 2025-10-28T01-15-00Z metadata capture now records the QEMU version and `_raise_with_transcript` includes it in failure messages, ensuring provenance for host-specific regressions.【F:docs/work-notes/2025-10-28T01-15-00Z-boot-image-qemu-version-diagnostics.md†L1-L17】【F:tests/test_boot_image_vm.py†L240-L305】【F:tests/test_boot_image_vm.py†L1405-L1459】【F:tests/test_boot_image_metadata.py†L24-L56】
   - 2025-10-28T12-44-37Z IPv4 timeouts now capture `ip -s link show dev <iface>` output so link statistics accompany address and routing diagnostics in both metadata and assertion messages.【F:docs/work-notes/2025-10-28T12-44-37Z-boot-image-ip-link-diagnostics.md†L1-L15】【F:tests/test_boot_image_vm.py†L1161-L1199】【F:tests/test_boot_image_vm.py†L2184-L2251】
   - 2025-10-29T19-20-22Z storage and IPv4 timeouts now snapshot `systemctl list-units --failed --no-legend` alongside job queues so metadata and failure messages surface failed services during triage.【F:docs/work-notes/2025-10-29T19-20-22Z-boot-image-failed-units-diagnostics.md†L1-L18】【F:tests/test_boot_image_vm.py†L1096-L1249】【F:tests/test_boot_image_vm.py†L1969-L2251】
   - 2025-10-29T19-55-52Z unit inactivity timeouts now snapshot `systemctl list-units --failed --no-legend` alongside job queues so metadata and failure messages surface failed services when waiting for units to stop.【F:docs/work-notes/2025-10-29T19-55-52Z-boot-image-unit-inactive-diagnostics.md†L1-L15】【F:tests/test_boot_image_vm.py†L1278-L1389】【F:tests/test_boot_image_vm.py†L2252-L2359】
   - 2025-10-29T20-25-29Z storage, IPv4, and unit inactivity timeouts now capture the kernel ring buffer via `dmesg`, logging and cataloguing the artifacts alongside existing diagnostics.【F:docs/work-notes/2025-10-29T20-25-29Z-boot-image-dmesg-diagnostics.md†L1-L9】【F:tests/test_boot_image_vm.py†L1137-L1389】【F:tests/test_boot_image_vm.py†L2102-L2567】
   - 2025-10-29T20-45-20Z storage timeouts archive `/run/pre-nixos/storage-status` snapshots as labelled diagnostics and surface the contents in failure messages for faster triage.【F:docs/work-notes/2025-10-29T20-45-20Z-boot-image-storage-status-diagnostics.md†L1-L16】【F:tests/test_boot_image_vm.py†L1080-L1159】【F:tests/test_boot_image_vm.py†L2036-L2177】
  - 2025-10-27T04-21-49Z BootImageVM failure metadata now lists the disk image and shell-quoted QEMU command so provenance survives outside `metadata.json`, with regression coverage guarding the new lines.【F:docs/work-notes/2025-10-27T04-21-49Z-boot-image-qemu-command-diagnostics.md†L1-L18】【F:tests/test_boot_image_vm.py†L368-L428】【F:tests/test_boot_image_vm.py†L1870-L1914】【F:tests/test_boot_image_vm.py†L1512-L1538】
   - 2025-10-09T15-30-00Z improvements laid the groundwork; continue iterating as new edge cases appear. 【F:docs/work-notes/2025-10-09T15-30-00Z-boot-image-vm-test-attempt.md†L1-L42】
   - 2025-10-24T03-00-00Z updates capture serial tails and systemd diagnostics in the harness log when timeouts occur. 【F:docs/work-notes/2025-10-24T03-00-00Z-boot-image-vm-diagnostics.md†L1-L17】【F:tests/test_boot_image_vm.py†L286-L341】【F:tests/test_boot_image_vm.py†L599-L675】

2. **Rebuild the boot image with future network/storage tweaks and rerun the VM regression.**
   - Use the now-working dev shell workflow to produce new ISOs whenever changes land, then run `pytest tests/test_boot_image_vm.py -vv` without interruption to validate end-to-end behaviour.
   - Promote passing serial/journal logs to `docs/boot-logs/` with updated test reports.
   - 2025-10-29T21-32-03Z - Rebuilt the ISO and reran the full regression suite; see `docs/work-notes/2025-10-29T21-32-03Z-boot-image-vm-regression.md` and `docs/test-reports/2025-10-29T21-32-03Z-boot-image-vm-test.md` for command output and results.【F:docs/work-notes/2025-10-29T21-32-03Z-boot-image-vm-regression.md†L1-L7】【F:docs/test-reports/2025-10-29T21-32-03Z-boot-image-vm-test.md†L1-L15】

3. **Capture follow-up boot timings after configuration adjustments.**
    - With the harness stable, collect new timing data after each substantive change to detect regressions early.
    - 2026-04-25T19-35-35Z - Root-cause review replaced the broad early-DHCP approach with a targeted networkd refresh fast-path (`networkctl reload` + `networkctl reconfigure lan`) and retained restart fallback; next VM timing pass should measure improvement without overriding static/rename workflows. See `docs/work-notes/2026-04-25T19-35-35Z-network-init-delay-root-cause.md`.

4. **Ensure the full test suite runs without skips.**
    - Audit pytest skips and prerequisites so the VM suite remains active, and maintain CI coverage for the entire suite.
    - 2026-10-18T02-53-00Z - In a Claude Code cloud session the full suite ran with no skips: `236 passed` in 17m14s, VM tests included, under TCG. See `notes/2026-10-18T025300Z-vm-run.md`. CI coverage is still outstanding.

5. **Add unit coverage for the TUI plan editor.**
   - Drive `pre_nixos.tui._edit_plan` via a fake window with scripted inputs for arrays and LVs, including invalid input handling.
   - 2026-04-25T17-43-55Z - Added a regression that verifies LV edits in `_edit_plan` also refresh the derived `plan["disko"]` structure used by `apply`, preventing stale LV sizes from being provisioned.

9. **Plan AArch64 support (Raspberry Pi CM4 microSD boot image).** *(user request, 2026-10-18T04-35-00Z)*
   - Goal: build an AArch64 boot image that can be written to a microSD card to boot e.g. a CM4. Use the stock NixOS AArch64 SD image as the base; it works, including on the serial console.
   - Deliverable: a top-down plan from requirements, with a design debate for each choice and a list of unknowns, each with an experiment to resolve it. Start after the race-fix PR.
   - 2026-10-18T14-21-35Z - Plan written: `plans/2026-10-18T142135Z-aarch64-cm4-boot-image-plan.md`.
     - E1 (module evaluates on the stock SD image), E2 (this host builds AArch64 via binfmt) and E3 (only 44 derivations built locally) are done.
     - Found a safety gap: the SD boot card is not excluded from storage plans (§3.1).
     - Its §3.1 (boot-medium protection) is now done via #306, #308 and #309.
   - 2026-10-18T22-03-51Z - User answers received and recorded (plan §8; verbatim copy `plans/2026-10-18T220351Z-aarch64-user-answers.txt`).
     - Requirements §2 approved and applied to `automated-pre-nixos-reqs.md` (R-IDs).
     - Install target: NVMe. Refusing to install on a wrong `BOOT_ORDER` is acceptable.
     - **Next:** implement work items 3 to 9 of the plan in order (not started).
   - 2026-10-19:
     - Items 3 to 8 are done and merged in trbarbour/NixOS-boot-image#315 (0.18.1, 2026-10-20 03:08Z).
     - 2026-10-20/21:
       - E9b to E9b-4 on the CM4 (#316, closed): U-Boot moved to v2026.10, plus a local patch for NVMe read/write DMA translation, which is verified on hardware.
       - Item 9 (the `BOOT_ORDER` check, 0.19.0) is done.
       - VM tests at 0.19.1: the full regression had 11 passed and 1 stale test, which was fixed. The AArch64 module then passed 4/4.
     - **Next:** item 10, hardware acceptance on the CM4 (the user).
       - 2026-10-21: the first attempt used an image built without a root key, so `end0` was not renamed and SSH failed. That is designed behaviour: `configure_lan` skips when no key is embedded (user confirmed). The user's NVMe holds a Windows GPT, so auto-provisioning will not run (reqs §2.3) unless the user wipes it.
       - 2026-10-22: attempt 1 with 0.20.0 and a site key (`docs/test-reports/2026-10-22T025029Z-cm4-item10-acceptance-1.md`).
         - Worked: LAN renamed with DHCP, the BOOT_ORDER check passed, disko provisioned the NVMe.
         - Failed: `nixos-install` stopped on a duplicate `boot.loader.grub.enable` (#320).
         - Fixed in 0.20.1: the Pi loader is now a separate module with `mkForce`, tested against real `nixos-generate-config` output.
         - **Next:** the user rebuilds from 0.20.1, wipes the NVMe, and repeats the test.
       - 2026-10-22: attempt 2 with 0.21.0 (`docs/test-reports/2026-10-22T154500Z-cm4-item10-acceptance-2.md`).
         - Worked: the install, then firmware → U-Boot 2026.10 → extlinux from NVMe, as far as `Starting kernel ...`.
         - Failed:
           - the installed initrd lacks `pcie-brcmstb`, so the system hung with no serial output and no DHCP (#323);
           - the installer's sshd waited for the whole auto-install (#324).
         - Both fixed in 0.21.1.
         - **Next:** the user rebuilds 0.21.1, wipes the NVMe, and retests. Open question: make serial the installed Pi's primary console?
       - 2026-10-23 (user decision): the primary console is a site setting (`primaryConsole`), serial by default on AArch64 and display on x86. It applies to the image and is inherited by the installed system. Implemented in 0.22.0 (`plans/2026-10-23T022949Z-primary-console-design.md`).
       - 2026-10-23: attempt 3 with 0.22.0 (`docs/test-reports/2026-10-23T142031Z-cm4-item10-acceptance-3.md`).
         - The installed system boots from NVMe with serial login and SSH. #323 and #324 are confirmed on hardware, and serial primary works.
         - Failed: `lan` holds two DHCP leases, because NetworkManager runs beside networkd (#326). Also, each broadcast appears twice on serial (#327).
         - Both fixed in 0.22.1.
         - **Next:** the user rebuilds 0.22.1 and retests. Expected: one lease, single broadcasts.

10. **Stop old boot-image builds from filling the disk.** *(anomaly, 2026-10-18T22-31-37Z)*
    - The first 26.05 VM regression failed before any test ran. The ISO build stopped in xorriso with `Image size 716672s exceeds free space on media 441800s`, because the session's disk allowance was spent.
    - Cause: 15 unrooted 25.05 ISOs at 1.4 GiB each were left in `/nix/store` by earlier builds. Deleting them freed 20.1 GiB.
    - Plan: a helper that deletes boot-image store paths other than the current one, called from the VM fixture's build step (or the session hook) when free space is low. Record the disk headroom in the run metadata so this shows up early.
    - 2026-10-19 - It happened again, and the full VM regression's output was lost (ENOSPC, also in `/tmp`). A second cause: pytest kept the tmp dirs of the **last 3 sessions**, each holding the VM disk images (now including 14 GiB of RAID disks, about 5 GiB of it written by the RAID-1 resync).
      - Mitigation (0.12.1): `tmp_path_retention_count = 1` in `pytest.ini`. Verified by experiment: three consecutive runs left only the latest dir.
      - 2026-10-19 (0.17.1) - It happened again twice: the AArch64 image build hit `zstd … No space left on device`, and the x86 regression's RAID and USB tests failed with ENOSPC.
        - Root cause: **every VM fixture was session-scoped**, so all VMs and their disk images lived until the end of the run (primary, hot-plug, residue, 14 GiB of RAID disks, USB stick and target, the AArch64 card), on top of a 21 GiB store.
        - Fix: VM and disk fixtures are now module-scoped (each is used by exactly one test file) and delete their images at teardown. The image builds stay session-scoped.
        - Disk headroom is now logged in `harness.log` at VM start and at teardown.
        - `nix-collect-garbage` freed 18.0 GiB this time.
        - Pitfall: `pgrep -f "pytest -m vm"` matches its own command line; use `pgrep -f "[p]ytest -m vm"`.
      - Still to do: the stale-ISO helper above.

30. **`uptime` reports about 220 days on the installer and on the first boot of the installed system; `date -u` is right.** *(anomaly, 2026-10-24, user)*
    - 220 days is the time from systemd's built-in clock epoch (2026-03-17, seen in attempt 1) to now.
    - coreutils 9.11's `uptime` computes now minus a boot time taken from the utmp `BOOT_TIME` entry. Without that entry, it falls back to the mtime of `/var/lib/systemd/random-seed` (gnulib `boot-time-aux.h`); only after that does it use the kernel's counter.
    - **Hypothesis:** both are written early in boot, before NTP corrects the clock. On a first boot (the installer always; a fresh install, which has no `/var/lib/systemd/timesync/clock`), the clock still holds the epoch at that moment. A later boot restores the clock saved at shutdown, so the error should be small.
    - **2026-10-24, confirmed (user): `who -b` shows 2026-03-17 and `/proc/uptime` is right.** So the utmp boot record was written before the clock was corrected.
    - To confirm, on the CM4:
      - `cat /proc/uptime` should be right;
      - `who -b` should show 2026-03-17;
      - `stat -c %y /var/lib/systemd/random-seed` should show its mtime;
      - after a reboot, `uptime` should be about right.
    - Not caused by pre-nixos; it comes from the board having no RTC (item 23's board). To decide: document it, or keep it out of pre-nixos's own logs.

34. **An old SATA SSD is planned as an HDD.** *(user report, 2026-11-06, the first BIOS PC: 128 GB SATA SSD `sda` plus two 750 GB HDDs, serial ISO 0.25.0)*
    - The plan put `main` on a RAID-1 of the HDDs and `sda` in `large`; the TUI showed `sda` as an HDD.
    - pre-nixos uses only the kernel's `/sys/block/<disk>/queue/rotational` (`inventory.py:52`).
    - **Hypothesis:** the kernel reports `1` because the drive's ATA identify data does not report "solid state" (word 217), as some early SSDs do not.
    - Asked the user for `queue/rotational`, `lsblk ROTA` and `hdparm -I` (rotation rate).
    - Then design an override (a site setting, a TUI toggle, or reading the rotation rate).
    - **2026-11-06, confirmed (user):**
      - `/sys/block/sda/queue/rotational` = 1;
      - `lsblk`: `sda 1 sata G.SKILL 128GB SSD`;
      - `hdparm -I /dev/sda | grep -i rotation` prints nothing, so the drive does not report a rotation rate and the kernel defaults to rotational.
      - Not a pre-nixos defect. The user can lay the disks out in the TUI.
      - Optional improvement (user to decide): an override, such as a site setting listing disks to treat as SSD, a TUI toggle, or treating a model name containing "SSD" as solid-state.
    - **2026-11-06, user decision:** do both of these (not many such drives are expected):
      1. When an apparently rotational disk has "SSD" in its model name, do not assume: **ask**, and block auto-install until answered.
      2. A per-disk SSD/HDD toggle in the TUI.
      - Needs a short design (where the question is asked; how auto-install reports the block).
    - **2026-11-07: design** `plans/2026-11-07T161535Z-ssd-model-name-design.md`. Finding F3: on blank disks the boot run provisions storage even without auto-install, so the design recommends blocking provisioning too (D2 (b)). Waiting on the user: R-S3/R-S4, D2.
    - **2026-11-07 (user):** R-S3/R-S4 approved; D2 (b) (block provisioning and auto-install).
    - **Implemented in 0.26.0:**
      - `disk_class.py` (the D1 rule, answers applied to the inventory, the plan's `disk_classes`);
      - `pre-nixos --ssd/--hdd`; a run that would provision or install stops first (exit 3, `REASON=disk-class-unconfirmed`);
      - the boot service reports exit 3 as `STATE=plan-only`, `DETAIL=disk-class-unconfirmed` (flake check `boot-service-status`), and the login notice says how to answer;
      - TUI: a question per unconfirmed disk at start, and `T` to switch any disk's class.
      - U1 resolved by experiment: `notes/2026-11-07T165520Z-u1-scsi-unreported-rotation.md`. VM test `tests/vm/test_disk_class_vm.py`.
      - **2026-11-08, user:** with 0.26.0, `pre-nixos --plan-only` on the PC did not ask; the SSD was still planned as an HDD. **Root cause (#336, experiment `notes/2026-11-08T003000Z-u2-sata-model-truncation.md`):** for SATA disks, sysfs `device/model` is 16 characters (`G.SKILL 128GB SS`). The VM stand-in was virtio-scsi, which does not truncate. **Fix in 0.26.1:** the model comes from `device/vpd_pg89` (ATA IDENTIFY) when present; the VM test now uses an AHCI disk with the user's model name.
      - 2026-11-08: the SATA VM test **passed** (guest sysfs model `G.SKILL 128GB SS`; journal names `G.SKILL 128GB SSD`). The user's real drive page (serial blanked) is a fixture and decodes to the full model; its rotation rate (word 217) is 0.
      - 2026-11-08: RAID VM test passed with the SATA-capable disk helper; `nix flake check` passed (inputs over git, `scripts/nix_git_inputs.py`).
      - 2026-11-07, VM runs: run 1 failed on the test's own `cat /proc/mdstat` (no md driver when nothing is provisioned); run 2 found the TEST SSD named `sdb`, which exposed #334 (sd names follow probe order). Run 3 **passed** (`notes/2026-11-07T172113Z-vm-run`). `test_raid_provisioning.py`, fixed for #334, **passed** (`notes/2026-11-07T172610Z-vm-run`). `nix flake check` passed, including the new `boot-service-status`.
