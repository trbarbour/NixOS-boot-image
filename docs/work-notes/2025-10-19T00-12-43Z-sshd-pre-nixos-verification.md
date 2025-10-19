# sshd/pre-nixos verification snapshot (2025-10-19T00:12:43Z)

## Overview
- Re-ran the BootImageVM regression suite with the debug flag to confirm the harness still passes end-to-end while providing a fresh ISO build for this verification step.
- Captured systemd job status, sshd/pre-nixos unit state, network diagnostics, and storage status from a paused debug session immediately after LAN configuration completed.
- Captured a second set of artefacts after waiting for `pre-nixos.service` to finish to prove the non-blocking sshd restart proceeds independently once provisioning completes.

## Test executions
- `nix develop .#bootImageTest -c pytest tests/test_boot_image_vm.py -vv --boot-image-debug`
  - Duration: ~9m52s
  - Result: pass (both VM scenarios passed)
  - Reference: `docs/work-notes/2025-10-19T00-12-43Z-sshd-pre-nixos-verification/` (harness + serial logs)

## Debug artefacts (LAN configured, provisioning active)
- Directory: `docs/work-notes/2025-10-19T00-12-43Z-sshd-pre-nixos-verification/`
- Key observations:
  - `systemctl list-jobs`: `sshd.service` queued in `start waiting` while `pre-nixos.service` continues running (`systemctl_list_jobs.txt`).
  - `systemctl status pre-nixos`: service is still in `activating (start)` performing disk provisioning and invoking the non-blocking sshd restart (`systemctl_status_pre_nixos.txt`).
  - `systemctl status sshd`: unit remains `inactive (dead)` while the queued job waits for provisioning to finish (`systemctl_status_sshd.txt`).
  - `networkctl status lan`: LAN interface is routable with DHCP lease acquired; network prerequisites satisfied (`networkctl_status_lan.txt`).
  - `journalctl -u pre-nixos.service -b`: logs record the `systemctl reload-or-restart --no-block sshd` invocation immediately after securing the SSH key.

## Debug artefacts (post `pre-nixos` completion)
- Directory: `docs/work-notes/2025-10-19T00-12-43Z-sshd-pre-nixos-verification/post-pre-nixos`
- Key observations:
  - `systemctl list-jobs`: only the sshd start job remains and is actively running, proving it unblocks as soon as `pre-nixos` exits (`systemctl_list_jobs_after.txt`).
  - `systemctl status pre-nixos`: service is `inactive (dead)` with `status=0/SUCCESS` (`systemctl_status_pre_nixos_after.txt`).
  - `systemctl status sshd`: unit sits in `start-pre`, generating host keys independently (`systemctl_status_sshd_after.txt`).
  - `journalctl -u pre-nixos.service -b`: confirms the provisioning plan succeeded and `pre-nixos` shut down cleanly (`journalctl_pre_nixos_after.txt`).
  - `/run/pre-nixos/storage-status`: reports `STATE=applied` and `DETAIL=auto-applied` (`storage_status_after.txt`).

## Follow-up
- Update the task queue to record completion of the sshd/pre-nixos verification item.
- Use these artefacts when auditing dependent services (task queue item 2) to ensure no other units pull sshd online prematurely.
