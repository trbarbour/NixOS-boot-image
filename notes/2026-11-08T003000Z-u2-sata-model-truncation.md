# U2: a SATA disk's model in sysfs is truncated to 16 characters (#336)

_Experiment run 2026-11-08 (UTC); recorded 2026-11-08 00:30:18Z. Task queue item 34; trbarbour/NixOS-boot-image#336._

**User report:** with 0.26.0, `pre-nixos --plan-only` on the first BIOS PC did not ask about the SSD. The user noted that only the `/dev/disk/by-id` name contains "SSD".

**Hypothesis:** for a SATA disk, `/sys/block/<d>/device/model` is the SCSI INQUIRY product field that libata fills in, 16 characters long. `G.SKILL 128GB SSD` has 17 characters, so it would read `G.SKILL 128GB SS`.

**Set-up (isolated from pre-nixos):**
- as U1 (`notes/2026-11-07T165520Z-u1-scsi-unreported-rotation.md`): QEMU 8.2.2 (TCG), the image's kernel (Linux 6.18.56), and a busybox initramfs;
- this time loading libata, libahci and ahci;
- disks: `ich9-ahci` with `ide-hd,model="G.SKILL 128GB SSD",rotation_rate=0` and `ide-hd,model="ST3750528AS",rotation_rate=7200`.

Init script:
```sh
#!/bin/busybox sh
/bin/busybox mkdir -p /proc /sys /dev
/bin/busybox mount -t proc proc /proc
/bin/busybox mount -t sysfs sys /sys
/bin/busybox mount -t devtmpfs dev /dev
for m in scsi_common scsi_mod sd_mod libata libahci ahci; do /bin/busybox insmod /mods/$m.ko || echo "skip $m"; done
/bin/busybox sleep 4
for d in /sys/block/sd*; do
  n=$(/bin/busybox basename $d)
  echo "U2 $n rotational=$(/bin/busybox cat $d/queue/rotational) vendor=[$(/bin/busybox cat $d/device/vendor)] model=[$(/bin/busybox cat $d/device/model)]"
  echo "U2 $n attrs: $(/bin/busybox ls $d/device | /bin/busybox tr '\n' ' ')"
  if [ -r $d/device/vpd_pg89 ]; then
    echo "U2 $n vpd_pg89 bytes=$(/bin/busybox wc -c < $d/device/vpd_pg89)"
    /bin/busybox od -A n -v -t x1 $d/device/vpd_pg89 | /bin/busybox sed "s/^/U2HEX $n /"
  fi
done
/bin/busybox poweroff -f
```

**Result:**
```
U2 sda rotational=1 vendor=[ATA     ] model=[G.SKILL 128GB SS]
U2 sda vpd_pg89 bytes=572
U2 sdb rotational=1 vendor=[ATA     ] model=[ST3750528AS     ]
U2 sdb vpd_pg89 bytes=572
```

`vpd_pg89` (572 bytes; saved as `tests/fixtures/vpd_pg89/qemu-ahci-*.bin`) decodes as follows. IDENTIFY data starts at byte 60; the model is words 27–46, each byte-swapped.
- `sda`: `G.SKILL 128GB SSD`
- `sdb`: `ST3750528AS`

**Conclusion:** the hypothesis holds.
- sysfs `device/model` drops the "D", so the R-S3 rule never fired on the user's disk.
- The full ATA model is in `device/vpd_pg89`, readable without udev.
- The VM test passed with 0.26.0 because its stand-in was virtio-scsi, where the product field is the whole name (8 characters, "TEST SSD").
