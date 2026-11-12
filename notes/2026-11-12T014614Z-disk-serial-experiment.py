"""Experiment (item 53): which sysfs files hold each bus's disk serial?"""
import sys, re, time
from pathlib import Path
import pexpect
sys.path.insert(0, "/home/user/NixOS-boot-image")
from tests.vm.boot_medium import boot_medium_args
from tests.vm.scsi_disks import Bus, ScsiDisk, scsi_disk_args

S = Path(sys.argv[1]); iso = Path(sys.argv[2])
def img(name):
    p = S / f"{name}.img"
    with p.open("wb") as f: f.truncate(64 * 1024**2)
    return p
disks = [
    ScsiDisk(img("scsi"), rotational=True, serial="SCSISER1", model="SCSIDISK"),
    ScsiDisk(img("sata"), rotational=True, serial="SATASER1", model="SATADISK", bus=Bus.SATA),
]
cmd = ["qemu-system-x86_64", "-m", "2048", "-smp", "2", "-display", "none", "-no-reboot",
       "-serial", "stdio", *boot_medium_args(iso, None), *scsi_disk_args(disks),
       "-drive", f"file={img('virtio')},if=none,id=vd,format=raw",
       "-device", "virtio-blk-pci,drive=vd,serial=VIRTSER1",
       "-drive", f"file={img('nvme')},if=none,id=nvm,format=raw",
       "-device", "nvme,serial=NVMESER1,drive=nvm",
       "-nic", "none"]
child = pexpect.spawn(cmd[0], cmd[1:], encoding="utf-8", codec_errors="ignore", timeout=900)
child.logfile_read = (S / "serial.log").open("w")
child.expect(r"nixos@nixos:~\]\$", timeout=1200)
time.sleep(60)  # let udev settle and late disks appear
probe = r'''for d in /sys/block/*; do n=${d##*/}; case $n in loop*|sr*|zram*) continue;; esac; echo "== $n -> $(readlink $d)"; for f in serial device/serial device/vpd_pg80 device/wwid wwid device/device/serial; do [ -e "$d/$f" ] && printf '  %s: %s\n' "$f" "$(tr -d '\000' < "$d/$f" | tr -c '[:print:]' ' ' | head -c 80)"; done; done; echo PROBE-DONE'''
child.sendline(probe)
child.expect("PROBE-DONE\r?\n.*PROBE-DONE", timeout=300)
print(child.before + child.after)
child.sendline("sudo poweroff")
child.expect(pexpect.EOF, timeout=300)
