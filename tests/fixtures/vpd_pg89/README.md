# ATA Information VPD pages (`/sys/block/<d>/device/vpd_pg89`)

Captured 2026-11-08 from Linux 6.18.56 (the image's kernel) in QEMU 8.2.2, on
`ich9-ahci` disks (`ide-hd`). Issue #336; task queue item 34.

| File | QEMU disk | `device/model` (sysfs) | Model in the page |
|---|---|---|---|
| `qemu-ahci-gskill-128gb-ssd.bin` | `model="G.SKILL 128GB SSD",rotation_rate=0` | `G.SKILL 128GB SS` (truncated) | `G.SKILL 128GB SSD` |
| `gskill-128gb-ssd-user-pc.bin` | none: the user's drive on the first BIOS PC (0.26.0 image, `od -A d -t x1 -v`, 2026-11-08) | `G.SKILL 128GB SS` (truncated) | `G.SKILL 128GB SSD` |
| `qemu-ahci-st3750528as.bin` | `model="ST3750528AS",rotation_rate=7200` | `ST3750528AS` | `ST3750528AS` |

Layout: a 4-byte header (byte 1 = 0x89), SAT vendor/product/revision, the ATA
device signature, the command code at byte 56 (0xEC, IDENTIFY DEVICE), then
512 bytes of IDENTIFY data from byte 60. The model is IDENTIFY words 27–46,
each word byte-swapped. Captured as in `notes/2026-11-08T*-u2-sata-model-truncation.md`.

In `gskill-128gb-ssd-user-pc.bin` the drive's serial number (IDENTIFY words
10–19) is blanked with spaces, so the IDENTIFY checksum (word 255) no longer
matches; pre-nixos does not check it. Its rotation rate (word 217) is 0, "not
reported", which is why the kernel calls the drive rotating.
