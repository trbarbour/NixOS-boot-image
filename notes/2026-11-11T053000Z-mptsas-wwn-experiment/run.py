"""Experiment (item 48): does Linux's mptsas discover a disk on QEMU's mptsas1068?"""
import subprocess, sys, time, pexpect
from pathlib import Path

ISO = sys.argv[1]
QEMU = sys.argv[2]
OUT = Path(sys.argv[3])
variants = {
    "A-scsi-id-0": "scsi-id=0",
    "B-scsi-id-1": "scsi-id=1",
    "C-wwn": "scsi-id=0,wwn=0x5000c500a0b0c0d1",
}
for name, extra in variants.items():
    disk = OUT / f"{name}.img"
    subprocess.run(["truncate", "-s", "1G", str(disk)], check=True)
    cmd = [QEMU, "-m", "2048", "-smp", "2", "-display", "none", "-no-reboot", "-serial", "stdio",
           "-boot", "d", "-cdrom", ISO,
           "-device", "mptsas1068,id=mptsas0",
           "-drive", f"file={disk},if=none,id=d0,format=raw",
           "-device", f"scsi-hd,bus=mptsas0.0,drive=d0,serial=hbahdd,{extra}"]
    log = open(OUT / f"{name}.log", "w")
    child = pexpect.spawn(cmd[0], cmd[1:], encoding="utf-8", codec_errors="ignore", timeout=900)
    child.logfile = log
    started = time.time()
    try:
        # The serial console logs in as nixos automatically.
        child.expect(r"nixos@nixos:~\]\$", timeout=900)
        time.sleep(5)
        child.sendline("sudo -i")
        child.expect(r"root@nixos", timeout=120)
        child.sendline("PS1='EXP# '")
        child.expect("EXP# ", timeout=60)
        child.sendline("sleep 45; echo ==RESULT==; dmesg | grep -iE 'mpt|sas|scsi [0-9]|\\] sd|sd [0-9]'; lsblk -dnro NAME,SERIAL; echo ==END==")
        child.expect("==END==\r?\n", timeout=300)
        child.expect("==END==", timeout=300)
    except Exception as exc:
        log.write(f"\nEXPERIMENT ERROR: {exc!r}\n")
    finally:
        log.write(f"\nELAPSED {time.time()-started:.0f}s\n")
        child.close(force=True)
        log.close()
        disk.unlink(missing_ok=True)
print("done")
