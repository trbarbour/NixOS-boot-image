# Task Queue

_Last updated: 2026-10-30T12-35-13Z_

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
    - 2026-10-24 (user), on the installed CM4 with the stock `config.txt` (`arm_boost=1` present): `cpufreq/policy0/cpuinfo_max_freq` = 1500000, `cpufreq/boost` = 0.
      - So `arm_boost` does not raise this CM4 above 1.5 GHz, and removing it should not change the undervoltage. Suspect eliminated by measurement, unless the reading was taken without the line (to confirm with the user).
      - Warnings also appear at idle (from 20 s after boot), so the supply is marginal even at low load.
      - Next split: the power path. Run on a bench 5 V supply instead of PoE. Check the GS308EPP's per-port power reading, class and limit. Check whether the UPS battery charging shares the PoE budget.
      - 2026-10-24 (user): the reading **was** taken with `arm_boost=1` present, so `arm_boost` is eliminated.
        - **Correction:** this CM4 is not on PoE. It is powered through the barrel jack (7–36 V DC) from the board's own 12 V wall-wart (3–4 A, to be checked), which is barely warm. So the input supply (about 36–48 W) is far above the load.
        - The suspect is the board's 5 V rail to the CM4: its regulator, the UPS power path, or the contacts. A web search found one user report of undervoltage with this UPS board; another poster suggested dirty contacts, unconfirmed (community.home-assistant.io/t/ups-for-rpi-4/503505).
        - **Plan (half-split, one change at a time, same idle period, warnings counted with `journalctl -k -b | grep -c 'Undervoltage detected'`):**
          1. Bench supply at 12 V: note the current, and whether the count changes (this rules the wall-wart in or out).
          2. Measure the 5 V rail at the CM4 (GPIO header 5 V to GND), with a DMM at idle and ideally a scope for dips below about 4.63 V. This decides between "the rail sags" and "the reading is wrong".
          3. ~~Remove the UPS battery~~: the board has **no 18650 cells fitted** (user, 2026-10-24), so battery charging is ruled out. The UPS power-path circuitry is still in the 5 V path.
          4. Reseat the CM4 (contacts).
        - 2026-10-24 (user, DMM): 5 V rail at idle = **5.132 V**. Not low at idle, so look for transient dips under load (scope).
        - 2026-10-24 (user, DMM):
          - The 4-core CPU load drops the rail to 5.096 V; adding NVMe reads at 389 MB/s takes off another 1–2 mV.
          - Neither load triggered warnings. The installed system gives about 1–2 warnings per hour.
        - **Attempt-4 log, warnings by phase:**
          - installer: 36 in about 6.5 min, one every 4–6 s, starting at 20 s, before the install;
          - installed system: 3 in the first minute, then one at 909 s and one at 2473 s.
        - Note: the driver polls every 2 s and clears the firmware's sticky flag (`raspberrypi-hwmon.c`), so the counts are episodes, not dips.
        - **Hypothesis:** the trigger is the installer's **SD-card** activity, not CPU or NVMe load.
          - Next test: `dd if=/dev/mmcblk0 of=/dev/null bs=1M iflag=direct` on the installed system, with the card inserted, while watching `journalctl -kf`.
          - If that triggers warnings: scope the 5 V rail and the card's 3.3 V supply, and try another card. If not: SD reads plus NVMe writes together, and Wi-Fi/Bluetooth bring-up.
        - 2026-10-24 (user):
          - SD reads alone give 5.089 V. SD and NVMe reads with the CPU load give 5.088 V. **No warnings at all.**
          - **The SD-read hypothesis is refuted.**
        - Remaining installer-only activity:
          1. **NVMe writes:** mkfs and the store copy. Warnings ran from about 60 s, the formatting, to the end of the install. Not yet tested.
          2. **Early boot, 20–40 s:** Ethernet link down/up during the rename, and Wi-Fi/Bluetooth bring-up. The installed system's few warnings are also in its first minute.
          - Next test: `dd … oflag=direct` writes, then writes with the CPU and SD loads, with the scope on 5 V and the M.2 slot's 3.3 V.
        - 2026-10-24 (user): NVMe writes alone give 5.091 V and **no warnings**, with a slight whine (probably coil whine).
        - Wi-Fi ruled out:
          - attempt 3's installed system ran `wpa_supplicant` and had 8 warnings over about 12 min of log, against attempt 4's 5;
          - but the installer, with the most warnings, runs no Wi-Fi client (`networking.wireless.enable` and `networkmanager.enable` both evaluate to false).
        - Next splits:
          1. NVMe writes plus SD reads plus the CPU load, imitating the install.
          2. **The installer idle for 10 min** (SD boot; the NVMe is non-empty, so no install), counting warnings. This separates the installer environment from the install's load.
        - User's hypothesis: the installer runs the CPU faster. Evidence against it (evaluated):
          - the same `config.txt` on the SD card and the NVMe `/boot`;
          - neither system sets `powerManagement.cpuFreqGovernor` (the installer's evaluates to null, and the generator writes none), so both use the kernel default `schedutil`.
          - To confirm on the installer: `cpuinfo_max_freq`, `scaling_governor`, `scaling_cur_freq`.
        - New hypothesis: **frequency/voltage transitions**, not the frequency itself. Test a bursty load (`timeout 0.2 yes; sleep 0.3` in a loop) under `schedutil`, against the same under `performance`.
        - 2026-10-24 (user): **4 h of steady 4-core load: no warnings. Removing the load: a burst of about 9 warnings in 2 min.**
          - Warnings follow load *changes*, which supports the transition hypothesis.
          - Next split: load on/off cycles (30 s/30 s) under `schedutil` against `performance`.
            - Warnings under `schedutil` only: frequency/voltage (DVFS) transitions.
            - Under both: the regulator's response to load steps.
          - Scope: single-shot, falling edge at about 4.75 V on 5 V, armed before the load stops.
        - 2026-10-24 (user): 30 s/30 s load cycling under `schedutil` for 18 min: **one warning, at the start** (when commands were typed). Under `performance` for 5 min: the same.
          - **Load steps and DVFS are not the trigger.**
          - User's hypothesis: **network activity**, since the tests were run over two SSH sessions. It fits every observation so far: the idle SSH during the 4 h load; typing at load removal; the installer's link changes and DHCP; possible cache downloads during the install; a quiet installed system.
          - Tests:
            1. Watch from the **serial console** with no SSH sessions.
            2. Bulk Ethernet traffic with no disk I/O: `iperf3`, both directions, or `curl -o /dev/null`.
            3. If it triggers: force the link to 100 Mbit/s with `ethtool -s lan speed 100` and repeat.
        - 2026-10-24 (user): a third SSH login was followed, after a few seconds, by **4 episodes in about 20 s**, then quiet for 3 min.
          - The delay is not the journal (`-f` is sub-second). The driver polls every 2 s, and the login itself takes seconds: key exchange, a logind session, and the first login's `user@.service`.
          - Next:
            - correlate with `journalctl -o short-precise`;
            - split a serial-console login (no network) from bulk traffic with no login.
        - 2026-10-29 (user):
          - The CM4 idle, installed system, for **5 days: no episodes at all.**
          - The later SSH logout and a new login gave none, so the earlier SSH-login burst does not reproduce.
          - Planned: a marked run (`logger MARK …`), with the journal exported for correlation, covering bulk Ethernet traffic and the installer left idle.
        - 2026-10-30 (user): a bulk download (`curl -o /dev/null` of a Linux kernel tarball, about 150 MB, limited by the WAN speed): **no episodes.**
          - Ethernet receive at WAN speed is ruled out. Gigabit-rate traffic and transmit are untested.
          - Remaining:
            1. the link bounce (`ip link set lan down/up`), the installer's early-boot pattern;
            2. gigabit transmit and receive on the LAN (`iperf3` and `-R`);
            3. the installer left idle.
    - Plan:
      - Get the user's earlier `config.txt` and the `vcgencmd get_throttled` readings, then half-split the differences.
      - If a setting is needed, add it to the installer image and to the installed `/boot`. The image's config.txt is shared with the installed system via `nix/rpi4-nvme-firmware.nix`.

24. **The auto-install start time is logged from an unsynced clock.** *(anomaly, 2026-10-22, CM4 attempt 2)*
    - `Starting automatic NixOS installation at 2026-03-17 19:56:48Z`: the CM4 has no RTC, and timesyncd had not synced yet.
    - Options: wait for `time-sync.target` (bounded) before stamping, or mark the time as unsynchronised.

25. **The installed system's label is `26.05pre-git`.** *(anomaly, 2026-10-22, CM4 attempt 2)*
    - The image's label is `26.05.20261015.26f4107`. The channel that `nixos-install` copies seems to lack nixpkgs' `.version`/`.git-revision` files.
    - Reproduce by evaluating `system.nixos.label` against the copied channel, then root-cause.

26. **The installed U-Boot 2026.10 prints `ERROR: reserving fdt memory region failed (addr=0 size=1000 flags=4): -17`.** *(anomaly, 2026-10-22, CM4 attempt 2)*
    - Not printed by the stock U-Boot 2026.04 on the SD card. -17 is EEXIST (already reserved), so it is probably harmless.
    - Find its source in `boot/image-fdt.c`, then decide.

27. **Stale signatures inside old partition areas can resurface when disko recreates the same layout.** *(hazard, 2026-10-23, hypothesis)*
    - What happened: the user removed only the CM4 NVMe's partitions and its first 16 MiB.
    - Detection (`wipefs -n` on the disk) still found signatures, probably the backup GPT at the end of the disk.
    - The hazard: if only disk-level signatures are cleared, the old LVM PV label (at sector 2099201, partition 2's sector 1) and the LVs' ext4 superblocks survive. disko recreates partitions at the same offsets, and guards its `pvcreate` and `mkfs` with `blkid … | grep -q TYPE=` (seen in the attempt-1 journal). It could then reuse stale metadata instead of creating it.
    - Reproduce in a VM: provision, delete the partitions, wipe only the disk-level signatures, provision again, and see whether `pvcreate`/`mkfs` are skipped. Then root-cause and decide, for example: discard or zero the partition starts before disko, or wipe signatures on the new partitions before creating them.

28. **The NVMe U-Boot cannot choose a boot device without editing its environment.** *(gap, 2026-10-23)*
    - Without `CONFIG_BOOTSTD_FULL`, `bootflow scan` takes no flags or label. To boot the SD card when NVMe holds a system, the user had to run `setenv boot_targets mmc0; bootflow scan`.
    - Consider enabling `CONFIG_BOOTSTD_FULL` in `nix/uboot-rpi4-nvme.nix` (size and boot-time cost to check), and document the recovery path.

29. **The installed system shows its LAN announcement twice.** *(anomaly, 2026-10-23; second source in #327)*
    - `pre-nixos-auto-install-ip` has `StandardOutput = "journal+console"`, and `announce-lan-ip.sh` also writes to `/dev/console`, because `pre-nixos-console` is absent on the installed system.
    - Reproduce, then decide on one path to the console, e.g. `StandardOutput = "journal"`.

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

31. **Use the Waveshare CM4-POE-UPS-BOX's battery-backed RTC.** *(user request, 2026-10-24; fixes item 30 at the source)*
    - **Facts (verified here):**
      - Kernel 6.18.56 sets the clock from `rtc0` when it registers, even for a module driver (`drivers/rtc/class.c:433–435`).
      - `CONFIG_RTC_HCTOSYS=y` and `CONFIG_RTC_SYSTOHC=y` (written back after NTP sync).
      - `rtc-pcf85063`, `i2c-bcm2835` and `i2c-mux-pinctrl` are modules.
      - Linux gets the **firmware's** device tree: U-Boot's `fdtdir` lookup fails ("Skipping fdtdir"), and the `blconfig` alias, which is only in the firmware's DT, is readable. So `config.txt` overlays apply.
      - **But the stock firmware set (`sd-image-aarch64.nix` `populateFirmwareCommands`, reused by `nix/rpi4-nvme-firmware.nix`) copies no `overlays/` directory, so `dtoverlay=` cannot work today.**
    - **Unverified:** the board's RTC chip and bus. Waveshare's CM4 PoE Board wiki (found by search; the UPS-BOX page was unreachable from here) says: PCF85063A on i2c-10, address 0x51, `dtparam=i2c_vc=on` and `dtoverlay=i2c-rtc,pcf85063a,i2c_csi_dsi`.
    - **Plan:**
      1. A manual experiment on the installed CM4: copy `i2c-rtc.dtbo` into `/boot/overlays/`, add the lines, reboot, check `/dev/rtc0`, set the RTC, reboot, and check that `who -b` is right.
      2. Then a design debate: ship `overlays/` in the firmware set, and how a site adds `config.txt` lines (a new site setting?), traced to this request.

32. **The installed system's generation limit does not follow its ESP size.** *(gap, 2026-10-30, found while doing R-B3)*
    - The ESP is now 1 to 4 GiB (R-B3), at about 200 MB per generation. extlinux keeps 20 generations by default, which overflows a 1 GiB ESP; systemd-boot (x86) has no default limit at all. A full `/boot` makes `nixos-rebuild switch` fail.
    - Consider writing `boot.loader.{systemd-boot,generic-extlinux-compatible}.configurationLimit` into the generated configuration, derived from the planned ESP size. Needs a design debate (fixed headroom per generation vs. measured closure; what happens when a kernel grows).

33. **BIOS (legacy) x86 installs fail late: the disks are wiped first, then `nixos-install` fails.** *(defect plus possible feature, 2026-10-31, user question)*
    - Facts (evaluated):
      - the ISO is BIOS-bootable (`isoImage.makeBiosBootable = true`), and the x86 VM tests already boot it under SeaBIOS;
      - on a BIOS machine, `nixos-generate-config` writes `grub.enable = true` with no device. The rendered configuration (the GRUB fixture plus the managed block) fails with "You must set the option 'boot.loader.grub.devices' or 'boot.loader.grub.mirroredBoots'".
    - So under R-B1 (UEFI only) pre-nixos should refuse **before** planning or provisioning, by checking `/sys/firmware/efi`, as the BOOT_ORDER check does on the Pi.
    - Optional feature (user: "not worth a lot of effort"):
      - amend R-B1;
      - detect the boot mode at run time;
      - add a 1 MiB EF02 BIOS boot partition on the `main` disks;
      - a GRUB module with `grub.devices` set to the `main` disks' by-id paths;
      - tests: a flake check on the GRUB fixture, and the item-12 end-to-end install VM test under SeaBIOS.
    - 2026-10-31: **the guard is done in 0.23.1** (user request; `boot_platform.legacy_bios_refusal`, `install.legacy_bios_preflight`). Full support is being planned next (user: "I have a couple of old machines to install").

## Recently Completed
- 2026-10-30T23-57-39Z - Merged trbarbour/NixOS-boot-image#329 (0.23.0): the ESP is sized at 3% of its disk, clamped to [1 GiB, 4 GiB] (R-B3; patch from another session, applied and verified here: unit tests, a disko dry run, sgdisk on a sparse image, and x86 VM tests 4/4). The PR also carried the CM4 item-10 acceptance records and the undervoltage notes. CI green, no Codex findings.
- 2026-10-30T12-35-13Z - (user request) 0.23.0: the ESP is sized at 3% of its disk, clamped to [1 GiB, 4 GiB], instead of a fixed 1 GiB (R-B3). Array members share one size, from the smallest. The SD image is unchanged: its FAT partition holds only firmware. Design: `plans/2026-10-30T123513Z-esp-size-design.md`. Follow-up: item 32.
- 2026-10-24T14-05-00Z - **AArch64 plan item 10 passed** (CM4 attempt 4, 0.22.1, user: "LGTM"; `docs/test-reports/2026-10-24T135908Z-cm4-item10-acceptance-4.md`). The SD installer auto-installed NixOS to NVMe, and the installed system boots firmware → U-Boot → extlinux → LVM root, with serial primary, one DHCP lease and SSH. Closes #326 and #327 on hardware. Attempts 1–3 found #320, #323, #324, #326 and #327, all fixed.
- 2026-10-24T03-00-28Z - Merged trbarbour/NixOS-boot-image#328 (0.22.1). Fixed #326: NetworkManager is forced off on installed systems, so networkd is the only DHCP client on `lan`. Fixed #327: console broadcasts no longer appear twice on the primary console. CI green, no Codex findings. Item 10: waiting for the user's attempt 4.
- 2026-10-23T03-50-16Z - Merged trbarbour/NixOS-boot-image#325 (0.22.0). Fixed #323: the installed Pi's initrd now has `pcie-brcmstb` and `nvme`. Fixed #324: the installer's sshd no longer waits for the auto-install. Added the `primaryConsole` site setting (R-C2): serial by default on the SD image, display on the ISO; the serial device comes from the format's own console list. VM tests: x86 3/3, AArch64 4/4. Item 10: waiting for the user's retest.
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
