"""E5/E6 spike: boot the AArch64 SD image's system under qemu-system-aarch64 -M virt.

Direct kernel boot (skips the Pi firmware/U-Boot chain; user decision U5) of the
system closure inside the SD image, with the SD image as the root disk.
"""
import subprocess, sys, time
from pathlib import Path
sys.path.insert(0, "/home/user/NixOS-boot-image")
import pexpect
from scripts.manual_vm_debug import allocate_ssh_port, prepare_disk_image
from tests.vm.controller import BootImageVM
from tests.vm.fixtures import BootImageBuild

OUT = Path(sys.argv[1]); IMG_ZST = Path(sys.argv[2]); TOP = Path(sys.argv[3]); ZSTD = sys.argv[4]
OUT.mkdir(parents=True, exist_ok=True)
sd = OUT / "sd.img"
if not sd.exists():
    subprocess.run([ZSTD, "-d", "-q", "-o", str(sd), str(IMG_ZST)], check=True)
    # A real card is larger than the image; the image's first-boot service grows
    # the root partition into the free space (run6 ran out of space without it).
    subprocess.run(["truncate", "-s", "8G", str(sd)], check=True)
target = prepare_disk_image(OUT / "target.img")
params = (TOP / "kernel-params").read_text().strip()
port = allocate_ssh_port()
cmd = ["qemu-system-aarch64", "-M", "virt", "-cpu", "cortex-a72", "-smp", "2", "-m", "2048",
       "-display", "none", "-no-reboot", "-serial", "stdio",
       "-kernel", str(TOP / "kernel"), "-initrd", str(TOP / "initrd"),
       # Spike only (diagnosis): serial last = primary console, so systemd's
       # status and failure messages reach the serial log.  EXTRA_APPEND.
       "-append", f"{params} init={TOP}/init {__import__('os').environ.get('EXTRA_APPEND', '')}".strip(),
       "-drive", f"file={sd},if=virtio,format=raw",
       "-drive", f"file={target},if=virtio,format=raw",
       "-device", "virtio-rng-pci",
       "-netdev", f"user,id=net0,hostfwd=tcp:127.0.0.1:{port}-:22", "-device", "virtio-net-pci,netdev=net0"]
artifact = BootImageBuild(iso_path=sd, store_path=IMG_ZST, deriver=None, nar_hash=None,
                          root_key_fingerprint="none")
(OUT / "harness.log").write_text("")
serial = (OUT / "serial.log").open("w")
t0 = time.time()
child = pexpect.spawn(cmd[0], cmd[1:], encoding="utf-8", codec_errors="ignore", timeout=2400)
child.logfile = serial
vm = BootImageVM(child=child, log_path=OUT / "serial.log", harness_log_path=OUT / "harness.log",
                 metadata_path=OUT / "metadata.json", ssh_port=port, ssh_host="127.0.0.1",
                 ssh_executable="ssh", artifact=artifact)
print(f"E5: logged in after {time.time()-t0:.0f}s", flush=True)
for c in ["uname -m; cat /proc/cmdline", "df -h / | tail -1", "lsblk -o NAME,RM,ROTA,TYPE,SIZE,MOUNTPOINTS", "findmnt -n -o SOURCE /",
          "ip -br link", "systemctl is-active pre-nixos"]:
    print(f"$ {c}\n{vm.run_as_root(c, timeout=300)}", flush=True)
vm.wait_for_unit_inactive("pre-nixos", timeout=2400)
print(f"pre-nixos finished after {time.time()-t0:.0f}s", flush=True)
for c in ["systemctl status pre-nixos --no-pager -l | head -20",
          "journalctl -u pre-nixos -b --no-pager | tail -60",
          "cat /run/pre-nixos/storage-status",
          "lsblk -o NAME,TYPE,SIZE,MOUNTPOINTS",
          "journalctl -u pre-nixos -b --no-pager | grep -iE 'error|fail|Traceback|protected|existing|auto' | head -20",
          "ip -br addr; networkctl list --no-pager 2>&1 | head; journalctl -b --no-pager | grep -iE 'lan|rename|enp0s2|link' | head -20",
          "nixos-generate-config --show-hardware-config --root /mnt 2>&1 | head -60"]:
    print(f"$ {c}\n{vm.run_as_root(c, timeout=600)}", flush=True)
vm.shutdown()
