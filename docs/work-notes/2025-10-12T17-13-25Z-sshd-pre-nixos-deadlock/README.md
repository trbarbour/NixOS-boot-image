# sshd/pre-nixos dependency deadlock (2025-10-12T17-13-25Z)

- **Collection command:** `python scripts/collect_sshd_pre_nixos_debug.py --output-dir docs/work-notes/2025-10-12T17-13-25Z-sshd-pre-nixos-deadlock --public-key /tmp/pytest-of-root/pytest-0/boot-image-ssh-key0/id_ed25519.pub`
- **Boot image:** `/nix/store/ss1n5r410q2n4fsaiii82bxaywf92qhj-nixos-24.05.20241230.b134951-x86_64-linux.iso` (see `metadata.json`).
- **Harness artefacts:** `harness.log` captures the scripted session; `serial.log` contains the raw console transcript.

## Evidence

- `systemctl show -p After sshd` confirms that `sshd.service` still has `pre-nixos.service` in its `After=` ordering, so the daemon will never start until the oneshot completes. (`systemctl_show_sshd.txt`)
- `systemctl list-jobs` shows the outstanding jobs, with `sshd.service` waiting for `pre-nixos.service` while the multi-user target also waits behind it. (`systemctl_list_jobs.txt`)
- `systemctl status pre-nixos --no-pager` captures the active oneshot stuck running `systemctl start sshd` inside the `pre_nixos.network.secure_ssh` step, matching the original deadlock hypothesis. (`systemctl_status_pre_nixos.txt`)
- `journalctl --no-pager -u pre-nixos.service -b` records the networking workflow reaching `secure_ssh` and repeatedly invoking `systemctl restart systemd-networkd` before launching `systemctl start sshd`, after which the unit never reaches `inactive`. (`journalctl_pre_nixos.txt`)
- `networkctl status lan` produced no additional output beyond the command header; the interface rename completed, but no status details were emitted in this run. (`networkctl_status_lan.txt`)
- `cat /run/pre-nixos/storage-status 2>/dev/null || true` returned no data, confirming that storage provisioning never progressed while the network oneshot was wedged. (`storage_status.txt`)

## Context

- Earlier debug captures exhibiting the same hang are available in:
  - `docs/work-notes/2025-10-12T02-04-19Z-boot-image-vm-debug-session/`
  - `docs/work-notes/2025-10-12T03-06-00Z-boot-image-vm-debug-session/`
- Those sessions lacked the explicit `sshd` ordering evidence; the new artefacts above document the dependency cycle for task queue item 1.
