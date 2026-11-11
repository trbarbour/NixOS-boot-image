# Experiment: does Linux's mptsas find a disk on QEMU's mptsas1068? (task queue item 48)

_Run 2026-11-11, finished 05:09Z. Scripts and serial logs: `notes/2026-11-11T053000Z-mptsas-wwn-experiment/`._

## Question
With 0.29.0 (`mptsas` in the initrd), `tests/vm/test_hba_disk_vm.py` saw the driver load in the initrd (24.1 s) and the controller come up (`scsi host3: ioc0: LSISAS1068 A0`), but no disk behind it. Is it the image, or the way the harness attaches the disk?

## Method
The 0.29.0 ISO was booted by hand: QEMU 10.2.4, SeaBIOS, `-device mptsas1068`, one 1 GiB raw disk as `scsi-hd,bus=mptsas0.0,serial=hbahdd`, and nothing else.
- Variants: A `scsi-id=0` (as the harness did), B `scsi-id=1`, C `scsi-id=0,wwn=0x5000c500a0b0c0d1`.
- 45 s after login: `dmesg | grep mpt|sas|sd`, then `lsblk -dnro NAME,SERIAL`.

## Observations
- **A:** the driver loads at 20.0 s and the controller comes up. No `attaching` line, and no disk.
- **B:** no result. The script timed out at login (inconclusive).
- **C:** `mptsas: ioc0: attaching ssp device: fw_channel 0, fw_id 0, phy 0, sas_addr 0x5000c500a0b0c0d1` at 22.4 s, then `sd 0:0:0:0: [sda] Attached SCSI disk` at 24.1 s. `lsblk` shows `sda hbahdd`.
- (All three end in a pexpect timeout after the result, from the script's second `expect`. That is cosmetic.)

## Conclusion
Linux's `mptsas` discovers a disk on QEMU's `mptsas1068` only when the disk has a SAS address (`wwn`). The image was right; the harness was not. `tests/vm/scsi_disks.py` now gives each `Bus.MPTSAS` disk a deterministic `wwn` (`sas_wwn`).

Real SAS and SATA disks behind a real HBA have addresses, so this concerns the emulation only.
