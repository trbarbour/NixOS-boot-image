# Task Queue

_Last updated: 2026-10-22T03-33-24Z_

## Active Tasks

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


6. **Narrow the flake's package source (`src = ./.`).**
   - 2026-10-19 evidence that this matters:
     - Committing four new test files during a VM run changed the `pre-nixos` source, and so the whole AArch64 system.
     - The image and a second evaluation of the system disagreed (`q9m06…` vs `cbcs15…`). The fixture's precondition caught it.
     - Test-only edits should not change the product image. Rule until fixed: do not commit or edit tracked files while a VM run is evaluating.
   - 2026-10-18T03-05-00Z - Every tracked-file change, docs included, alters the boot-image derivation. Shown: commit `4bb90dd` → `rmhwpzbb…`, current HEAD → `s8l0sbw4…`, with identical inputs. This defeats build caching and makes it harder to show two ISOs are the same. Consider `lib.fileset` restricted to `pre_nixos/`, `modules/` and packaging files; needs a design debate.


7. **Make the VM harness (`tests/vm/`) type-check cleanly.**
   - 2026-10-18T03-25-00Z - `mypy --check-untyped-defs` reports 18 errors in `tests/vm/{controller,fixtures,metadata}.py`. Reviewed: none is a known runtime bug.
     - 4× "Missing return": the functions end in `_raise_with_transcript`, which always raises but is annotated `-> None`; annotate it `NoReturn`.
     - 3× undefined `Dict`: annotations only, under `from __future__ import annotations`.
     - 4× undefined `pexpect`: a `TYPE_CHECKING` import alias.
     - The rest are generator-fixture return types and `object`-typed metadata dicts.
   - Then add a mypy check over `scripts/` and `tests/vm/` to the suite, so drift between script and harness APIs is caught at check time rather than at run time.


8. **Let `collect_pre_nixos_journal.py` capture the whole run.**
   - 2026-10-18T04-04-07Z - The script collects the journal right after login, while `pre-nixos` is still running, so it captured only 2 lines. This behaviour predates the 0.9.3 repair. Wait for the unit to go inactive first, as the VM tests do.


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

11. **Planner gives a 4 MiB swap LV on two SSDs.** *(anomaly, 2026-10-19)*
    - `plan_storage("fast", [vda 4G, vdb 4G], ram_gb=2)` plans `md0` RAID-0, `slash` 6136M and `swap` **4M** in `main`.
    - Reqs §2.4: swap goes in `main` "when no rotating tier exists and capacity allows"; "if there is insufficient capacity anywhere, swap may be omitted". A 4 MiB swap is neither a real size nor omitted, so it looks like `slash` is sized before swap.
    - Similarly, SSD + 3 HDD gives `data` 4M on `large`.
    - To do: reproduce in a unit test, then root-cause against §2.4.
    - Related (2026-10-19, AArch64 E5 run5): a solid-state device too small for `slash` still becomes `main`. The planner postcondition (#313) then stops pre-nixos, which is safe but leaves no plan at all. Seen with QEMU virt's 128M flash (`mtdblock0`); that device is now excluded as a non-candidate. Design question: choose `main` only where `slash` fits.

12. **End-to-end install VM test (E9d).** *(gap, 2026-10-19)*
    - 2026-10-22: #320 (duplicate loader attribute) reached hardware because of this gap; the flake checks added for it now cover the parse and evaluation part.
    - No VM test runs `nixos-install` and then boots the installed system, on either x86 or AArch64. Images are built without `PRE_NIXOS_AUTO_INSTALL`.
    - For AArch64: boot the installed NVMe disk with U-Boot for `qemu_arm64` and extlinux. That checks the extlinux, initrd and LVM-root part of plan item 8 (design §3, E9d).
    - Unknowns: `nixos-install` builds the generated configuration, so it needs substitutes or network inside the VM, and it is slow under TCG.

13. **Firmware updates on the installed Pi.** *(follow-up, plan item 8 design D2)*
    - The firmware and U-Boot on `/boot` are written once, at install, as on the stock SD card.
    - Decide whether `nixos-rebuild` should refresh them.

14. **Test-only path in `install._is_mount_ready`.** *(anomaly, 2026-10-19)*
    - Under pytest, the function treats `ROOT/etc` existing as "mounted" (`PYTEST_CURRENT_TEST`). That is test logic in product code.
    - Replace it with an injected predicate, as `boot_platform.install_boot_files` does.

15. **`nix-collect-garbage` deletes unrooted experiment builds.** *(anomaly, 2026-10-19)*
    - The GC before the 0.18.1 regression deleted the NVMe U-Boot just built, which cost 17 minutes to rebuild.
    - Plan: build experiment inputs with `--out-link` under the scratchpad (GC roots), per AGENTS.md "save a copy".

16. **Show auto-install results in the TUI.** *(gap, 2026-10-20, AArch64 item 9)*
    - The TUI does not read `/run/pre-nixos/auto-install-status`.
    - A refusal such as `REASON=boot-order` (with `MESSAGE=…`) reaches only the consoles and the status file.

17. **Report a second installer boot after a successful install (AArch64 item 9b).** *(plan §3.9)*
    - When the installer boots again on a board that already has an installed system, say on serial and in the TUI that the boot order is the likely cause.

18. **CI tiers 2 and 3, and the mypy ratchet.** *(user request, 2026-10-21; tier 1 is trbarbour/NixOS-boot-image#318)*
    - 2026-10-21: #318 merged; `pre_nixos/boot_order.py` added to `[tool.mypy] files` on #317's branch.
    - Tier 2: x86 VM tests (about 1 h), nightly or on a label.
    - Tier 3: AArch64 image and VM tests under emulation; needs a binary cache (e.g. Cachix) to fit a 6-hour job.

19. **Move the VM fixtures and scripts from PRE_NIXOS_ROOT_KEY/--impure to sites.** *(follow-up, site-settings design D2)*
    - `tests/vm/fixtures.py`, `scripts/manual_vm_debug.py` and `scripts/collect_sshd_pre_nixos_debug.py` still pass the key through the legacy environment fallback.
    - Move them to `--override-input site path:<tmp dir>`, then decide whether to drop the fallback.

20. **CMA pool exhausted on the CM4 during provisioning.** *(anomaly, 2026-10-22, item 10 attempt 1)*
    - `cma: __cma_alloc: linux,cma: alloc failed, req-size: 256 pages` (also 512 pages), with 176 of 16384 pages free.
    - Hypothesis, unproven: the NVMe host memory buffer (64 MiB, `allocated 64 MiB host memory buffer`) fills the 64 MiB CMA pool.
    - To do: find who requests the failed allocations, and whether the installed system is affected. Candidate remedies: a larger `cma=`, or `nvme.max_host_mem_size_mb`.

21. **Duplicate "Starting automatic NixOS installation" line after a failure.** *(anomaly, 2026-10-22)*
    - The journal shows it again after `Auto-install failed: nixos-install`, at the same second, apparently a buffered message replayed. Reproduce in a unit test, then root-cause.

22. **The SD image took 29 minutes to build on the user's N355.** *(anomaly, 2026-10-22)*
    - Find which derivations are built locally rather than substituted (likely the NVMe U-Boot and the firmware). Consider publishing them to a binary cache (see item 18, tier 3).
    - 2026-10-22 (user): the 0.20.1 rebuild took **8 minutes**, because no AArch64 binaries needed rebuilding. So the first build's cost is one-off AArch64 compilation under emulation on an x86 host. A binary cache remains the remedy for fresh hosts.

23. **Undervoltage warnings on the CM4 (Waveshare CM4-POE-UPS-BOX, PoE from a GS308EPP).** *(anomaly, 2026-10-22, item 10 attempt 1)*
    - `hwmon hwmon1: Undervoltage detected!` appears every few seconds while the installer runs. The user has seen this before on this board, sometimes linked to `config.txt` settings.
    - Unknowns:
      1. Do the warnings also appear with the user's known-good `config.txt`, on the same supply?
      2. Which setting in the image's stock `config.txt` differs, if any?
    - 2026-10-22: the image's `config.txt` (1008 bytes, matching the boot log) is saved as `docs/test-reports/2026-10-22T025029Z-cm4-item10-sd-config.txt`. It is the stock nixpkgs file. Candidate settings, all unproven:
      - `arm_boost=1` (`[pi4]`): a higher CPU clock where the board supports it, so more current;
      - `otg_mode=1` (`[cm4]`): the XHCI host;
      - `avoid_warnings=1`, which only hides the firmware's on-screen warning.
      Still needed: the user's known-good `config.txt`.
    - 2026-10-22 (user):
      - No USB devices are attached, so `otg_mode=1` is unlikely to matter.
      - `avoid_warnings=1` is wanted: it stops the firmware's warning from overwriting the framebuffer.
      - The user also suspects `arm_boost=1`: as they recall, it (or `arm_freq`) may need a matching `over_voltage`. The CM4s have good heatsinks.
      - Experiment: change one line at a time in the SD card's FIRMWARE `config.txt`, first without `arm_boost=1`, and count the warnings over a fixed period.
    - Plan:
      - Get the user's earlier `config.txt` and the `vcgencmd get_throttled` readings, then half-split the differences.
      - If a setting is needed, add it to the installer image and to the installed `/boot`. The image's config.txt is shared with the installed system via `nix/rpi4-nvme-firmware.nix`.

## Recently Completed
- 2026-10-22T13-30-56Z - Merged trbarbour/NixOS-boot-image#322 (0.21.0). (user request) The 0.20.1 SD image had the same file name as 0.20.0, because nixpkgs names images after its own version only. From 0.21.0, both images are named `pre-nixos-<version>-g<commit>[-dirty]-<nixpkgs label>-<system>.<ext>` (the user chose version plus commit). Covered by the flake check `image-file-names`.
- 2026-10-22T04-04-06Z - Merged trbarbour/NixOS-boot-image#321 (0.20.1): fixed #320 (closed). On the CM4, `nixos-install` failed on a duplicate `boot.loader.grub.enable`. The Pi loader is now a separate module with `mkForce`, tested against real `nixos-generate-config` output (pytest, plus the flake checks `installed-configuration-parses` and `installed-rpi-boot-loader`). CI green, no Codex findings. Item 10: waiting for the user's retest.
- 2026-10-22T00-38-17Z - Merged trbarbour/NixOS-boot-image#319 (0.20.0): site settings. The root key and auto-install are supplied purely, from a directory outside git (`--override-input site path:<dir>`, or `lib.mkBootImage { format; site; }`), for the ISO or the SD image separately. A missing site file and invalid settings are errors. `.#bootImageSd` works on x86_64 hosts. VM regression 12/12.
- 2026-10-21T13-23-59Z - Merged trbarbour/NixOS-boot-image#317 (0.19.1): NVMe U-Boot v2026.10 plus the read/write DMA-translation patch (verified on the CM4, #316 closed), and AArch64 item 9 (the `BOOT_ORDER` check). Also merged trbarbour/NixOS-boot-image#318: tier-1 CI (unit tests on 3.10 and 3.13, the strict mypy ratchet, flake check, SD-image evaluation), and tests no longer write to the host's `/var/log`.
- 2026-10-20T03-08-58Z - Merged trbarbour/NixOS-boot-image#315 (0.18.1). AArch64 plan items 3 to 8:
  - the SD image is the stock installer variant plus pre-nixos;
  - VM test on `qemu virt`;
  - installed-system boot through the Pi firmware, an NVMe-capable U-Boot and extlinux.
  It also has the Codex review fixes (all-or-nothing ledger appends, fixture cleanup in `finally`, emulation-setup errors, AArch64 SSH). Full VM regression 12/12.
- 2026-10-19T02-13-57Z - Merged trbarbour/NixOS-boot-image#314 (0.12.1). Added the RAID-1 provisioning VM test. RAID arrays are now created with no write-intent bitmap (reqs §2.2 R-R1; disko patched with `--bitmap=none`). Fixed #313 (HDD-only plans had no `main/slash`; the swap-room check compared bytes with GiB). The harness filters console broadcasts out of command output, and pytest keeps only one session's tmp dirs. Full VM regression 8/8. Details: `notes/2026-10-19T003559Z-raid-spike.md`.
- 2026-10-19T00-19-13Z - Merged trbarbour/NixOS-boot-image#312 (0.11.1). nixpkgs is now 26.05 (`26f4107e47e3`). Pin updates work over git (`nix_git_inputs.py --update`, and `update_nixos_stable.py` via `git ls-remote`). Fixed #311 (disko could not build offline: `makeBinaryWrapper` added to the image) with the closure test `tests/vm/test_disko_offline_closure.py`. The residue test's `mdadm` is now non-interactive. All VM tests pass. Details: `docs/work-notes/2026-10-18T222729Z-nixpkgs-26.05-pin.md`.
- 2026-10-18T22-18-16Z - Merged trbarbour/NixOS-boot-image#310 (0.10.9): fixed #309 (the USB boot stick was counted as existing storage; the boot disk resolved to `/dev/dev/sda`). Added the USB-stick VM test, the `run_as_root_checked` echo fix, the AArch64 user answers and the requirements. VM-verified.
- 2026-10-18T17-32-54Z - Merged trbarbour/NixOS-boot-image#308 (0.10.7):
  - **#306:** disks backing the running system, including the boot medium, are never planned, wiped or counted as existing storage. Requirements §2.3 is amended.
  - **#307:** forced teardown releases mounts and swap before deactivating.
  - **Residue VM scenario:** now deterministic, by hot-plugging its disks via QMP.
  - **Harness fixes:** anchored root-prompt pattern; fail fast on failed units; action-log capture.
  - Full suite: 290 passed (`notes/2026-10-18T170729Z-vm-run.md`).
  - Follow-up still open: a VM test that boots the ISO from a non-removable USB disk (needs a spike).
- 2026-10-18T04-04-07Z - Repaired the VM debug scripts (version `0.9.3`).
  - Five scripts failed at import, because the legacy shim's star-import omits `_resolve_iso_path`; they now import from `tests/vm/` directly.
  - mypy then exposed stale call sites, which are fixed; `collect_pre_nixos_journal.py` is rebuilt on `manual_vm_debug` helpers via `describe_boot_image()`.
  - The harness now disables pagers, after `networkctl` hung `manual_vm_debug`.
  - Added `tests/test_script_imports.py`. The journal script and `manual_vm_debug` pass end to end. See `notes/2026-10-18T040407Z-vm-run.md`.
- 2026-10-18T02-53-00Z - Migrated the dev environment from Codex to Claude Code cloud. Added `scripts/nix_git_inputs.py` (verified git overrides for `github:` inputs), the SessionStart hook `.claude/hooks/session-start.sh`, and shared `scripts/lib/dev_packages.sh`/`python_venv.sh` (now including `openssh-client`). The full suite passes under TCG. Details: `docs/work-notes/2026-10-18T02-01-07Z-claude-code-environment-migration.md`, `notes/2026-10-18T025300Z-vm-run.md`.
- 2026-10-18T03-30-00Z - Made the unit tests independent of host storage: an autouse `existing_storage` stub (`tests/storage_stub.py`) fails any test that reaches `detect_existing_storage()` without declaring a scenario, using a `BaseException` so production `except Exception` handlers can't hide it. This exposed 9 dependent tests (4 failing, 5 passing by accident). Added failure-path tests for the scan, the CLI, the TUI header and TUI apply; removed two stale `# pragma: no cover`; bumped version to `0.9.1`. See `docs/work-notes/2026-10-18T02-01-07Z-claude-code-environment-migration.md` (F1).
- 2026-04-25T20-37-02Z - Kept GRUB serial support enabled, taught installed-system configuration generation to mirror the booted console ordering (`/proc/cmdline`) so explicit serial-menu boots keep serial primary while default boots remain display-primary, added regression coverage in `tests/test_install.py`, and bumped patch version to `0.8.8`; details in `docs/work-notes/2026-04-25T20-37-02Z-console-policy-alignment.md`.
- 2026-04-25T19-35-35Z - Reverted the global early-DHCP module change, switched `configure_lan` from unconditional `systemctl restart systemd-networkd` to `networkctl reload`/`reconfigure` with restart fallback, added unit coverage for both paths in `tests/test_network.py`, and bumped patch version to `0.8.7`; details in `docs/work-notes/2026-04-25T19-35-35Z-network-init-delay-root-cause.md`.

- 2026-04-25T19-15-23Z - Added early Ethernet DHCP startup in `modules/pre-nixos.nix` via `systemd.network.networks."10-early-dhcp"`, extended module wiring assertions in `tests/test_pre_nixos_module.py`, and bumped the patch version to `0.8.6`; details in `docs/work-notes/2026-04-25T19-15-23Z-boot-image-early-dhcp.md`.

- 2026-04-25T17-43-55Z - Fixed TUI plan-editor drift by regenerating `plan["disko"]` after array/LV edits, added regression coverage in `tests/test_tui.py`, and bumped the patch version to `0.8.5`; details in `docs/work-notes/2026-04-25T17-43-55Z-tui-lv-size-sync.md`.

- 2026-04-25T01-56-44Z - Fixed installed-system console ordering generated by `pre_nixos/install.py` so `console=tty0` remains the final kernel console target (`console=ttyS0,115200n8` is now listed first), added regression assertions in `tests/test_install.py`, and bumped the patch version to `0.8.4`; details in `docs/work-notes/2026-04-25T01-56-44Z-installed-system-console-order.md`.

- 2025-10-19T11-58-00Z - Probed the storage-detection path inside the debug VM and captured `pre-nixos-detect-storage`/`pre-nixos --plan-only` output; see `docs/work-notes/2025-10-19T11-49-37Z-storage-detection-probe/`. 【F:docs/work-notes/2025-10-19T11-49-37Z-storage-detection-probe/storage-detection-probe.md†L1-L205】

- 2025-10-19T02-45-00Z - Verified the boot ISO embeds the generated root key; see `docs/work-notes/2025-10-19T02-45-00Z-embedded-key-verification.md`. 【F:docs/work-notes/2025-10-19T02-45-00Z-embedded-key-verification.md†L1-L58】
- 2025-10-19T01-40-00Z - Audited `systemctl list-dependencies sshd` on the rebuilt ISO: only `sysinit.target` and its mounts remain, `WantedBy=` is empty, and no `secure_ssh` unit exists—evidence captured in `docs/work-notes/2025-10-19T01-11-04Z-sshd-dependency-audit/`. 【F:docs/work-notes/2025-10-19T01-11-04Z-sshd-dependency-audit/sshd-dependency-notes.md†L1-L98】
- 2025-10-19T00-12-43Z - Captured sshd/pre-nixos verification before and after provisioning to confirm the non-blocking restart completes independently; artefacts in `docs/work-notes/2025-10-19T00-12-43Z-sshd-pre-nixos-verification/`.
- 2025-10-19T01-15-00Z - BootImageVM harness now regains a root shell for privileged probes and waits for `pre-nixos` to become inactive, removing the LVM permission failure and IPv4 buffering. 【F:docs/work-notes/2025-10-18T22-57-17Z-boot-image-vm-regression/harness.log†L120-L185】
- 2025-10-18T22-57-17Z - `nix develop .#bootImageTest -c pytest tests/test_boot_image_vm.py -vv` passes both VM cases end-to-end using the shared `/tmp/boot-image-shared-tmp`; logs archived under `docs/work-notes/2025-10-18T22-57-17Z-boot-image-vm-regression/` with summary in `docs/test-reports/2025-10-18T22-57-17Z-boot-image-vm-test.md`. 【F:docs/work-notes/2025-10-18T22-57-17Z-boot-image-vm-regression/harness.log†L1-L185】【F:docs/test-reports/2025-10-18T22-57-17Z-boot-image-vm-test.md†L1-L26】
- 2025-10-18T17-45-00Z - The `bootImageTest` dev shell enforces a shared `/tmp/boot-image-shared-tmp`, letting `nix build .#bootImage` succeed without manual overrides; the ISO completed at `/nix/store/83vw736vi27nryfaa3i2bawy435xspqm-…-x86_64-linux.iso`. 【F:flake.nix†L120-L135】【029fd2†L1-L68】【0054d1†L1-L4】
- 2025-10-17T03-10-54Z - Disko label regression is resolved and the impure ISO build now completes: `/run/pre-nixos/storage-status` reaches `STATE=applied`/`DETAIL=auto-applied`, and the harness records the rebuilt store path before launching the VM. 【F:docs/test-reports/2025-10-17T03-10-54Z-boot-image-vm-test.md†L1-L12】【F:docs/work-notes/2025-10-17T03-20-16Z-boot-image-vm-regression/harness.log†L1-L5】
- 2025-10-14T05-00-00Z - Added HDD-only regression coverage in `tests/test_apply.py` that asserts the generated disko configuration provisions both disks, keeps `md0` bound to the `main` volume group, and retains the slash LV mount at root.
- 2025-10-14T01-01-49Z - HDD-only plans now populate `plan["disko"]` and the single-disk regression test asserts the emitted disk/LVM layout (`pre_nixos/planner.py`, `tests/test_plan_storage.py`).
- 2025-10-13T00-00-00Z - `secure_ssh` now invokes `systemctl reload-or-restart --no-block sshd` with unit coverage guarding against regressions; follow-up VM runs will confirm the oneshot no longer blocks on sshd.
 - 2025-10-11T04-10-39Z - Pre-built the boot image ahead of VM regressions, recording `/nix/store/d8xvgbl51svz0axi2n0xzrij330hw6i4-nixos-24.05.20241230.b134951-x86_64-linux.iso` in `docs/work-notes/2025-10-11T04-10-39Z-boot-image-prebuild.md` for reuse.
- 2025-10-10T13-05-00Z - Confirmed structured `pre_nixos` journal entries are present in the debug session logs (former queue item 2). No logging configuration changes required; see `docs/work-notes/2025-10-10T13-05-00Z-pre-nixos-journalctl-verification.md` for details.
- 2025-10-08T06-10-00Z - Confirmed the boot image crashed because `systemd-networkd.service` is absent, captured `journalctl -u pre-nixos.service`, and planned fixes (enable networkd + guard restarts). See `docs/work-notes/2025-10-08T06-10-00Z-pre-nixos-networkd-investigation.md` and new serial log `docs/boot-logs/2025-10-08T06-10-00Z-serial.log`.
- 2025-10-07T04-01-53Z - Verified `boot.kernelParams` for the pre-installer ISO include `console=ttyS0,115200n8` and `console=tty0`; no further changes required for persistent serial logging. See `docs/work-notes/2025-10-07T04-01-53Z-serial-console-verification.md`.
- 2025-10-07T03-58-17Z - Identified `wipefs -n /dev/fd0` failures as the source of the storage detection error, taught the detector to ignore `/dev/fd*`, and ensured VM tests print `journalctl -u pre-nixos.service` on provisioning failures; see `docs/work-notes/2025-10-07T03-58-17Z-pre-nixos-storage-detection.md`.
- 2025-10-07T03-11-58Z - Hardened BootImageVM login handling against ANSI escape sequences; see `tests/test_boot_image_vm.py` and regression log `docs/test-reports/2025-10-07T03-11-58Z-boot-image-vm-test.md` for details (remaining provisioning/network issues persist).
- 2025-10-07T02-11-38Z - Audited boot-image VM prerequisites; see `docs/test-reports/2025-10-07T02-11-38Z-boot-image-prereq-audit.md` for detailed pass/fail outcomes and recommended follow-ups.
- 2025-10-07T01-11-00Z - Identified root cause of boot-image VM login failure: colourised Bash prompt emits ANSI escapes that our regex does not match, preventing `_login` from issuing `sudo -i`. See `docs/work-notes/2025-10-07T01-11-00Z-boot-image-vm-root-prompt-analysis.md`.
- 2025-10-06T15-54-30Z - Captured baseline boot-image VM test output, timings, and serial log for reference.
- 2025-10-24T01-39-58Z - Expanded unit coverage for LAN detection, SSH key propagation, and storage plan execution, asserting structured logs for regressions in `tests/test_network.py` and `tests/test_apply.py`. 【F:tests/test_network.py†L1-L210】【F:tests/test_apply.py†L1-L260】
