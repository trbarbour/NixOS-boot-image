# Primary console per image (design)

**User request (2026-10-23):** "There is no one console order that suits all machines. Most of my CM4s are headless, so will only have the serial console. Some mini-PCs have no serial console."
- The image should be configurable: serial or HDMI primary.
- Default: serial for AArch64, HDMI for x86.

**Trigger:** CM4 attempt 2 (#323). On the installed system, systemd's status lines and the initrd's emergency shell went to HDMI (`console=tty0` last), so a headless CM4 showed nothing after `Starting kernel ...`.

## 0. Facts (experiments)

| # | Question | Result |
|---|---|---|
| F1 | Which `console=` is primary (`/dev/console`)? | The **preferred** one. A repeated `console=` sets `preferred_console` to the existing entry (`kernel/printk/printk.c:2534–2539`, Linux 6.18.56). |
| F2 | Does appending the serial console once more make it primary, in practice? | **Yes.** In QEMU, with the image's x86 kernel and a busybox initramfs that prints `/proc/consoles` to `/dev/console`:<br>• `console=ttyS0,115200n8 console=tty0`: nothing on serial (tty0 is `/dev/console`);<br>• the same plus `console=ttyS0,115200n8` at the end: `ttyS0 -W- (EC p a)`, where `C` marks `/dev/console`, and init's output arrived on serial. |
| F3 | Current kernel parameters | ISO: `console=ttyS0,115200n8 console=tty0` (display primary). SD (stock): `console=ttyS0,115200n8 console=ttyAMA0,115200n8 console=tty0` (display primary). |
| F4 | Installed system | `_select_console_kernel_params` keeps every booted console at its **last** occurrence (R-C1), so it inherits whatever primary the image booted with. |
| F5 | The Pi's serial console | `ttyS0`, the mini UART (`<<< Welcome … - ttyS0 >>>` on the CM4). |

## 1. Choices (debate; the user chose D1 and D2)

### D1. What the setting controls
- **(a) The boot image's own kernel command line**, with the installed system inheriting it via R-C1. **Chosen.**
  - Gives one rule and one place.
  - The installer's own systemd output and emergency shell follow the setting too.
  - Costs an amendment to R-P2: the SD image's console **order** may differ from stock. The set of consoles stays the same.
- **(b) The installed system only:** R-P2 is unchanged, but R-C1 has to be amended, and a headless installer stays blind.

### D2. How it is supplied
- **(a) A site setting `primaryConsole = "serial" | "display"`**, beside `rootKey` and `autoInstall`: pure and validated. **Chosen.**
  - When unset, the default depends on the format: `"serial"` for `sd`, `"display"` for `iso`.
- **(b) The same, plus a boot-time kernel-parameter override:** rejected for now. U-Boot's extlinux menu is hard to edit headless, and nothing asks for it.

### D3. How "serial primary" is expressed
- **(a) Append the image's serial console once more** (`lib.mkAfter [ "console=ttyS0,115200n8" ]`), per F1/F2. **Chosen.**
  - Every stock parameter stays.
  - R-P2's check becomes "stock, plus the appended serial console when serial is primary".
- **(b) `mkForce` the whole `boot.kernelParams`:** this would drop or duplicate other stock parameters (`nohibernate`, `loglevel=7`, …).
- **"display primary":** nothing is appended, because both stock lists already end with `console=tty0`. A check asserts that the last console is `tty0`.

### D4. Which serial console
`console=ttyS0,115200n8` on both formats: COM1 on x86, the mini UART on the Pi (F5).

## 2. Requirements changes
- **R-P2:** pre-nixos must not change the stock image's boot chain, or the **set** of kernel consoles. Their **order** follows R-C2.
- **New R-C2:** each image's primary console is a build-time choice, serial or display. Defaults: serial on AArch64, display on x86_64. The installed system keeps it (R-C1).

## 3. Tests
- **Flake check `primary-console`:** for each format, with the setting unset (the default), `"serial"` and `"display"`, the last `console=` in `boot.kernelParams` is the expected one.
- **Updated flake check `stock-aarch64-boot-settings`:** ours equals stock, except for the one appended serial console when serial is primary.
- **`site-validation`:** `primaryConsole = "hdmi"` (not a known value) fails evaluation.
- **pytest:** the installed system keeps serial primary when the boot cmdline ends with the appended `ttyS0` (R-C1, F4).

## 4. Unknowns
On `qemu virt` (the AArch64 VM tests), the serial port is `ttyAMA0` and there is no `ttyS0`, so the preferred console never registers.
- Expected: the AArch64 VM tests are unaffected, because their getty and login use `ttyAMA0`, which stays registered.
- To check: run the AArch64 VM test after the change.
