# AArch64 plan item 9: boot-order verification (design)

Parent plan: `plans/2026-10-18T142135Z-aarch64-cm4-boot-image-plan.md` (§3.9 and §6, item 9).
Requirement: **R-B2**, the installed system must boot first, with the SD card still inserted. That depends on the EEPROM `BOOT_ORDER`.
User decision (2026-10-18): verify now; refusing to install on a wrong order is acceptable; automating the change comes later, with separate approval.

## 0. Facts this design rests on

| Fact | Source |
|---|---|
| `BOOT_ORDER` digits, read right to left, up to 8: 0 = SD card detect, 1 = SD (eMMC on CM4), 2 = network, 3 = rpiboot, 4 = USB-MSD, 5 = BCM-USB-MSD, 6 = NVMe, 7 = HTTP, e = stop, f = restart. Empty means `0xf41`. | **E11**: raspberrypi/documentation `eeprom-bootloader.adoc` @ `ddea98e` (2026-10-13) |
| The bootloader config supports `config.txt` conditional filters (except EDID). | the same document, line 25 |
| The running bootloader's configuration can be read without `vcgencmd`: follow `/sys/firmware/devicetree/base/aliases/blconfig` to an OF node, find the `/sys/bus/nvmem/devices/*` whose `of_node` is that node, and read its `nvmem` file as text. | **E12**: `rpi-eeprom-config.read_current_config()` (raspberrypi-eeprom 2026.05.11); user's CM4, 2026-10-18 |
| The user's CM4 runs EEPROM 2022-11-04 with `BOOT_ORDER=0xf2516` in effect (it tried NVMe, then SD). | serial log `docs/test-reports/2026-10-20T031705Z-…` |

## 1. Design choices (debate)

### D1. How to read the configuration
- **Run `rpi-eeprom-config`:** reuses the upstream tool, but `raspberrypi-eeprom` is **213 MB** (it bundles EEPROM images) and adds a Python dependency to the image, for about 10 lines of logic.
- **Reimplement the `blconfig` read:** about 20 lines, with the source cited, and testable against a fake sysfs tree.
- **Choice: reimplement.** The trailing NUL in the device-tree alias string is stripped; upstream instead relies on a substring match.
- An unreadable configuration (no alias, no matching nvmem device, unreadable file) gives **unknown**, never "fine".

### D2. How to interpret the configuration
- Parse `[section]` lines as `config.txt` does. Lines before the first section, and lines under `[all]`, apply unconditionally.
- A `BOOT_ORDER` under any other filter (`[cm4]`, `[pi4]`, `[gpio…]`, `[partition=…]`, `[none]`) may or may not apply. Evaluating filters would mean reimplementing the firmware's filter engine.
- **Choice:**
  - the last unconditional `BOOT_ORDER` wins;
  - a `BOOT_ORDER` in any conditional section makes the result **unknown**, and the message names the section;
  - no `BOOT_ORDER` at all means the documented default `0xf41`.
- Value syntax: `0x`-prefixed hex, or decimal, per the docs' examples. Anything else is unknown.

### D3. The rule
- The order is evaluated until the first `f` (restart) or `e` (stop), since later digits are never reached.
- The **target's mode** must occur, and it must come **before SD** (1, or 0 = SD card detect).
- Why SD: the installer is an SD image.
- Target class, from the disk that **actually backs the mounted `ROOT/boot`** (`stat` gives the device number, `/sys/dev/block/MAJ:MIN` gives the partition, its parent is the disk). Both auto-install and the manual-install entry point use this, and the latter may have no storage plan:
  - `nvme*` gives NVMe (6);
  - anything else is **unsupported** for now. eMMC shares mode 1 with SD, so no order can prefer it over the card. USB targets are outside the user's scope.
  - The result is refused, with the reason.
- `0xf2516` and `0xf25146` pass (§8.2 of the plan). `0xf41` (no NVMe), `0xf1` (no NVMe) and `0xf461` (NVMe after SD) are refused. `0xf16f6` passes: it tries NVMe first, and the `f` makes the later digits unreachable.

### D4. Where it runs, and what refusing does
- In `auto_install`, right after the boot setup is parsed, **only for `rpi4-uboot-extlinux`**, and before `nixos-generate-config`, so nothing is installed.
- Storage provisioning has already run by then. It only touches empty disks, and it is not what R-B2 is about.
- **On refusal:**
  - `auto-install-status` gets `STATE=failed REASON=boot-order`, with details: the value found (or why it is unknown), the target mode, and a suggested value;
  - the message is printed and broadcast to the consoles (serial included);
  - **correction (implementation):** the TUI does **not** read `auto-install-status` today. Showing auto-install results in the TUI is queued (task queue item 16). The serial broadcast meets R-B2's visibility need, because unattended installs are watched on serial.
- **The suggested value** puts the target mode in front of the effective order, minus any other copy of it: `0xf41` gives `0xf416`. It is advice only. pre-nixos never writes the EEPROM (option (c) is deferred).
- **The manual-install entry point** (`pre-nixos-install-boot-files`) runs the same check and exits nonzero, unless `--ignore-boot-order` is given, for operators who know better.

### D5. Types
- `BootMode` is an `IntEnum` of the documented digits. An unknown digit is kept as raw `int` and reported, not dropped.
- `BootOrderReading = Known(order: tuple[int, ...], source) | Unknown(reason)`: a tagged union, so "unknown" cannot be mistaken for "OK".
- `check(reading, target) -> Verdict`, where the verdict is `Ok` or `Refused(reason, suggestion)`. It is a pure function, which the tests use directly.

## 2. Tests
- **Unit:**
  - parsing, with the user's real configuration text as a fixture, plus default, conditional and malformed inputs;
  - nibble decoding;
  - the rule, over the D3 table;
  - the suggestion;
  - the `blconfig` reader, over a fake sysfs tree;
  - `auto_install` stopping before `nixos-generate-config`;
  - the CLI exit codes.
- **VM (qemu virt):** there is no `blconfig` there. The reading must be `Unknown`, so a qemu install would be refused. That proves fail-safe behaviour, not the happy path. Covered by a unit test of the reader against an empty tree; an extra VM boot isn't worth it.
- **Hardware (user, item 10):** on the CM4, `pre-nixos` reports `Known(0xf2516)` and proceeds.

## 3. Deferred
- **9b:** a second installer boot after a successful install should say that the boot order is the likely cause. That is task queue work, separate from the check.
- **(c):** writing `BOOT_ORDER` automatically, which needs E13 and E14 and the user's approval.
