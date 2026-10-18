"""Spike for #306: boot the ISO from a writable, non-removable USB stick."""
import hashlib, shutil, sys, time
from pathlib import Path
sys.path.insert(0, "/home/user/NixOS-boot-image")
import pexpect
from scripts.manual_vm_debug import describe_boot_image, allocate_ssh_port, prepare_disk_image
from tests.vm.controller import BootImageVM

OUT = Path(sys.argv[1]); ISO_STORE = Path(sys.argv[2]); OUT.mkdir(parents=True, exist_ok=True)
artifact = describe_boot_image(ISO_STORE, public_key=None)
stick = OUT / "stick.img"
shutil.copyfile(artifact.iso_path, stick); stick.chmod(0o644)
def digest(p): return hashlib.sha256(p.read_bytes()).hexdigest()
before = digest(stick)
target = prepare_disk_image(OUT / "target.img")
port = allocate_ssh_port()
cmd = ["qemu-system-x86_64", "-m", "2048", "-smp", "2", "-display", "none", "-no-reboot",
       "-serial", "stdio",
       "-device", "qemu-xhci,id=xhci",
       "-drive", f"file={stick},if=none,id=stick,format=raw",
       "-device", "usb-storage,bus=xhci.0,drive=stick,removable=off,bootindex=0",
       "-drive", f"file={target},if=virtio,format=raw",
       "-device", "virtio-rng-pci",
       "-netdev", f"user,id=net0,hostfwd=tcp:127.0.0.1:{port}-:22", "-device", "virtio-net-pci,netdev=net0"]
print("qemu:", " ".join(cmd[-14:-6]), flush=True)
(OUT / "harness.log").write_text("")
serial = (OUT / "serial.log").open("w")
child = pexpect.spawn(cmd[0], cmd[1:], encoding="utf-8", codec_errors="ignore", timeout=900)
child.logfile = serial
t0 = time.time()
vm = BootImageVM(child=child, log_path=OUT / "serial.log", harness_log_path=OUT / "harness.log",
                 metadata_path=OUT / "metadata.json", ssh_port=port, ssh_host="127.0.0.1",
                 ssh_executable="ssh", artifact=artifact)
print(f"logged in after {time.time()-t0:.0f}s", flush=True)
for c in ["lsblk -o NAME,RM,TRAN,TYPE,SIZE,MOUNTPOINTS",
          "findmnt -n -o SOURCE /iso",
          "cat /sys/block/sda/removable 2>/dev/null"]:
    print(f"$ {c}\n{vm.run_as_root(c, timeout=120)}", flush=True)
vm.wait_for_unit_inactive("pre-nixos", timeout=900)
print("pre-nixos finished", flush=True)
for c in ["cat /run/pre-nixos/storage-status 2>/dev/null",
          "lsblk -o NAME,TYPE,SIZE,MOUNTPOINTS",
          "journalctl -u pre-nixos -b --no-pager | tail -n 40",
          "PRE_NIXOS_LOG_EVENTS=1 PRE_NIXOS_LOG_FILE=/tmp/d.log pre-nixos-detect-storage 2>&1 | grep -E 'resolve_boot_disk|device_' ; echo detect_rc=${PIPESTATUS[0]}",
          "PRE_NIXOS_LOG_EVENTS=1 PRE_NIXOS_LOG_FILE=/tmp/p.log pre-nixos --plan-only 2>&1 | grep -E 'resolve_protected|device_' ; echo plan_rc=${PIPESTATUS[0]}",
          "cat /proc/cmdline", "findmnt -rn -o TARGET,SOURCE,FSTYPE | grep -vE '^/(proc|sys|dev|run)'"]:
    print(f"$ {c}\n{vm.run_as_root(c, timeout=120)}", flush=True)
vm.shutdown()
after = digest(stick)
print("STICK UNCHANGED" if after == before else "STICK MODIFIED", flush=True)
