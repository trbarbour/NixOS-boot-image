"""Spike for queue item 11: does disko create a RAID-1 under mdadm 4.4 at boot?

Guest: empty 4G virtio SSD (vda) + two equal 2G scsi-hd disks with
rotation_rate=7200 (expected rotational=1) -> planner: md0 raid1 for swap VG.
"""
import sys, time
from pathlib import Path
sys.path.insert(0, "/home/user/NixOS-boot-image")
import pexpect
from scripts.manual_vm_debug import describe_boot_image, allocate_ssh_port, prepare_disk_image
from tests.vm.controller import BootImageVM

OUT = Path(sys.argv[1]); ISO = Path(sys.argv[2]); OUT.mkdir(parents=True, exist_ok=True)
artifact = describe_boot_image(ISO, public_key=None)
vda = prepare_disk_image(OUT / "vda.img")
hdds = [prepare_disk_image(OUT / f"hdd{i}.img", 2 * 1024**3) for i in (1, 2)]
port = allocate_ssh_port()
cmd = ["qemu-system-x86_64", "-m", "2048", "-smp", "2", "-display", "none", "-no-reboot",
       "-boot", "d", "-serial", "stdio", "-cdrom", str(artifact.iso_path),
       "-drive", f"file={vda},if=virtio,format=raw",
       "-device", "virtio-scsi-pci,id=scsi0"]
for i, img in enumerate(hdds, 1):
    cmd += ["-drive", f"file={img},if=none,id=hdd{i},format=raw",
            "-device", f"scsi-hd,bus=scsi0.0,drive=hdd{i},rotation_rate=7200,serial=hdd{i}"]
cmd += ["-device", "virtio-rng-pci",
        "-netdev", f"user,id=net0,hostfwd=tcp:127.0.0.1:{port}-:22", "-device", "virtio-net-pci,netdev=net0"]
(OUT / "harness.log").write_text("")
serial = (OUT / "serial.log").open("w")
child = pexpect.spawn(cmd[0], cmd[1:], encoding="utf-8", codec_errors="ignore", timeout=900)
child.logfile = serial
t0 = time.time()
vm = BootImageVM(child=child, log_path=OUT / "serial.log", harness_log_path=OUT / "harness.log",
                 metadata_path=OUT / "metadata.json", ssh_port=port, ssh_host="127.0.0.1",
                 ssh_executable="ssh", artifact=artifact)
print(f"logged in after {time.time()-t0:.0f}s", flush=True)
print(vm.run_as_root("for d in /sys/block/*; do echo \"$(basename $d) rot=$(cat $d/queue/rotational)\"; done", timeout=120), flush=True)
vm.wait_for_unit_inactive("pre-nixos", timeout=1200)
print("pre-nixos finished", flush=True)
for c in ["cat /run/pre-nixos/storage-status",
          "cat /proc/mdstat",
          "mdadm --detail /dev/md/md0 2>&1 | grep -E 'Raid Level|Intent|State :|Devices' ; ls -l /dev/md/ 2>&1",
          "vgs --noheadings -o vg_name,pv_count; lvs --noheadings -o lv_name,vg_name,lv_size",
          "lsblk -o NAME,ROTA,TYPE,SIZE,MOUNTPOINTS",
          "journalctl -u pre-nixos -b --no-pager | grep -iE 'mdadm|bitmap|continue creating|raid|error|fail|Traceback' | head -30"]:
    print(f"$ {c}\n{vm.run_as_root(c, timeout=180)}", flush=True)
vm.shutdown()
