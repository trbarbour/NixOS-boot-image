# sshd/pre-nixos debug capture (2025-10-13T13:06:59Z)

## Context
- Task queue item 1: verify sshd no longer blocks on `pre-nixos` after switching to `systemctl reload-or-restart --no-block`.
- Captured via `scripts/collect_sshd_pre_nixos_debug.py` using the freshly built ISO (`/nix/store/mris673jj79dhxz4jxmc7pfmmdrjb99m-nixos-24.05.20241230.b134951-x86_64-linux.iso`).

## Findings
- `pre-nixos.service` completed successfully (`inactive (dead)`) and applied the storage plan with `STATE=applied`/`DETAIL=auto-applied`. 【F:docs/work-notes/2025-10-13T13-06-59Z-sshd-pre-nixos-debug/serial.log†L55-L158】【F:docs/work-notes/2025-10-13T13-06-59Z-sshd-pre-nixos-debug/serial.log†L198-L200】
- `sshd.service` remained in `start running` with control PID `sshd-pre-start` generating host keys while the job stayed queued. 【F:docs/work-notes/2025-10-13T13-06-59Z-sshd-pre-nixos-debug/serial.log†L77-L90】
- `systemctl show -p After sshd` continues to list `pre-nixos.service` in the ordering set. 【F:docs/work-notes/2025-10-13T13-06-59Z-sshd-pre-nixos-debug/systemctl_status_pre_nixos.txt†L1-L4】

## Artefacts
- Logs and metadata: `docs/work-notes/2025-10-13T13-06-59Z-sshd-pre-nixos-debug/`

