# Where Linux exposes a disk's serial, by bus (task queue item 53)

_2026-11-12 01:46:14Z, experiment script `notes/2026-11-12T014614Z-disk-serial-experiment.py`._

**Question:** which sysfs file holds the serial for each kind of disk? `inventory.enumerate_disks` read only `/sys/block/<d>/device/serial`, and item 50's VM run showed "no serial" for a virtio disk that had one.

**Method:** booted the 0.32.1 ISO in QEMU (TCG) with one 64 MiB disk per bus, each with a known serial:
- virtio-scsi `scsi-hd`, serial SCSISER1;
- AHCI `ide-hd` (SATA), serial SATASER1;
- `virtio-blk-pci`, serial VIRTSER1;
- `nvme`, serial NVMESER1.

It then listed `serial`, `device/serial`, `device/vpd_pg80`, `device/wwid` and `wwid` for each disk. The LSI SAS (`mptsas`) disks use the same `sd` driver as virtio-scsi, so the SCSI disk stands for them.

The first two attempts failed in the script, not in the guest:
1. QEMU 10 refuses `serial=` on `-drive`; it goes on `-device virtio-blk-pci`.
2. The prompt pattern did not allow for the prompt's escape codes.

**Result** (non-printing bytes shown as spaces):

| Disk | File holding the serial | Value |
|---|---|---|
| `nvme0n1` | `device/serial` | `NVMESER1` plus trailing spaces |
| `sda` (SCSI) | `device/vpd_pg80` only | header, then `SCSISER1` |
| `sdb` (SATA) | `device/vpd_pg80` only | header, then `SATASER1` plus trailing spaces |
| `vda` (virtio) | `serial` (on the block device, not `device/`) | `VIRTSER1` |

- No SCSI or SATA disk has `device/serial`.
- `device/wwid` is empty for the virtio-scsi disk, and for SATA is a composite (`t10.ATA <model> <serial>`), so it is not the serial.

**Conclusion:**
- Item 53 is wider than virtio: SCSI, SAS and SATA disks also had no serial in the inventory, so R-D3 could not tell two same-size disks under one name apart on the user's PC either.
- The serial is, in order: `/sys/block/<d>/serial` (virtio), `device/serial` (NVMe), then the Unit Serial Number VPD page `device/vpd_pg80` (SCSI, SAS, SATA through libata).
- That page (SPC) is: byte 1 = page code 0x80, bytes 2-3 = page length, big-endian, then that many bytes of ASCII serial, which may be padded with spaces.
