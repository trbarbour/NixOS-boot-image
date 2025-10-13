# 2025-10-13T13:06:59Z sshd/pre-nixos verification

## Summary

Automated capture via `collect_sshd_pre_nixos_debug.py` against the latest boot image recorded that `pre-nixos.service` completes successfully while `sshd.service` remains in a long-running start job.

## Key observations

- `systemctl show -p After sshd` still lists `pre-nixos.service`, indicating sshd retains an ordering dependency on the provisioning unit. 【F:docs/work-notes/2025-10-13T13-06-59Z-sshd-pre-nixos-debug/systemctl_status_pre_nixos.txt†L1-L4】
- `systemctl list-jobs` shows job 275 (`sshd.service`) in `start` state even after `pre-nixos.service` has stopped. 【F:docs/work-notes/2025-10-13T13-06-59Z-sshd-pre-nixos-debug/systemctl_status_sshd.txt†L1-L5】
- `systemctl status pre-nixos` reports the service inactive (dead) with the provisioning journal confirming the storage plan applied and the network rename succeeded. 【F:docs/work-notes/2025-10-13T13-06-59Z-sshd-pre-nixos-debug/serial.log†L55-L158】
- `systemctl status sshd` shows the daemon stuck in the `start-pre` phase running `sshd-pre-start` while host keys are generated, despite `secure_ssh` invoking `systemctl reload-or-restart --no-block sshd`. 【F:docs/work-notes/2025-10-13T13-06-59Z-sshd-pre-nixos-debug/serial.log†L77-L90】
- `/run/pre-nixos/storage-status` contains `STATE=applied` and `DETAIL=auto-applied`, confirming the storage plan completed. 【F:docs/work-notes/2025-10-13T13-06-59Z-sshd-pre-nixos-debug/serial.log†L198-L200】
- Metadata captures the boot image derivation, deriver, and embedded root key fingerprint for traceability. 【F:docs/work-notes/2025-10-13T13-06-59Z-sshd-pre-nixos-debug/metadata.json†L1-L12】

