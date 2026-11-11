# Writing an image to removable media (design)

_2026-11-11T18:10:58Z. Task queue item 42._

**User request (2026-11-08):** a target that builds the chosen image and writes it to a chosen device, perhaps as a TUI. It must refuse non-removable devices, and default to a USB stick for the ISO and an (u)SD card for the SD image. Verification would be nice, as an option.

**User decisions (2026-11-11):**
- D1: a CLI **and** a TUI. "DRY implies that the TUI calls the CLI."
- D2: the device rules below.
- D3: build from a site (or take `--image`).
- D4: optional verification.
- D5: "I don't want to run the build as root, and I would prefer not to have to do separate building and writing." The privileged part is a helper run with `sudo`.
- D6: Linux only (not contested).

## 1. Requirements (traceability)

- **R-W1:** one command builds the chosen image (ISO or SD) from a site, as the invoking user, and writes it to a chosen device. `--image PATH` writes an image that is already built.
- **R-W2:** only removable media are accepted: the kernel's `removable` flag, or a USB or MMC/SD transport (USB SSD enclosures often report `removable = 0`). Always refused:
  - SATA, NVMe and virtio disks;
  - any device with a mounted partition;
  - the device holding `/` or `/nix`.
- **R-W3:** before writing, the device's model, serial and size are shown, and the user types the device name to confirm (`--yes` skips this for scripts).
- **R-W4:** `--verify` reads back exactly the image's length, bypassing the page cache, and compares SHA-256 with the image's own (decompressed) content.
- **R-W5:** only the write step runs as root. It re-checks R-W2 itself and does not trust the unprivileged side.
- **R-W6:** the TUI offers the same choices and runs the CLI to do the work. There is one implementation of the rules and of the write.

## 2. Design

### Structure (`write_image/`, its own package; not in the boot image)
- `devices.py` (pure): reads a sysfs root (`/sys/block/<d>/{removable,size,device/model,…}`), the transport (from the `/sys/block/<d>` symlink target: `/usb`, `/mmc`), the mounted sources (`/proc/self/mounts`) and the system devices.
  - Returns `Candidate(name, model, serial, size_bytes, transport, removable)` for an eligible device, or a `Refusal(name, reason)`.
  - Typed; the same function serves the list, the CLI's check and the helper's re-check.
- `image.py`: finds the image file in a build output (`iso/*.iso`, `sd-image/*.img.zst`). It reports the decompressed size and SHA-256 by streaming, through `zstd -dc` for `.zst`.
- `writer.py`: copies a byte stream to a device in 4 MiB blocks with a progress callback, then calls `fsync`. Verification flushes the device's cache (`BLKFLSBUF`, plus `posix_fadvise(DONTNEED)`) and hashes exactly the image's length read back.
- `helper.py` (runs as root through `sudo`): `--device`, `--image`, `--verify`.
  - It re-runs the eligibility check, opens the device with `O_EXCL` (Linux refuses if it is in use), then writes and verifies.
  - Exit codes: 0 written, 2 refused, 3 verification failed, 1 other error.
- `cli.py` (`write-image`):
  - `--list [--json]` lists eligible devices and refusals.
  - Otherwise it resolves the image (with `--site DIR`, `nix build .#bootImage|.#bootImageSd --override-input site path:DIR` as the user; or `--image PATH`) and chooses the device (`--device`, or a numbered prompt).
  - It confirms by typed name (R-W3), then runs the helper: directly if already root, else `sudo <python> -I -c <bootstrap> …`, where the bootstrap imports the helper from the tool's own (store) directory.
- `tui.py` (curses):
  - Format, site directory, device (from `write-image --list --json`), verify.
  - Then it ends curses and runs `write-image` with those arguments and without `--yes`, so the CLI asks for the typed confirmation, shows the build, prompts for the `sudo` password and shows progress in the plain terminal.
- **Flake:** `apps.<system>.write-image` and `.write-image-tui`, with `zstd` from the store on `PATH`. The host's `sudo` stays on `PATH` (a setuid wrapper cannot come from the store).

### Defaults
- `--format iso` (x86) lists USB devices first; `--format sd` lists MMC/SD first. Both accept any eligible device.

### Why not a group or udisks (D5)
- **A group with write access to removable disks** (a udev rule) would give any program the user runs standing write access to any inserted stick, and needs setup on each build host. The `disk` group is effectively root.
- **udisks/polkit:** its default policy for raw writes varies (usually it asks for admin authentication), it is absent on headless hosts, and it adds a D-Bus dependency.

### TUI presentation (user request, 2026-11-11)
- The user asked: "I would like the TUI to do a nice job of presenting the options for machine architecture, console and image type, with sensible defaults."
- `write_image/choices.py` (pure) is the single description, used by both the CLI and the TUI:
  - architectures: x86_64 PC (default), AArch64 Raspberry Pi 4/CM4;
  - image types per architecture: ISO, SD-card image;
  - consoles, with the R-C2 default per architecture (display on x86_64, serial on AArch64);
  - the flake attribute for each (format, console): `bootImage`, `bootImageSerial`, `bootImageSd`, `bootImageSdDisplay`;
  - the summary text.
- The CLI takes `--console default|display|serial`.
- The TUI's menus open on the default, mark it "(default)", and explain each option in one line. A summary screen comes before the CLI runs.

## 3. Tests
- Fake sysfs trees (`tests/write_image/`): a USB stick (removable), a USB SSD (removable = 0, USB transport), an SD card in an MMC slot, a SATA disk, NVMe, virtio, a mounted stick, the root disk. Each gets the expected candidate or refusal (R-W2).
- Writing to a temporary file, then verifying; a corrupted byte fails verification (R-W4). A `.zst` image is streamed through `zstd`.
- CLI flow with a fake runner:
  - the build command (as the user);
  - the helper command (through `sudo`, with absolute paths);
  - a refusal when the typed name is wrong (R-W3);
  - `--yes`;
  - `--list --json`.
- The helper refuses an ineligible device even when the CLI asked for it (R-W5).
- The TUI's choices map to the CLI's arguments (a pure function), without `--yes` (R-W6).
- Real hardware: the user.
