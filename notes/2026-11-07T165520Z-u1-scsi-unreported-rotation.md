# U1: a QEMU SCSI disk with no rotation rate and an "SSD" model name

_2026-11-07 16:55:20Z. Task queue item 34; plans/2026-11-07T161535Z-ssd-model-name-design.md, U1._

**Question:** does a QEMU `scsi-hd` with `rotation_rate=0` (none reported) and `product="TEST SSD"` look, to the guest, like the user's G.SKILL drive (`rotational = 1`, model containing "SSD")?

**Set-up (isolated from pre-nixos):**
- QEMU 8.2.2 (TCG);
- the image's kernel, Linux 6.18.56 (`/nix/store/l94h0skn…-linux-6.18.56/bzImage`);
- a busybox initramfs that loads virtio_pci, scsi_mod, sd_mod and virtio_scsi from the matching modules package, then prints sysfs;
- three disks on one virtio-scsi controller.

Init script:
```sh
#!/bin/busybox sh
/bin/busybox mkdir -p /proc /sys /dev
/bin/busybox mount -t proc proc /proc
/bin/busybox mount -t sysfs sys /sys
/bin/busybox mount -t devtmpfs dev /dev
for m in virtio_ring virtio virtio_pci_legacy_dev virtio_pci_modern_dev virtio_pci scsi_common scsi_mod sd_mod virtio_scsi; do
  [ -f /mods/$m.ko ] && /bin/busybox insmod /mods/$m.ko || echo "skip $m"
done
/bin/busybox sleep 3
for d in /sys/block/sd*; do
  echo "U1 $(/bin/busybox basename $d) rotational=$(/bin/busybox cat $d/queue/rotational) model=[$(/bin/busybox cat $d/device/model)] vendor=[$(/bin/busybox cat $d/device/vendor)]"
done
/bin/busybox poweroff -f
```

**Result:**
```
U1 sda rotational=1 model=[TEST SSD        ] vendor=[QEMU    ]
U1 sdb rotational=0 model=[TEST SSD        ] vendor=[QEMU    ]
U1 sdc rotational=1 model=[QEMU HARDDISK   ] vendor=[QEMU    ]
```

**Conclusion:** yes.
- `rotation_rate=0` gives `rotational = 1`: the kernel's default when no rate is reported, as with the user's drive.
- `product=` sets `device/model`, padded to 16 characters (pre-nixos strips it).
- `rotation_rate=1` gives `rotational = 0`, as in the RAID spike.

The VM test can stand in for the user's drive with `rotation_rate=0` and `product="TEST SSD"`.
