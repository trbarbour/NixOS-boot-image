Manual command capture from BootImageVM session

## storage_status
```shell
cat /run/pre-nixos/storage-status 2>/dev/null || true
```
```
'
cat /run/pre-nixos/storage-status 2>/dev/null || true
__USER__
[nixos@nixos:~]$ export PS1='
```

## systemctl_status
```shell
systemctl status pre-nixos --no-pager -l 2>&1 || true
```
```
'
```

## journalctl_pre_nixos
```shell
journalctl --no-pager -u pre-nixos.service -b || true
```
```
cat /run/pre-nixos/storage-status 2>/dev/null || true
systemctl status pre-nixos --no-pager -l 2>&1 || true
journalctl --no-pager -u pre-nixos.service -b || true
```

## networkctl_status
```shell
networkctl status lan || true
```
```
systemctl status pre-nixos --no-pager -l 2>&1 || true
networkctl status lan || true
● pre-nixos.service - Pre-NixOS setup
Loaded: loaded (/etc/systemd/system/pre-nixos.service; enabled; preset: enabled)
Active: activating (start) since Sun 2025-10-12 01:16:00 UTC; 39s ago
Main PID: 676 (pre-nixos-start)
IP: 0B in, 0B out
IO: 43.0M read, 0B written
Tasks: 3 (limit: 2329)
Memory: 42.5M (peak: 42.7M)
CPU: 11.111s
CGroup: /system.slice/pre-nixos.service
├─676 /nix/store/1jzhbwq5rjjaqa75z88ws2b424vh7m53-bash-5.2p32/bin/bash /nix/store/7v090d6lml35kj94gybk8ma5vi8m1148-unit-script-pre-nixos-start/bin/pre-nixos-start
├─803 /nix/store/s0p1kr5mvs0j42dq5r08kgqbi0k028f2-python3-3.11.10/bin/python3.11 /nix/store/9wziy04f2i8d887wrp76kya3p1jqafvn-pre-nixos-0.1.0/bin/.pre-nixos-wrapped
└─872 systemctl start sshd
Oct 12 01:16:22 nixos pre-nixos-start[803]: {"command": ["ip", "link", "set", "ens4", "down"], "event": "pre_nixos.network.command.finished", "returncode": 0, "status": "success", "timestamp": "2025-10-12T01:16:22.282878+00:00"}
Oct 12 01:16:22 nixos pre-nixos-start[803]: {"command": ["ip", "link", "set", "ens4", "name", "lan"], "event": "pre_nixos.network.command.start", "timestamp": "2025-10-12T01:16:22.285577+00:00"}
Oct 12 01:16:22 nixos pre-nixos-start[803]: {"command": ["ip", "link", "set", "ens4", "name", "lan"], "event": "pre_nixos.network.command.finished", "returncode": 0, "status": "success", "timestamp": "2025-10-12T01:16:22.461772+00:00"}
Oct 12 01:16:22 nixos pre-nixos-start[803]: {"command": ["ip", "link", "set", "lan", "up"], "event": "pre_nixos.network.command.start", "timestamp": "2025-10-12T01:16:22.463910+00:00"}
Oct 12 01:16:22 nixos pre-nixos-start[803]: {"command": ["ip", "link", "set", "lan", "up"], "event": "pre_nixos.network.command.finished", "returncode": 0, "status": "success", "timestamp": "2025-10-12T01:16:22.560491+00:00"}
Oct 12 01:16:22 nixos pre-nixos-start[803]: {"command": ["systemctl", "restart", "systemd-networkd"], "event": "pre_nixos.network.systemctl.start", "ignore_missing": true, "timestamp": "2025-10-12T01:16:22.569717+00:00"}
Oct 12 01:16:28 nixos pre-nixos-start[803]: {"command": ["systemctl", "restart", "systemd-networkd"], "event": "pre_nixos.network.systemctl.finished", "returncode": 0, "status": "success", "timestamp": "2025-10-12T01:16:28.395757+00:00"}
Oct 12 01:16:28 nixos pre-nixos-start[803]: {"authorized_key": "/nix/store/9wziy04f2i8d887wrp76kya3p1jqafvn-pre-nixos-0.1.0/lib/python3.11/site-packages/pre_nixos/root_key.pub", "event": "pre_nixos.network.secure_ssh.start", "ssh_dir": "/etc/ssh", "ssh_service": "sshd", "timestamp": "2025-10-12T01:16:28.415885+00:00"}
Oct 12 01:16:28 nixos pre-nixos-start[803]: {"authorized_keys_path": "/root/.ssh/authorized_keys", "event": "pre_nixos.network.secure_ssh.authorized_key_written", "timestamp": "2025-10-12T01:16:28.885675+00:00"}
Oct 12 01:16:28 nixos pre-nixos-start[803]: {"command": ["systemctl", "start", "sshd"], "event": "pre_nixos.network.systemctl.start", "ignore_missing": false, "timestamp": "2025-10-12T01:16:28.914413+00:00"}
```

## ip_link
```shell
ip -o link || true
```
```
journalctl --no-pager -u pre-nixos.service -b || true
ip -o link || true
Oct 12 01:16:00 nixos systemd[1]: Starting Pre-NixOS setup...
Oct 12 01:16:21 nixos pre-nixos-start[803]: {"authorized_key": null, "event": "pre_nixos.network.configure_lan.start", "net_path": "/sys/class/net", "network_dir": "/etc/systemd/network", "root_home": "/root", "ssh_dir": "/etc/ssh", "ssh_service": "sshd", "timestamp": "2025-10-12T01:16:21.463250+00:00"}
Oct 12 01:16:21 nixos pre-nixos-start[803]: {"attempts": 30, "delay_seconds": 2.0, "event": "pre_nixos.network.wait_for_lan.start", "net_path": "/sys/class/net", "timestamp": "2025-10-12T01:16:21.502817+00:00"}
Oct 12 01:16:21 nixos pre-nixos-start[803]: {"command": ["ip", "link", "set", "ens4", "up"], "event": "pre_nixos.network.command.start", "timestamp": "2025-10-12T01:16:21.512652+00:00"}
Oct 12 01:16:21 nixos pre-nixos-start[803]: {"command": ["ip", "link", "set", "ens4", "up"], "event": "pre_nixos.network.command.finished", "returncode": 0, "status": "success", "timestamp": "2025-10-12T01:16:21.903745+00:00"}
Oct 12 01:16:21 nixos pre-nixos-start[803]: {"event": "pre_nixos.network.identify_lan.detected", "interface": "ens4", "signal": "carrier", "timestamp": "2025-10-12T01:16:21.923469+00:00"}
Oct 12 01:16:21 nixos pre-nixos-start[803]: {"event": "pre_nixos.network.wait_for_lan.detected", "interface": "ens4", "timestamp": "2025-10-12T01:16:21.926719+00:00"}
Oct 12 01:16:21 nixos pre-nixos-start[803]: {"event": "pre_nixos.network.configure_lan.detected_interface", "interface": "ens4", "timestamp": "2025-10-12T01:16:21.927805+00:00"}
Oct 12 01:16:21 nixos pre-nixos-start[803]: {"event": "pre_nixos.network.write_lan_rename_rule.start", "net_path": "/sys/class/net", "rules_dir": "/etc/systemd/network", "timestamp": "2025-10-12T01:16:21.931086+00:00"}
Oct 12 01:16:21 nixos pre-nixos-start[803]: {"attempts": 30, "delay_seconds": 2.0, "event": "pre_nixos.network.wait_for_lan.start", "net_path": "/sys/class/net", "timestamp": "2025-10-12T01:16:21.931891+00:00"}
Oct 12 01:16:21 nixos pre-nixos-start[803]: {"command": ["ip", "link", "set", "ens4", "up"], "event": "pre_nixos.network.command.start", "timestamp": "2025-10-12T01:16:21.940128+00:00"}
Oct 12 01:16:22 nixos pre-nixos-start[803]: {"command": ["ip", "link", "set", "ens4", "up"], "event": "pre_nixos.network.command.finished", "returncode": 0, "status": "success", "timestamp": "2025-10-12T01:16:22.091520+00:00"}
Oct 12 01:16:22 nixos pre-nixos-start[803]: {"event": "pre_nixos.network.identify_lan.detected", "interface": "ens4", "signal": "carrier", "timestamp": "2025-10-12T01:16:22.107400+00:00"}
Oct 12 01:16:22 nixos pre-nixos-start[803]: {"event": "pre_nixos.network.wait_for_lan.detected", "interface": "ens4", "timestamp": "2025-10-12T01:16:22.109188+00:00"}
Oct 12 01:16:22 nixos pre-nixos-start[803]: {"event": "pre_nixos.network.write_lan_rename_rule.finished", "interface": "ens4", "rule_path": "/etc/systemd/network/10-lan.link", "timestamp": "2025-10-12T01:16:22.117663+00:00"}
Oct 12 01:16:22 nixos pre-nixos-start[803]: {"event": "pre_nixos.network.configure_lan.network_file_written", "network_file": "/etc/systemd/network/20-lan.network", "timestamp": "2025-10-12T01:16:22.121704+00:00"}
Oct 12 01:16:22 nixos pre-nixos-start[803]: {"command": ["ip", "link", "set", "ens4", "down"], "event": "pre_nixos.network.command.start", "timestamp": "2025-10-12T01:16:22.127412+00:00"}
Oct 12 01:16:22 nixos pre-nixos-start[803]: {"command": ["ip", "link", "set", "ens4", "down"], "event": "pre_nixos.network.command.finished", "returncode": 0, "status": "success", "timestamp": "2025-10-12T01:16:22.282878+00:00"}
Oct 12 01:16:22 nixos pre-nixos-start[803]: {"command": ["ip", "link", "set", "ens4", "name", "lan"], "event": "pre_nixos.network.command.start", "timestamp": "2025-10-12T01:16:22.285577+00:00"}
Oct 12 01:16:22 nixos pre-nixos-start[803]: {"command": ["ip", "link", "set", "ens4", "name", "lan"], "event": "pre_nixos.network.command.finished", "returncode": 0, "status": "success", "timestamp": "2025-10-12T01:16:22.461772+00:00"}
Oct 12 01:16:22 nixos pre-nixos-start[803]: {"command": ["ip", "link", "set", "lan", "up"], "event": "pre_nixos.network.command.start", "timestamp": "2025-10-12T01:16:22.463910+00:00"}
Oct 12 01:16:22 nixos pre-nixos-start[803]: {"command": ["ip", "link", "set", "lan", "up"], "event": "pre_nixos.network.command.finished", "returncode": 0, "status": "success", "timestamp": "2025-10-12T01:16:22.560491+00:00"}
Oct 12 01:16:22 nixos pre-nixos-start[803]: {"command": ["systemctl", "restart", "systemd-networkd"], "event": "pre_nixos.network.systemctl.start", "ignore_missing": true, "timestamp": "2025-10-12T01:16:22.569717+00:00"}
Oct 12 01:16:28 nixos pre-nixos-start[803]: {"command": ["systemctl", "restart", "systemd-networkd"], "event": "pre_nixos.network.systemctl.finished", "returncode": 0, "status": "success", "timestamp": "2025-10-12T01:16:28.395757+00:00"}
Oct 12 01:16:28 nixos pre-nixos-start[803]: {"authorized_key": "/nix/store/9wziy04f2i8d887wrp76kya3p1jqafvn-pre-nixos-0.1.0/lib/python3.11/site-packages/pre_nixos/root_key.pub", "event": "pre_nixos.network.secure_ssh.start", "ssh_dir": "/etc/ssh", "ssh_service": "sshd", "timestamp": "2025-10-12T01:16:28.415885+00:00"}
Oct 12 01:16:28 nixos pre-nixos-start[803]: {"authorized_keys_path": "/root/.ssh/authorized_keys", "event": "pre_nixos.network.secure_ssh.authorized_key_written", "timestamp": "2025-10-12T01:16:28.885675+00:00"}
Oct 12 01:16:28 nixos pre-nixos-start[803]: {"command": ["systemctl", "start", "sshd"], "event": "pre_nixos.network.systemctl.start", "ignore_missing": false, "timestamp": "2025-10-12T01:16:28.914413+00:00"}
```

