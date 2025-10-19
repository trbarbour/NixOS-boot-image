Captured at 2025-10-19T11:56:44.759226+00:00

## Artifact
- ISO: /nix/store/rc65p51sxc5hhsam21ysk9i86212a2d9-nixos-24.05.20241230.b134951-x86_64-linux.iso/iso/nixos-24.05.20241230.b134951-x86_64-linux.iso
- Store path: /nix/store/rc65p51sxc5hhsam21ysk9i86212a2d9-nixos-24.05.20241230.b134951-x86_64-linux.iso
- Deriver: /nix/store/h95a2f238l5xy65va7v57g06advwmlnr-nixos-24.05.20241230.b134951-x86_64-linux.iso.drv
- narHash: sha256-0dJEOx+hEoEnGN3woC0NaZXiGcRg9q9UoG0kMfxJq8o=
- Embedded root key fingerprint: 256 SHA256:doaQIT2DbUuuUFDXLO+KE/bsXdWWKjBEciqsM0Ut14s boot-image-vm-manual-debug (ED25519)
- SSH forward port: 33481
- Disk image: /workspace/NixOS-boot-image/docs/work-notes/2025-10-19T11-49-37Z-storage-detection-probe/disk.img (sparse capture removed after diagnostics)

## pre_nixos_detect_storage
```shell
pre-nixos-detect-storage
```
_(no output)_

## pre_nixos_plan_only
```shell
pre-nixos --plan-only
```
```
{"authorized_key": null, "event": "pre_nixos.network.configure_lan.start", "net_path": "/sys/class/net", "network_dir": "/etc/systemd/network", "root_home": "/root", "ssh_dir": "/etc/ssh", "ssh_service": "sshd", "timestamp": "2025-10-19T11:58:27.726294+00:00"}
{"attempts": 30, "delay_seconds": 2.0, "event": "pre_nixos.network.wait_for_lan.start", "net_path": "/sys/class/net", "timestamp": "2025-10-19T11:58:27.734126+00:00"}
{"command": ["ip", "link", "set", "lan", "up"], "event": "pre_nixos.network.command.start", "timestamp": "2025-10-19T11:58:27.737764+00:00"}
{"command": ["ip", "link", "set", "lan", "up"], "event": "pre_nixos.network.command.finished", "returncode": 0, "status": "success", "timestamp": "2025-10-19T11:58:27.806462+00:00"}
{"event": "pre_nixos.network.identify_lan.detected", "interface": "lan", "signal": "carrier", "timestamp": "2025-10-19T11:58:27.813317+00:00"}
{"event": "pre_nixos.network.wait_for_lan.detected", "interface": "lan", "timestamp": "2025-10-19T11:58:27.813838+00:00"}
{"event": "pre_nixos.network.configure_lan.detected_interface", "interface": "lan", "timestamp": "2025-10-19T11:58:27.814304+00:00"}
{"event": "pre_nixos.network.write_lan_rename_rule.start", "net_path": "/sys/class/net", "rules_dir": "/etc/systemd/network", "timestamp": "2025-10-19T11:58:27.814623+00:00"}
{"attempts": 30, "delay_seconds": 2.0, "event": "pre_nixos.network.wait_for_lan.start", "net_path": "/sys/class/net", "timestamp": "2025-10-19T11:58:27.816430+00:00"}
{"command": ["ip", "link", "set", "lan", "up"], "event": "pre_nixos.network.command.start", "timestamp": "2025-10-19T11:58:27.818465+00:00"}
{"command": ["ip", "link", "set", "lan", "up"], "event": "pre_nixos.network.command.finished", "returncode": 0, "status": "success", "timestamp": "2025-10-19T11:58:27.874270+00:00"}
{"event": "pre_nixos.network.identify_lan.detected", "interface": "lan", "signal": "carrier", "timestamp": "2025-10-19T11:58:27.879797+00:00"}
{"event": "pre_nixos.network.wait_for_lan.detected", "interface": "lan", "timestamp": "2025-10-19T11:58:27.880569+00:00"}
{"event": "pre_nixos.network.write_lan_rename_rule.finished", "interface": "lan", "rule_path": "/etc/systemd/network/10-lan.link", "timestamp": "2025-10-19T11:58:27.884780+00:00"}
{"event": "pre_nixos.network.configure_lan.network_file_written", "network_file": "/etc/systemd/network/20-lan.network", "timestamp": "2025-10-19T11:58:27.887599+00:00"}
{"command": ["ip", "link", "set", "lan", "down"], "event": "pre_nixos.network.command.start", "timestamp": "2025-10-19T11:58:27.888029+00:00"}
{"command": ["ip", "link", "set", "lan", "down"], "event": "pre_nixos.network.command.finished", "returncode": 0, "status": "success", "timestamp": "2025-10-19T11:58:27.956890+00:00"}
{"command": ["ip", "link", "set", "lan", "name", "lan"], "event": "pre_nixos.network.command.start", "timestamp": "2025-10-19T11:58:27.959586+00:00"}
{"command": ["ip", "link", "set", "lan", "name", "lan"], "event": "pre_nixos.network.command.finished", "returncode": 0, "status": "success", "timestamp": "2025-10-19T11:58:28.067725+00:00"}
{"command": ["ip", "link", "set", "lan", "up"], "event": "pre_nixos.network.command.start", "timestamp": "2025-10-19T11:58:28.069454+00:00"}
{"command": ["ip", "link", "set", "lan", "up"], "event": "pre_nixos.network.command.finished", "returncode": 0, "status": "success", "timestamp": "2025-10-19T11:58:28.134482+00:00"}
{"command": ["systemctl", "restart", "systemd-networkd"], "event": "pre_nixos.network.systemctl.start", "ignore_missing": true, "timestamp": "2025-10-19T11:58:28.135601+00:00"}
{"command": ["systemctl", "restart", "systemd-networkd"], "event": "pre_nixos.network.systemctl.finished", "returncode": 0, "status": "success", "timestamp": "2025-10-19T11:58:29.278588+00:00"}
{"authorized_key": "/nix/store/i9bf2j6rsrbk1bil83kqfv6jlz3mzv00-pre-nixos-0.1.0/lib/python3.11/site-packages/pre_nixos/root_key.pub", "event": "pre_nixos.network.secure_ssh.start", "ssh_dir": "/etc/ssh", "ssh_service": "sshd", "timestamp": "2025-10-19T11:58:29.280694+00:00"}
{"authorized_keys_path": "/root/.ssh/authorized_keys", "event": "pre_nixos.network.secure_ssh.authorized_key_written", "timestamp": "2025-10-19T11:58:29.297985+00:00"}
{"command": ["systemctl", "reload-or-restart", "--no-block", "sshd"], "event": "pre_nixos.network.systemctl.start", "ignore_missing": false, "timestamp": "2025-10-19T11:58:29.304634+00:00"}
{"command": ["systemctl", "reload-or-restart", "--no-block", "sshd"], "event": "pre_nixos.network.systemctl.finished", "returncode": 0, "status": "success", "timestamp": "2025-10-19T11:58:29.544338+00:00"}
{"authorized_keys_path": "/root/.ssh/authorized_keys", "event": "pre_nixos.network.secure_ssh.finished", "timestamp": "2025-10-19T11:58:29.545413+00:00"}
{"event": "pre_nixos.network.configure_lan.finished", "interface": "lan", "network_file": "/etc/systemd/network/20-lan.network", "timestamp": "2025-10-19T11:58:29.545810+00:00"}
{
"arrays": [],
"vgs": [
{
"name": "main",
"devices": [
"vda2"
]
}
],
"lvs": [
{
"name": "slash",
"vg": "main",
"size": "3064M"
},
{
"name": "swap",
"vg": "main",
"size": "4M"
}
],
"partitions": {
"vda": [
{
"name": "vda1",
"type": "efi"
},
{
"name": "vda2",
"type": "lvm"
}
]
},
"disko": {
"disk": {
"vda": {
"type": "disk",
"device": "/dev/vda",
"content": {
"type": "gpt",
"partitions": {
"vda1": {
"size": "1G",
"type": "EF00",
"content": {
"type": "filesystem",
"format": "vfat",
"extraArgs": [
"-n",
"EFI"
],
"mountpoint": "/boot",
"mountOptions": [
"umask=0077"
]
}
},
"vda2": {
"size": "100%",
"content": {
"type": "lvm_pv",
"vg": "main"
}
}
}
}
}
},
"mdadm": {},
"lvm_vg": {
"main": {
"type": "lvm_vg",
"lvs": {
"slash": {
"size": "3064M",
"content": {
"type": "filesystem",
"format": "ext4",
"mountpoint": "/",
"mountOptions": [
"noatime"
],
"extraArgs": [
"-L",
"slash"
]
}
},
"swap": {
"size": "4M",
"content": {
"type": "swap",
"extraArgs": [
"--label",
"swap"
]
}
}
}
}
}
}
}
```

## storage_status
```shell
cat /run/pre-nixos/storage-status 2>/dev/null || true
```
_(no output)_

## disko_config
```shell
cat /var/log/pre-nixos/disko-config.nix 2>/dev/null || true
```
```
{
disko.devices = builtins.fromJSON ''
{
"disk": {
"vda": {
"content": {
"partitions": {
"vda1": {
"content": {
"extraArgs": [
"-n",
"EFI"
],
"format": "vfat",
"mountOptions": [
"umask=0077"
],
"mountpoint": "/boot",
"type": "filesystem"
},
"size": "1G",
"type": "EF00"
},
"vda2": {
"content": {
"type": "lvm_pv",
"vg": "main"
},
"size": "100%"
}
},
"type": "gpt"
},
"device": "/dev/vda",
"type": "disk"
}
},
"lvm_vg": {
"main": {
"lvs": {
"slash": {
"content": {
"extraArgs": [
"-L",
"slash"
],
"format": "ext4",
"mountOptions": [
"noatime"
],
"mountpoint": "/",
"type": "filesystem"
},
"size": "3064M"
},
"swap": {
"content": {
"extraArgs": [
"--label",
"swap"
],
"type": "swap"
},
"size": "4M"
}
},
"type": "lvm_vg"
}
},
"mdadm": {}
}
'';
}
```

## running_disko_processes
```shell
ps -ef | grep -E 'disko|wipefs' | grep -v grep || true
```
```
root         863     842  1 11:58 ?        00:00:00 /nix/store/1jzhbwq5rjjaqa75z88ws2b424vh7m53-bash-5.2p32/bin/bash /nix/store/67n392qxiwrb0bsl32n81jz5f5i6nn34-disko/bin/.disko-wrapped --mode destroy,format,mount --yes-wipe-all-disks --root-mountpoint /mnt /var/log/pre-nixos/disko-config.nix
root         865     863  0 11:58 ?        00:00:00 /nix/store/1jzhbwq5rjjaqa75z88ws2b424vh7m53-bash-5.2p32/bin/bash /nix/store/67n392qxiwrb0bsl32n81jz5f5i6nn34-disko/bin/.disko-wrapped --mode destroy,format,mount --yes-wipe-all-disks --root-mountpoint /mnt /var/log/pre-nixos/disko-config.nix
root         866     865 71 11:58 ?        00:00:10 nix-build /nix/store/67n392qxiwrb0bsl32n81jz5f5i6nn34-disko/share/disko/cli.nix --no-out-link --impure --argstr mode destroy,format,mount --argstr rootMountPoint /mnt --arg diskoFile /var/log/pre-nixos/disko-config.nix
```

## lsblk
```shell
lsblk --output NAME,TYPE,SIZE,MOUNTPOINT
```
```
NAME  TYPE  SIZE MOUNTPOINT
fd0   disk    4K
loop0 loop    1G /nix/.ro-store
sr0   rom   1.1G /iso
vda   disk    4G
```
