# Task Queue

_Last updated: 2026-11-12T02-36Z_

## Rules
- **CI minutes (user decision, 2026-11-11):** record-keeping commits (notes, the task queue, VM run logs) go out with the next code push. When one must come after the last code push of a PR, its commit message carries `[skip ci]`. Not before the PR is opened: CI runs only for pull requests (and pushes to `main`), so the PR's first run would land on a `[skip ci]` head and be skipped (2026-11-11, item 52). Never write the skip marker in any other commit message, not even to describe this rule: GitHub matches it anywhere in the head commit's message. Commit d5e1bb0's subject quoted it and suppressed all of PR #353's CI, even after a close and reopen (2026-11-12). Most of #352's CI runs came from record-keeping pushes, and the account's free Actions minutes ran out.

## Active Tasks

6. **Narrow the flake's package source (`src = ./.`).**
   - 2026-10-19 evidence that this matters:
     - Committing four new test files during a VM run changed the `pre-nixos` source, and so the whole AArch64 system.
     - The image and a second evaluation of the system disagreed (`q9m06…` vs `cbcs15…`). The fixture's precondition caught it.
     - Test-only edits should not change the product image. Rule until fixed: do not commit or edit tracked files while a VM run is evaluating.
   - 2026-10-18T03-05-00Z - Every tracked-file change, docs included, alters the boot-image derivation. Shown: commit `4bb90dd` → `rmhwpzbb…`, current HEAD → `s8l0sbw4…`, with identical inputs. This defeats build caching and makes it harder to show two ISOs are the same. Consider `lib.fileset` restricted to `pre_nixos/`, `modules/` and packaging files; needs a design debate.
    - **2026-11-12, audit:** still open: the package's `src = ./.` (flake.nix line 93).

7. **Make the VM harness (`tests/vm/`) type-check cleanly.**
   - 2026-10-18T03-25-00Z - `mypy --check-untyped-defs` reports 18 errors in `tests/vm/{controller,fixtures,metadata}.py`. Reviewed: none is a known runtime bug.
     - 4× "Missing return": the functions end in `_raise_with_transcript`, which always raises but is annotated `-> None`; annotate it `NoReturn`.
     - 3× undefined `Dict`: annotations only, under `from __future__ import annotations`.
     - 4× undefined `pexpect`: a `TYPE_CHECKING` import alias.
     - The rest are generator-fixture return types and `object`-typed metadata dicts.
   - Then add a mypy check over `scripts/` and `tests/vm/` to the suite, so drift between script and harness APIs is caught at check time rather than at run time.
    - **2026-11-12, audit:** still open: `[tool.mypy] files` lists no `tests/vm/` or `scripts/` modules.

8. **Let `collect_pre_nixos_journal.py` capture the whole run.**
   - 2026-10-18T04-04-07Z - The script collects the journal right after login, while `pre-nixos` is still running, so it captured only 2 lines. This behaviour predates the 0.9.3 repair. Wait for the unit to go inactive first, as the VM tests do.
    - **2026-11-12, audit:** still open: `scripts/collect_pre_nixos_journal.py` does not wait for the unit to finish.

12. **End-to-end install VM test (E9d).** *(gap, 2026-10-19)*
    - 2026-10-22: #320 (duplicate loader attribute) reached hardware because of this gap; the flake checks added for it now cover the parse and evaluation part.
    - No VM test runs `nixos-install` and then boots the installed system, on either x86 or AArch64. Images are built without `PRE_NIXOS_AUTO_INSTALL`.
    - For AArch64: boot the installed NVMe disk with U-Boot for `qemu_arm64` and extlinux. That checks the extlinux, initrd and LVM-root part of plan item 8 (design §3, E9d).
    - Unknowns: `nixos-install` builds the generated configuration, so it needs substitutes or network inside the VM, and it is slow under TCG.
    - 2026-11-10: x86 done: `tests/vm/test_installed_system_vm.py` installs with a static address on the BIOS VM, boots the installed disks without the ISO and SSHes in (#342, #343). Remaining: AArch64 and UEFI.
    - **2026-11-12, audit:** the x86 part is done (BIOS). Remaining: AArch64 (U-Boot `qemu_arm64` + extlinux) and an x86 UEFI install.

13. **Firmware updates on the installed Pi.** *(follow-up, plan item 8 design D2)*
    - The firmware and U-Boot on `/boot` are written once, at install, as on the stock SD card.
    - Decide whether `nixos-rebuild` should refresh them.

14. **Test-only path in `install._is_mount_ready`.** *(anomaly, 2026-10-19)*
    - Under pytest, the function treats `ROOT/etc` existing as "mounted" (`PYTEST_CURRENT_TEST`). That is test logic in product code.
    - Replace it with an injected predicate, as `boot_platform.install_boot_files` does.
    - **2026-11-12, audit:** still open: `install.py` checks `PYTEST_CURRENT_TEST` in two places (lines 241 and 1060).

15. **`nix-collect-garbage` deletes unrooted experiment builds.** *(anomaly, 2026-10-19)*
    - The GC before the 0.18.1 regression deleted the NVMe U-Boot just built, which cost 17 minutes to rebuild.
    - Plan: build experiment inputs with `--out-link` under the scratchpad (GC roots), per AGENTS.md "save a copy".

16. **Show auto-install results in the TUI.** *(gap, 2026-10-20, AArch64 item 9)*
    - The TUI does not read `/run/pre-nixos/auto-install-status`.
    - A refusal such as `REASON=boot-order` (with `MESSAGE=…`) reaches only the consoles and the status file.
    - **2026-11-12, audit:** still open: `tui.py` does not read `auto-install-status`.

17. **Report a second installer boot after a successful install (AArch64 item 9b).** *(plan §3.9)*
    - When the installer boots again on a board that already has an installed system, say on serial and in the TUI that the boot order is the likely cause.

18. **CI tiers 2 and 3, and the mypy ratchet.** *(user request, 2026-10-21; tier 1 is trbarbour/NixOS-boot-image#318)*
    - 2026-10-21: #318 merged; `pre_nixos/boot_order.py` added to `[tool.mypy] files` on #317's branch.
    - Tier 2: x86 VM tests (about 1 h), nightly or on a label.
    - Tier 3: AArch64 image and VM tests under emulation; needs a binary cache (e.g. Cachix) to fit a 6-hour job.

19. **Move the VM fixtures and scripts from PRE_NIXOS_ROOT_KEY/--impure to sites.** *(follow-up, site-settings design D2)*
    - `tests/vm/fixtures.py`, `scripts/manual_vm_debug.py` and `scripts/collect_sshd_pre_nixos_debug.py` still pass the key through the legacy environment fallback.
    - Move them to `--override-input site path:<tmp dir>`, then decide whether to drop the fallback.
    - **2026-11-12, audit:** still open: `tests/vm/fixtures.py`, `scripts/manual_vm_debug.py` and `scripts/collect_sshd_pre_nixos_debug.py` still use `PRE_NIXOS_ROOT_KEY`.

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
    - **2026-11-12, audit:** still open: `pre-nixos-auto-install-ip` still has `StandardOutput = "journal+console"` (`pre_nixos/templates/auto-install-ip.nix`).

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
    - **2026-11-12, audit:** item 30 (`uptime` wrong on a first boot) is folded in here; this item fixes it at the source.

32. **The installed system's generation limit does not follow its ESP size.** *(gap, 2026-10-30, found while doing R-B3)*
    - The ESP is now 1 to 4 GiB (R-B3), at about 200 MB per generation. extlinux keeps 20 generations by default, which overflows a 1 GiB ESP; systemd-boot (x86) has no default limit at all. A full `/boot` makes `nixos-rebuild switch` fail.
    - Consider writing `boot.loader.{systemd-boot,generic-extlinux-compatible}.configurationLimit` into the generated configuration, derived from the planned ESP size. Needs a design debate (fixed headroom per generation vs. measured closure; what happens when a kernel grows).
    - **2026-11-12, audit:** still open: nothing writes `configurationLimit`.

33. **BIOS (legacy) x86 installs fail late: the disks are wiped first, then `nixos-install` fails.** Done except: keep the other boot disks' ESPs in sync (plan D3 (b)). *(defect plus possible feature, 2026-10-31, user question)*
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
    - 2026-10-31: the x86 VM test `test_pre_nixos_vm.py` passed 3/3 at 0.23.1 under SeaBIOS, so provisioning without auto-install is unchanged.
    - **Plan for full support:** `plans/2026-10-31T010024Z-x86-bios-support-plan.md`.
      - Waiting on the user: approve R-B1/R-B4; choose D2 (an EF02 partition always, or only on BIOS); say what disks the old machines have (U2: NVMe cannot boot under BIOS).
      - 2026-10-31 (user): R-B1/R-B4 approved. The old machines have SAS/SATA plus NVMe on PCIe carriers and cannot boot NVMe.
        - Proposed: D2 (a) on x86 only (ESP p1, EF02 p2, data p3).
        - New D6: on BIOS with an NVMe `main`, put `/boot` and GRUB on a SATA/SAS disk.
        - Waiting on the user: confirm D2 and D6; describe the SATA disks (U6).
      - 2026-10-31 (user): D2 and D6 confirmed (the user used to put /boot on the swap disks); the machines have probably one NVMe and a pair of HDDs for swap.
        - **Implemented in 0.24.0**; see plan §7.
        - Remaining: the end-to-end install VM test (item 12), the hardware test on the user's old machines (U1 `pmbr_boot`), and syncing the other boot disks' ESPs (D3 (b)).
    - **2026-11-12, audit:** done apart from one point. The guard (0.23.1) and full BIOS support (0.24.0) are in; the end-to-end install is covered on x86 BIOS (item 12, `tests/vm/test_installed_system_vm.py`); the user's BIOS PC has been installed. **Remaining:** keep the other boot disks' ESPs in sync (plan D3 (b)), so the machine still boots if the first disk fails.

54. **Small disks: `slash` takes everything before swap and `home`.** *(design question, 2026-11-12T02-47Z, found while fixing item 11)*
    - `slash` is planned first, at up to 50 GiB, so a `main` smaller than about 52 GiB has no `home`, and, when swap falls back to `main` (no rotating disks), no swap. Example: one 20 GiB SSD with 16 GiB RAM gives `slash` 19448M and nothing else.
    - Before 0.32.3 these were 4 MiB slivers (item 11), so nothing usable was lost; the question is only whether small systems should reserve room for swap or `home`.
    - For the user: keep `slash` first, or reserve some swap (e.g. up to RAM, or a fraction of `main`) before `slash` on small disks? Needs a short design debate; reqs §2.4 says swap goes in `main` "when capacity allows".

51. **In the VM, stage 2's udev does not auto-load `mptsas` for QEMU's `mptsas1068`** *(anomaly, 2026-11-11, item 48)*.
    - Evidence: the controller is present (`pci 0000:00:04.0: [1000:0054]`), and `modules.alias` maps `pci:v00001000d00000054` to `mptsas`. `modprobe -n -v mptsas` resolves, and `systemd-udev-trigger` ran, yet the driver is unbound and nothing is loaded.
    - On the user's PC (SAS1068E, 1000:0058, 0.27.0 image), stage 2 did load it.
    - Unknown why. Next: `udevadm test /sys/bus/pci/devices/0000:00:04.0` and udevd's debug log in the VM. Since item 48 the driver is in the initrd, so this no longer affects that controller.

## Recently Completed
- 2026-11-12T02-47Z - Item 11 fixed (0.32.3): no sliver LVs.
  - Root cause: `add_lv` gave whatever was left when a request did not fit, so a nearly full VG produced a one-extent (4 MiB) LV. That covered the filed swap case and also `large/data` once swap had filled a small `large`.
  - Now an optional LV is omitted below 1 GiB, or below its request if smaller; `slash` is exempt (R-L1).
  - Tests first: `tests/test_planner_lv_minimum.py`; 24 of its 67 cases failed before the fix, e.g. on a 20 GiB SSD.
  - Found item 54 (`slash` first on small disks). Full text in `docs/task-queue-archive.md`.
- 2026-11-12T02-36Z - **Queue audit** (user request). Each old item was checked against the code, the merged PRs and the notes. Closed:
  - Item 1: Harden BootImageVM diagnostics: an open-ended log of work already done (metadata, transcripts, journals, dmesg, failed units, QEMU version); items 37 and 38 extended it further. No concrete work remains; new gaps get their own items.
  - Item 2: Rebuild the image and rerun the VM regression: now standing practice, every change gets its VM runs (e.g. items 50, 52, 53), so it is not a task.
  - Item 3: Boot timings after configuration changes: no concrete target. The real slowness (item 35, a 60 s DHCP wait) was fixed in 0.25.2 and confirmed on hardware.
  - Item 4: Full suite without skips: the suite runs without skips (2026-10-18); CI covers the unit tests and flake checks (#318); running the VM tests in CI is item 18.
  - Item 5: TUI plan editor coverage: `tests/test_tui.py` drives `_edit_plan` for arrays, LVs, adding an LV and invalid input, and checks that `plan["disko"]` is refreshed.
  - Item 9: Plan and build AArch64 (CM4) support: done. Items 3–9 merged in #315 and later; attempts 1–4 on the CM4 led to fixes (#320, #323, #324, #326, #327), and attempt 4's installed system boots from NVMe with serial and SSH. The remaining CM4 questions are their own items (13, 20–28, 31).
  - Item 10: Old boot-image builds filling the disk: the stale-ISO helper exists (`tests/vm/fixtures.py` `_delete_stale_images`, called before each build), and item 38 added free-space checks and a low-space guard.
  - Item 30: `uptime` about 220 days on a CM4 first boot: root cause confirmed (the utmp boot record is written before the clock is corrected; the board has no RTC). Not pre-nixos's defect; item 31 (use the board's RTC) fixes it at the source, so it is folded into item 31.
  - Item 34: An old SATA SSD planned as an HDD: done in 0.26.0/0.26.1 (R-S3/R-S4: ask about a disk named SSD but reported rotating; `--ssd`/`--hdd`; TUI `T`; the full ATA model from `vpd_pg89`, #336). The SATA VM test passed; the user's PC has since been provisioned and installed (items 44–49).
  - The closed items' full text is kept in `docs/task-queue-archive.md`.
  - Updated with what the audit found: items 6, 7, 8, 11, 12, 14, 16, 19, 29, 31 and 33 (now only the ESP sync remains). The rest are unchanged and still open.
- 2026-11-12T02-05Z - Merged trbarbour/NixOS-boot-image#354 (0.32.2): item 53. The inventory reads each disk's serial where its bus puts it: virtio `serial`, NVMe `device/serial`, SCSI/SAS/SATA `device/vpd_pg80`. Before, only NVMe disks had one (experiment `notes/2026-11-12T014614Z-disk-serial-experiment.md`). Tests first; VM tests passed; Codex clean; CI green.
- 2026-11-12T01-06Z - Merged trbarbour/NixOS-boot-image#353 (0.32.1): item 52. The installed system's `lan` has one network unit, from NixOS's `networking.interfaces.lan`; the shadowed `systemd.network.networks."lan"` is gone (R-N4).
  - Test first: the flake check `installed-network-units` over golden copies of the managed block.
  - The VM install-and-boot test passed; Codex found nothing; CI green.
  - CI first failed to start because a commit subject quoted the skip marker (rule recorded under Rules).
- 2026-11-11T22-48Z - Closed items 35 and 36: both were fixed in trbarbour/NixOS-boot-image#333 (0.25.2) but left on the queue.
  - Item 35: manual runs reuse the boot's LAN configuration (`lan_reuse.ensure_lan`) instead of waiting 60 s for a DHCP lease; the user confirmed 0.35 s on 2026-11-07.
  - Item 36: the plan is printed once at a terminal (`tests/test_cli.py`).
  - The 18–34 s start-up seen in item 50's VM runs is not item 35. This container has no `/dev/kvm`, so the VMs run under QEMU's software emulation.
- 2026-11-11T22-23Z - Merged trbarbour/NixOS-boot-image#352 (0.32.0): item 50. The boot service waits for the set of disks to settle (15 s quiet, at most 120 s; kernel parameters), and a plan records its disks, which are checked again before any question and right before each write. Design `plans/2026-11-11T194943Z-disk-settle-design.md` (R-D1–R-D4).
  - Codex's first review found four issues, each fixed with tests first; the second was clean.
  - VM test passed on the final code. Its first run failed on the test's own timing (recorded in the notes).
  - CI stalled for two hours: the account's free Actions minutes were exhausted, and the user subscribed to GitHub Pro. Found item 53 along the way.
- 2026-11-11T19-48Z - Merged trbarbour/NixOS-boot-image#351 (0.31.0): item 41, the installer adopts the static network settings when it has no address, and the static settings carry DNS servers. Codex's reviews found four issues over two rounds, each fixed with tests first; the third review was clean. The VM test passed on the final code. Found item 52 along the way.
- 2026-11-11T18-37Z - Merged trbarbour/NixOS-boot-image#350 (0.30.0): item 42, `write-image` (a CLI and a TUI: build as the user, write to removable media through a `sudo` helper that re-checks the device and its identity, optional verification; the TUI presents architecture, image type and console with defaults). Codex's reviews found five issues over two rounds, each fixed with tests first; the third review was clean. CI green. A write to real media awaits the user's hardware.
- 2026-11-11T15-03Z - Merged trbarbour/NixOS-boot-image#349 (0.29.2): item 38, the VM harness's disk-space handling. After each build it deletes unreferenced older images, keeping every image the session holds. A VM does not start below `PRE_NIXOS_VM_MIN_FREE_GIB`, and a guard stops QEMU below `PRE_NIXOS_VM_FLOOR_GIB`, both watching the logs' and every VM disk's filesystem. Codex found three issues, each fixed with a test first; its re-review was clean. CI green.
- 2026-11-11T14-41Z - Merged trbarbour/NixOS-boot-image#348 (0.29.1): item 37, a failed image build shows the tail of Nix's stderr. CI green, no Codex findings.
- 2026-11-11T14-21-08Z - Merged trbarbour/NixOS-boot-image#347 (0.29.0): item 48, SAS/RAID controller drivers in the x86 initrd (R-S6; the HBA disk is now found in the initrd, and the test fails on the unfixed image); item 49, degraded arrays reported at login and through mdadm's PROGRAM hook instead of `MAILADDR root` (R-S7; the installed-system VM test fails a member and sees the crit entry and the login warning). CI green, no Codex findings. Follow-ups: items 50 and 51.
- 2026-11-11T02-55-39Z - Merged trbarbour/NixOS-boot-image#346 (0.28.1): fixes #344 (item 47). The boot image masks mdadm's last-resort units (initrd and system), so an array whose member appears late (an HBA disk at 67.8 s on the user's PC) is no longer started degraded, which had dropped that member for good. R-S5, design §7.2.1. Tests first: `tests/vm/test_late_raid_member_vm.py` fails on the unfixed image and passes on 0.28.1, and the flake check `no-degraded-md-start` does the same. RAID regression passes. CI green, no Codex findings. The user still has to re-add `sdc1` on the PC. Follow-ups: items 48 and 49.
- 2026-11-11T01-06-16Z - Merged trbarbour/NixOS-boot-image#345 (0.28.0): item 45, the optional site setting `rootHashedPassword` (R-A1, R-A2), checked by libxcrypt at build time after Codex's finding.
- 2026-11-10T04-02-58Z - Merged trbarbour/NixOS-boot-image#343 (0.27.1): fixes #342 (item 46). An installed system with a static address was unreachable because the installer's DHCP unit `20-lan.network`, copied into the target by an earlier failed DHCP install, overrode the declared network. pre-nixos no longer copies the installer's units and removes leftovers. The end-to-end VM test `tests/vm/test_installed_system_vm.py` (item 12; static 10.0.2.20, stale unit planted) passes on 0.27.1 (`notes/2026-11-10T032558Z-vm-run`) and fails on the unfixed `install.py` with no SSH to the installed system (`notes/2026-11-10T035101Z-vm-run`, 04:23Z). The user confirmed the cause on the PC. CI green, no Codex findings.
- 2026-11-09T14-21-45Z - Merged trbarbour/NixOS-boot-image#341 (0.27.0): R-I1, an automatic install waits for an IPv4 address and a default route (item 44); the x86 image carries reference installed systems and builder tools, fixing #340 (item 43; offline dry run 1751 → 78 configuration derivations). CI green, no Codex findings. Awaits the user's install on the PC.
- 2026-11-08T18-17-10Z - Merged trbarbour/NixOS-boot-image#339 (0.26.2): fixes #338 (cleanup wipes each LV/array while active, then deactivates) and item 40 (only the question while a disk is unconfirmed; messages announced once at a terminal). CI green, no Codex findings. Awaits the user's apply on the PC.
- 2026-11-08T04-04-13Z - Merged trbarbour/NixOS-boot-image#337 (0.26.1): fixes #336, the model now comes from ATA IDENTIFY (`device/vpd_pg89`), so a SATA disk's full model (`G.SKILL 128GB SSD`) reaches the R-S3 rule. CI green, no Codex findings. Item 34 awaits the user's try on the PC.
- 2026-11-07T20-14-14Z - Merged trbarbour/NixOS-boot-image#335 (0.26.0): item 34, R-S3/R-S4. A disk named SSD but reported as rotating waits for the user's answer (TUI or `--ssd`/`--hdd`) before anything touches the disks; the TUI's `T` sets any disk's class. Fixes #334 (VM tests assumed sd names follow attach order). Codex found four issues over two reviews (forced cleanup, explicit partitioning, `T` unreachable disks, `T` list overflow), each reproduced and fixed. CI green. Not yet tried on the user's PC.
- 2026-11-06T13-53-17Z - Merged trbarbour/NixOS-boot-image#333 (0.25.1, 0.25.2): the plan is printed once at a terminal (item 36); manual runs reuse the boot's LAN configuration instead of waiting 60 s for DHCP (item 35). CI green, no Codex findings. Item 35 awaits confirmation on the user's PC.
- 2026-11-01T13-54-41Z - Merged trbarbour/NixOS-boot-image#331 (0.25.0):
  - console variant packages (`bootImageSerial`, `bootImageSdDisplay`), with `-serial`/`-display` in image names when the console is not the format's default;
  - fixes #332: with `--override-input` on a clean tree, names fall back to `<date>-s<hash>` instead of `gunknown`;
  - Codex's finding (the check assumed the default site) was fixed.
- 2026-10-31 - (user request) 0.25.0:
  - image file names carry `-serial`/`-display` when the primary console is not the format's default (the user chose those words over `hdmi`);
  - variant packages `bootImageSerial` and `bootImageSdDisplay` (the user chose variant packages over separate sites), so one command builds all four images;
  - `lib.mkBootImage`/`mkBootConfiguration` take `primaryConsole`, overriding the site;
  - covered by the flake check `image-file-names`.
- 2026-11-01 - (user choice, option 3) #332:
  - with `--override-input` and a clean tree, Nix 2.34 gives `self` no revision (an experiment; a dirty tree keeps `dirtyShortRev`), so images were named `gunknown`;
  - names now fall back to `<lastModifiedDate>-s<hash of narHash>`;
  - the README recommends a wrapper flake for the exact commit;
  - covered by the flake check `source-id`.
- 2026-10-31T05-21-22Z - Merged trbarbour/NixOS-boot-image#330 (0.24.0): x86 installs in legacy BIOS mode with GRUB (R-B4). It included 0.23.1, the guard that refuses BIOS installs before provisioning, now narrowed to machines with no BIOS-bootable disk. x86 VM tests 8/8 under SeaBIOS. A Codex finding (a mixed NVMe/SATA group) was fixed. Next: the user's hardware test on the old machines (U1 `pmbr_boot`); item 12, the end-to-end install VM test, is still open.
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
