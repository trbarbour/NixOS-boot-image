# 2025-10-14T00:00:00Z sshd/pre-nixos verification

## Summary

`collect_sshd_pre_nixos_debug.py` captured a fresh VM run after the non-blocking sshd restart change. `pre-nixos.service` now exits cleanly with `STATE=applied`, yet `sshd.service` continues to report an active start job while host keys are generated.

## Key observations

- `systemctl show -p After sshd` still lists `pre-nixos.service`, so the sshd job retains an ordering dependency on the provisioning unit. 【F:docs/work-notes/2025-10-14T00-00-00Z-sshd-pre-nixos-verify/systemctl_status_pre_nixos.txt†L1-L5】
- `systemctl list-jobs` reports job 262 (`sshd.service`) in `start running` even after the oneshot finishes. 【F:docs/work-notes/2025-10-14T00-00-00Z-sshd-pre-nixos-verify/systemctl_status_sshd.txt†L1-L6】
- `systemctl status pre-nixos` shows the oneshot inactive and the journal confirms the plan applied with no pending work. 【F:docs/work-notes/2025-10-14T00-00-00Z-sshd-pre-nixos-verify/journalctl_pre_nixos.txt†L1-L13】
- `systemctl status sshd` remains in `start-pre` running `sshd-pre-start` to generate a 4096-bit RSA host key; this work continues independently of the completed `pre-nixos` run. 【F:docs/work-notes/2025-10-14T00-00-00Z-sshd-pre-nixos-verify/serial.log†L70-L91】
- `/run/pre-nixos/storage-status` contains `STATE=applied`/`DETAIL=auto-applied`, confirming the storage workflow succeeded under the new build. 【F:docs/work-notes/2025-10-14T00-00-00Z-sshd-pre-nixos-verify/serial.log†L120-L141】
- Metadata records the ISO derivation, deriver, and embedded root key fingerprint for traceability. 【F:docs/work-notes/2025-10-14T00-00-00Z-sshd-pre-nixos-verify/metadata.json†L1-L12】
