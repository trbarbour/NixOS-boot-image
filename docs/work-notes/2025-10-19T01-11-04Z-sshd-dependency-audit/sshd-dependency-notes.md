Captured at 2025-10-19T01:21:49.514612+00:00

## Summary

- `systemctl list-dependencies sshd` shows only `sysinit.target` and its standard mounts, with no auxiliary services queued to start OpenSSH. 【F:docs/work-notes/2025-10-19T01-11-04Z-sshd-dependency-audit/sshd-dependency-notes.md†L15-L47】
- Reverse dependency inspection confirms nothing requires `sshd.service` directly. 【F:docs/work-notes/2025-10-19T01-11-04Z-sshd-dependency-audit/sshd-dependency-notes.md†L49-L57】
- `WantedBy=` is empty, so systemd does not pull `sshd` into a target automatically while pre-provisioning is in progress. 【F:docs/work-notes/2025-10-19T01-11-04Z-sshd-dependency-audit/sshd-dependency-notes.md†L91-L97】
- There is no standalone `secure_ssh` unit on this image; the service call returns `Unit secure_ssh.service could not be found.`, matching the hand-off to the Python helper instead of a oneshot. 【F:docs/work-notes/2025-10-19T01-11-04Z-sshd-dependency-audit/sshd-dependency-notes.md†L64-L71】
- `systemctl status sshd` still reflects the daemon in `start-pre` while host keys are generated, so the non-blocking restart remains safe to defer until provisioning completes. 【F:docs/work-notes/2025-10-19T01-11-04Z-sshd-dependency-audit/sshd-dependency-notes.md†L73-L89】

## Artifact
- ISO: /nix/store/n54vx051l18665kxd4y4y41b8klhijlh-nixos-24.05.20241230.b134951-x86_64-linux.iso/iso/nixos-24.05.20241230.b134951-x86_64-linux.iso
- Store path: /nix/store/n54vx051l18665kxd4y4y41b8klhijlh-nixos-24.05.20241230.b134951-x86_64-linux.iso
- Deriver: /nix/store/m7s7sc5hf0v1kwgd6dh0316syyk5fy4d-nixos-24.05.20241230.b134951-x86_64-linux.iso.drv
- narHash: sha256-vTfoWgQXXsJhexdyiIQwUMSdYP7sMKlPcVUbuCDNR/k=
- Embedded root key fingerprint: 256 SHA256:nIF54ffXiJFYPj5a6i6QH6uOKmrSGyIB3OYkW0uBmu4 boot-image-vm-manual-debug (ED25519)
- SSH forward port: 36685
- Disk image: /workspace/NixOS-boot-image/docs/work-notes/2025-10-19T01-11-04Z-sshd-dependency-audit/disk.img

## systemctl_list_dependencies_sshd
```shell
systemctl list-dependencies sshd --no-pager
```
```
sshd.service
● ├─system.slice
● └─sysinit.target
●   ├─dev-hugepages.mount
●   ├─dev-mqueue.mount
●   ├─firewall.service
●   ├─kmod-static-nodes.service
○   ├─suid-sgid-wrappers.service
●   ├─sys-fs-fuse-connections.mount
●   ├─sys-kernel-config.mount
●   ├─sys-kernel-debug.mount
●   ├─systemd-ask-password-console.path
○   ├─systemd-boot-random-seed.service
●   ├─systemd-journal-catalog-update.service
●   ├─systemd-journal-flush.service
●   ├─systemd-journald.service
●   ├─systemd-modules-load.service
○   ├─systemd-pstore.service
●   ├─systemd-random-seed.service
●   ├─systemd-sysctl.service
●   ├─systemd-timesyncd.service
●   ├─systemd-tmpfiles-setup-dev-early.service
●   ├─systemd-tmpfiles-setup-dev.service
●   ├─systemd-tmpfiles-setup.service
●   ├─systemd-udev-trigger.service
●   ├─systemd-udevd.service
●   ├─systemd-update-done.service
●   ├─systemd-update-utmp.service
●   ├─cryptsetup.target
●   ├─local-fs.target
●   │ ├─-.mount
●   │ ├─iso.mount
●   │ ├─nix-.ro\x2dstore.mount
●   │ ├─nix-.rw\x2dstore.mount
●   │ ├─nix-store.mount
●   │ └─systemd-remount-fs.service
●   └─swap.target
```

## systemctl_list_dependencies_reverse_sshd
```shell
systemctl list-dependencies --reverse sshd --no-pager
```
```
sshd.service
```

## systemctl_status_secure_ssh
```shell
systemctl status secure_ssh --no-pager
```
```
Unit secure_ssh.service could not be found.
```

## systemctl_status_sshd
```shell
systemctl status sshd --no-pager
```
```
● sshd.service - SSH Daemon
Loaded: loaded (/etc/systemd/system/sshd.service; linked; preset: enabled)
Active: activating (start-pre) since Sun 2025-10-19 01:29:04 UTC; 8s ago
Cntrl PID: 1393 (sshd-pre-start)
IP: 0B in, 0B out
IO: 1.2M read, 0B written
Tasks: 2 (limit: 2329)
Memory: 3.9M (peak: 4.3M)
CPU: 8.121s
CGroup: /system.slice/sshd.service
├─1393 /nix/store/1jzhbwq5rjjaqa75z88ws2b424vh7m53-bash-5.2p32/bin…
└─1397 ssh-keygen -t rsa -b 4096 -f /etc/ssh/ssh_host_rsa_key -N
Oct 19 01:29:04 nixos systemd[1]: Starting SSH Daemon...
```

## systemctl_show_wantedby_sshd
```shell
systemctl show -p WantedBy sshd.service
```
```
WantedBy=
```

## journalctl_secure_ssh
```shell
journalctl --no-pager -u secure_ssh -b
```
```
-- No entries --
```
