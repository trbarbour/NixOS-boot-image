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
- **Resolved (2026-10-23 02:51Z):** `tests/vm/test_aarch64_boot.py` passed 4/4 at 0.22.0, commit b73f41e (17 min). The cmdline ends with the appended `ttyS0`, and login and SSH work on `qemu virt`.

## 5. Limitation: which serial device (user question, 2026-10-23)

The appended device is **fixed per format** (D4), not detected.

**Evidence for `ttyS0` on the CM4**, from the attempt-2 serial log `docs/test-reports/2026-10-22T154500Z-cm4-item10-attempt2-serial.txt`:
- `fe215040.serial: ttyS0 … is a 16550` (`bcm2835-aux-uart`, the mini UART on GPIO 14/15, enabled by `enable_uart=1`) prints the kernel log;
- `serial-getty@ttyS0` and `<<< Welcome … - ttyS0 >>>` appear in the user's serial capture;
- the PL011 is `ttyAMA1` (`fe201000.serial`), owned by Bluetooth (`serial serial0: tty port ttyAMA1 registered`, `hci_uart_bcm serial0-0`);
- **no `ttyAMA0` exists**, so the stock `console=ttyAMA0` names no device on this board.

**Evidence for `ttyS0` on x86:** it is COM1 by convention, and the ISO already used it. There is no hardware evidence from the user's mini-PCs.

**Where the guess is wrong:**
- a Pi with `dtoverlay=disable-bt` or `miniuart-bt`: the GPIO UART becomes the PL011, `ttyAMA0`;
- a Pi 5: `ttyAMA10`;
- an x86 machine with the port on COM2 (`ttyS1`), on a PCIe card or AMT serial-over-LAN (often `ttyS4`), or on USB.

In those cases the preferred console names an absent device. Which console then becomes `/dev/console` has not been determined (the `qemu virt` VM test passed, but did not check `/proc/consoles`).

**F6 (experiment, 2026-10-23): a preferred console that the machine lacks.** Same QEMU set-up as F2 (an x86 machine, so no `ttyAMA0`).
- `console=ttyS0,115200n8 console=tty0 console=ttyAMA0,115200n8`: init's output did **not** reach serial. `/dev/console` fell back to `tty0` (the first registered console becomes the head, `printk.c:4139–4142`), although `ttyS0` was listed.
- The same with `ttyS0` last: `ttyS0 (EC …)`.
- So the kernel does not fall back to another listed serial console. Appending every stock serial console would give the display on any board that lacks the last one.

**Stock lists:**
- The ISO lists one serial console, `ttyS0`.
- The SD image lists two. nixpkgs' comment says `ttyS0` is "for Tegra (Jetson TX1)" and `ttyAMA0` "for QEMU's -machine virt". On the CM4, `ttyS0` is the mini UART, and no `ttyAMA0` exists (§5).

## 6. Decision: the serial console comes from the format's own list (user, 2026-10-23)

**User:** don't hard-code `ttyS0`; use the serial device the stock kernel command line already contains. Overlays and other device changes happen on installed systems, whose owners adjust the command line themselves.

**Supersedes D4.** The kernel has no "the board's serial console" name. It offers `tty<n>`, named ports, `<DEVNAME>:<n>.<n>` and `uart8250,…` (kernel-parameters.txt). DT `stdout-path` is used only when there is no `console=` at all (`drivers/of/base.c:2002`).

**Rule (`flake.nix`: `serialConsoleFor`):**
- A format's **consoles** are the `console=` entries of the image evaluated with display primary, so nothing is appended.
- Its **serial consoles** are the entries that are not `tty<n>`.
- If the format names one (`formats.<f>.serialConsole`), it must be in that list; otherwise evaluation fails.
- If it names none, the list must hold exactly one serial console, which is used; otherwise evaluation fails.

**Per format:**
- **ISO:** names none. The only serial console is `ttyS0,115200n8`.
- **SD:** names `ttyS0,115200n8`. The stock list has `ttyS0` and `ttyAMA0` (F6), and R-P1's Pi 4 family uses `ttyS0` (§5).

**Defaults:** `primaryConsole` defaults are now per format too (ISO `display`, SD `serial`). The module on its own defaults to `display`, which keeps the stock order.

**Tests:**
- The flake check `serial-console-choice` covers both formats and the rule's error cases.
- Evaluating the SD image with `serialConsole = "ttyS1,…"` fails: "not among its consoles". Evaluating it with none named fails: "name one".
