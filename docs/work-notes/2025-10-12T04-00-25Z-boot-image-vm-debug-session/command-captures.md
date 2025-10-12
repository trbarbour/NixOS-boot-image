# Manual debug command captures

Normalized console transcript from the 2025-10-12 debug session. Prompt noise and ANSI control sequences have been removed.

## storage_status
```shell
cat /run/pre-nixos/storage-status 2>/dev/null || true
```
No output (the file was absent or empty during capture).

## systemctl_status
```shell
SYSTEMD_COLORS=0 SYSTEMD_PAGER=cat SYSTEMD_PAGERSECURE=1 systemctl status pre-nixos --no-pager 2>&1 || true
```
```text
● pre-nixos.service - Pre-NixOS setup
     Loaded: loaded (/etc/systemd/system/pre-nixos.service; enabled; preset: enabled)
     Active: activating (start) since Sun 2025-10-12 04:02:35 UTC; 39s ago
   Main PID: 669 (pre-nixos-start)
         IP: 0B in, 0B out
         IO: 45.1M read, 0B written
      Tasks: 3 (limit: 2329)
     Memory: 42.9M (peak: 43.1M)
        CPU: 11.972s
     CGroup: /system.slice/pre-nixos.service
             ├─669 /nix/store/1jzhbwq5rjjaqa75z88ws2b424vh7m53-bash-5.2p32/bin/…
             ├─801 /nix/store/s0p1kr5mvs0j42dq5r08kgqbi0k028f2-python3-3.11.10/…
             └─861 systemctl start sshd

Oct 12 04:02:57 nixos pre-nixos-start[801]: {"command": ["ip", "link", "set"…0"}
Oct 12 04:02:57 nixos pre-nixos-start[801]: {"command": ["ip", "link", "set"…0"}
Oct 12 04:02:57 nixos pre-nixos-start[801]: {"command": ["ip", "link", "set"…0"}
Oct 12 04:02:57 nixos pre-nixos-start[801]: {"command": ["ip", "link", "set"…0"}
Oct 12 04:02:57 nixos pre-nixos-start[801]: {"command": ["ip", "link", "set"…0"}
Oct 12 04:02:57 nixos pre-nixos-start[801]: {"command": ["systemctl", "resta…0"}
Oct 12 04:03:01 nixos pre-nixos-start[801]: {"command": ["systemctl", "resta…0"}
Oct 12 04:03:01 nixos pre-nixos-start[801]: {"authorized_key": "/nix/store/i…0"}
Oct 12 04:03:01 nixos pre-nixos-start[801]: {"authorized_keys_path": "/root/…0"}
Oct 12 04:03:01 nixos pre-nixos-start[801]: {"command": ["systemctl", "start…0"}
Hint: Some lines were ellipsized, use -l to show in full.
```

## journalctl_pre_nixos
```shell
SYSTEMD_COLORS=0 SYSTEMD_PAGER=cat SYSTEMD_PAGERSECURE=1 JOURNALCTL_PAGER=cat journalctl --no-pager -u pre-nixos.service -b || true
```
```text
Oct 12 04:02:35 nixos systemd[1]: Starting Pre-NixOS setup...
Oct 12 04:02:57 nixos pre-nixos-start[801]: {"authorized_key": null, "event": "pre_nixos.network.configure_lan.start", "net_path": "/sys/class/net", "network_dir": "/etc/systemd/network", "root_home": "/root", "ssh_dir": "/etc/ssh", "ssh_service": "sshd", "timestamp": "2025-10-12T04:02:56.956629+00:00"}
Oct 12 04:02:57 nixos pre-nixos-start[801]: {"attempts": 30, "delay_seconds": 2.0, "event": "pre_nixos.network.wait_for_lan.start", "net_path": "/sys/class/net", "timestamp": "2025-10-12T04:02:56.972800+00:00"}
Oct 12 04:02:57 nixos pre-nixos-start[801]: {"command": ["ip", "link", "set", "ens4", "up"], "event": "pre_nixos.network.command.start", "timestamp": "2025-10-12T04:02:56.981178+00:00"}
Oct 12 04:02:57 nixos pre-nixos-start[801]: {"command": ["ip", "link", "set", "ens4", "up"], "event": "pre_nixos.network.command.finished", "returncode": 0, "status": "success", "timestamp": "2025-10-12T04:02:57.260281+00:00"}
Oct 12 04:02:57 nixos pre-nixos-start[801]: {"event": "pre_nixos.network.identify_lan.detected", "interface": "ens4", "signal": "carrier", "timestamp": "2025-10-12T04:02:57.269470+00:00"}
Oct 12 04:02:57 nixos pre-nixos-start[801]: {"event": "pre_nixos.network.wait_for_lan.detected", "interface": "ens4", "timestamp": "2025-10-12T04:02:57.270572+00:00"}
Oct 12 04:02:57 nixos pre-nixos-start[801]: {"event": "pre_nixos.network.configure_lan.detected_interface", "interface": "ens4", "timestamp": "2025-10-12T04:02:57.271131+00:00"}
Oct 12 04:02:57 nixos pre-nixos-start[801]: {"event": "pre_nixos.network.write_lan_rename_rule.start", "net_path": "/sys/class/net", "rules_dir": "/etc/systemd/network", "timestamp": "2025-10-12T04:02:57.271868+00:00"}
Oct 12 04:02:57 nixos pre-nixos-start[801]: {"attempts": 30, "delay_seconds": 2.0, "event": "pre_nixos.network.wait_for_lan.start", "net_path": "/sys/class/net", "timestamp": "2025-10-12T04:02:57.272813+00:00"}
Oct 12 04:02:57 nixos pre-nixos-start[801]: {"command": ["ip", "link", "set", "ens4", "up"], "event": "pre_nixos.network.command.start", "timestamp": "2025-10-12T04:02:57.275009+00:00"}
Oct 12 04:02:57 nixos pre-nixos-start[801]: {"command": ["ip", "link", "set", "ens4", "up"], "event": "pre_nixos.network.command.finished", "returncode": 0, "status": "success", "timestamp": "2025-10-12T04:02:57.351749+00:00"}
Oct 12 04:02:57 nixos pre-nixos-start[801]: {"event": "pre_nixos.network.identify_lan.detected", "interface": "ens4", "signal": "carrier", "timestamp": "2025-10-12T04:02:57.359174+00:00"}
Oct 12 04:02:57 nixos pre-nixos-start[801]: {"event": "pre_nixos.network.wait_for_lan.detected", "interface": "ens4", "timestamp": "2025-10-12T04:02:57.360173+00:00"}
Oct 12 04:02:57 nixos pre-nixos-start[801]: {"event": "pre_nixos.network.write_lan_rename_rule.finished", "interface": "ens4", "rule_path": "/etc/systemd/network/10-lan.link", "timestamp": "2025-10-12T04:02:57.363615+00:00"}
Oct 12 04:02:57 nixos pre-nixos-start[801]: {"event": "pre_nixos.network.configure_lan.network_file_written", "network_file": "/etc/systemd/network/20-lan.network", "timestamp": "2025-10-12T04:02:57.366088+00:00"}
Oct 12 04:02:57 nixos pre-nixos-start[801]: {"command": ["ip", "link", "set", "ens4", "down"], "event": "pre_nixos.network.command.start", "timestamp": "2025-10-12T04:02:57.366952+00:00"}
Oct 12 04:02:57 nixos pre-nixos-start[801]: {"command": ["ip", "link", "set", "ens4", "down"], "event": "pre_nixos.network.command.finished", "returncode": 0, "status": "success", "timestamp": "2025-10-12T04:02:57.484088+00:00"}
Oct 12 04:02:57 nixos pre-nixos-start[801]: {"command": ["ip", "link", "set", "ens4", "name", "lan"], "event": "pre_nixos.network.command.start", "timestamp": "2025-10-12T04:02:57.486068+00:00"}
Oct 12 04:02:57 nixos pre-nixos-start[801]: {"command": ["ip", "link", "set", "ens4", "name", "lan"], "event": "pre_nixos.network.command.finished", "returncode": 0, "status": "success", "timestamp": "2025-10-12T04:02:57.609411+00:00"}
Oct 12 04:02:57 nixos pre-nixos-start[801]: {"command": ["ip", "link", "set", "lan", "up"], "event": "pre_nixos.network.command.start", "timestamp": "2025-10-12T04:02:57.611317+00:00"}
Oct 12 04:02:57 nixos pre-nixos-start[801]: {"command": ["ip", "link", "set", "lan", "up"], "event": "pre_nixos.network.command.finished", "returncode": 0, "status": "success", "timestamp": "2025-10-12T04:02:57.722073+00:00"}
Oct 12 04:02:57 nixos pre-nixos-start[801]: {"command": ["systemctl", "restart", "systemd-networkd"], "event": "pre_nixos.network.systemctl.start", "ignore_missing": true, "timestamp": "2025-10-12T04:02:57.725184+00:00"}
Oct 12 04:03:01 nixos pre-nixos-start[801]: {"command": ["systemctl", "restart", "systemd-networkd"], "event": "pre_nixos.network.systemctl.finished", "returncode": 0, "status": "success", "timestamp": "2025-10-12T04:03:01.565422+00:00"}
Oct 12 04:03:01 nixos pre-nixos-start[801]: {"authorized_key": "/nix/store/ig1zxgbsd3j5ypaydpr0blcahxx0r0is-pre-nixos-0.1.0/lib/python3.11/site-packages/pre_nixos/root_key.pub", "event": "pre_nixos.network.secure_ssh.start", "ssh_dir": "/etc/ssh", "ssh_service": "sshd", "timestamp": "2025-10-12T04:03:01.571872+00:00"}
Oct 12 04:03:01 nixos pre-nixos-start[801]: {"authorized_keys_path": "/root/.ssh/authorized_keys", "event": "pre_nixos.network.secure_ssh.authorized_key_written", "timestamp": "2025-10-12T04:03:01.813276+00:00"}
Oct 12 04:03:01 nixos pre-nixos-start[801]: {"command": ["systemctl", "start", "sshd"], "event": "pre_nixos.network.systemctl.start", "ignore_missing": false, "timestamp": "2025-10-12T04:03:01.815890+00:00"}
```

## networkctl
```shell
SYSTEMD_COLORS=0 SYSTEMD_PAGER=cat SYSTEMD_PAGERSECURE=1 networkctl status lan || true
```
```text
● 2: lan
                   Link File: /nix/store/rhq3rwyghbqq4lnkmdf4vsrazr2aa5a7-syste…
                Network File: /etc/systemd/network/20-lan.network
                       State: routable (configured)
                Online state: online
                        Type: ether
                        Path: pci-0000:00:04.0
                      Driver: virtio_net
                      Vendor: Red Hat, Inc.
                       Model: Virtio network device
           Alternative Names: enp0s4
            Hardware Address: 52:54:00:12:34:56
                         MTU: 1500 (min: 68, max: 65535)
                       QDisc: fq_codel
IPv6 Address Generation Mode: eui64
    Number of Queues (Tx/Rx): 1/1
            Auto negotiation: no
                     Address: 10.0.2.15 (DHCP4 via 10.0.2.2)
                              fec0::5054:ff:fe12:3456
                              fe80::5054:ff:fe12:3456
                     Gateway: 10.0.2.2
                              fe80::2
                         DNS: 10.0.2.3
           Activation Policy: up
         Required For Online: yes
             DHCP4 Client ID: IAID:0x405663a2/DUID
           DHCP6 Client DUID: DUID-EN/Vendor:0000ab11c9ce267a852d6a0f

Oct 12 04:02:57 nixos systemd-networkd[757]: lan: Link UP
Oct 12 04:02:57 nixos systemd-networkd[757]: lan: Gained carrier
Oct 12 04:03:01 nixos systemd-networkd[845]: lan: Link UP
Oct 12 04:03:01 nixos systemd-networkd[845]: lan: Gained carrier
Oct 12 04:03:01 nixos systemd-networkd[845]: lan: Gained IPv6LL
Oct 12 04:03:01 nixos systemd-networkd[845]: lan: Configuring with /etc/syst…rk.
Oct 12 04:03:02 nixos systemd-networkd[845]: lan: DHCPv4 address 10.0.2.15/2…2.2
```

## ip_link
```shell
ip -o link || true
```
No output captured (command completed without producing stdout).

## ip_addr
```shell
ip -o -4 addr show dev lan 2>/dev/null || true
```
No output captured (command completed without producing stdout).
