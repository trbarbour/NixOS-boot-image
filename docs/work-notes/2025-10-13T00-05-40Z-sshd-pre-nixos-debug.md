# sshd vs pre-nixos verification (2025-10-13T00:05:40Z)

## Context
- **Task queue item:** Verify the sshd/pre-nixos interaction after switching `secure_ssh` to `systemctl reload-or-restart --no-block`.
- **ISO under test:** `/nix/store/hln7xwr47dgjsjpm4fs9l108cyl963f7-nixos-24.05.20241230.b134951-x86_64-linux.iso` (deriver `/nix/store/pjkszgq0cp77s9fk1pkzq76bfa305r18-nixos-24.05.20241230.b134951-x86_64-linux.iso.drv`).
- **SSH key:** Reused `/tmp/pytest-of-root/pytest-1/boot-image-ssh-key0/id_ed25519.pub` from the pytest fixture so the script could reuse the cached build.

## Actions
1. Installed `pexpect` via `pip install -r requirements-dev.txt` and reran the VM regression with interactive debugging enabled:
   - Command: `pytest tests/test_boot_image_vm.py -vv --boot-image-debug`
   - Result: both tests failed after ~11m44s. The fixture attempted to drop into the interactive debug shell but `pexpect` raised `termios.error: (25, 'Inappropriate ioctl for device')`, so no manual commands could be entered. Harness and serial logs were copied to `docs/work-notes/2025-10-13T00-05-40Z-sshd-pre-nixos-debug/pytest-run/`. 【F:docs/work-notes/2025-10-13T00-05-40Z-sshd-pre-nixos-debug/pytest-run/harness.log†L120-L139】【3ff5fa†L1-L133】
2. Collected automated diagnostics with `python scripts/collect_sshd_pre_nixos_debug.py --public-key … --output-dir docs/work-notes/2025-10-13T00-05-40Z-sshd-pre-nixos-debug`.
   - Captured command outputs under `docs/work-notes/2025-10-13T00-05-40Z-sshd-pre-nixos-debug/` alongside `harness.log` and `serial.log`.
   - The script shut the VM down automatically after gathering the data.

## Findings
- **Pre-nixos completion:** `systemctl status pre-nixos` reports the oneshot finished successfully in 5.777s. 【F:docs/work-notes/2025-10-13T00-05-40Z-sshd-pre-nixos-debug/networkctl_status_lan.txt†L1-L20】
- **Journal excerpts:** Structured journal entries confirm LAN detection, DHCP assignment, and that `systemctl reload-or-restart --no-block sshd` returned `status": "success"` within ~0.5s. They also show the provisioning plan contained the expected `main` VG and `slash` LV. 【F:docs/work-notes/2025-10-13T00-05-40Z-sshd-pre-nixos-debug/storage_status.txt†L3-L68】
- **Outstanding sshd job:** Immediately after pre-nixos exited, `systemctl list-jobs` still showed `sshd.service` in `start running` state. 【F:docs/work-notes/2025-10-13T00-05-40Z-sshd-pre-nixos-debug/journalctl_pre_nixos.txt†L1-L5】
- **Ordering:** `systemctl show -p After sshd` still lists `pre-nixos.service` in `After=…`, so sshd retains an ordering dependency on the pre-nixos oneshot even after the non-blocking restart change. 【F:docs/work-notes/2025-10-13T00-05-40Z-sshd-pre-nixos-debug/systemctl_status_pre_nixos.txt†L1-L4】
- **Networking:** `networkctl status lan` confirms the `lan` interface is routable with DHCPv4 `10.0.2.15`. 【F:docs/work-notes/2025-10-13T00-05-40Z-sshd-pre-nixos-debug/networkctl_status_lan.txt†L1-L20】

## Gaps and follow-ups
- The pytest harness still mis-parses `systemctl is-active pre-nixos` output because the prior IPv4 probe output bleeds into the assertion context; this mirrors earlier failures and prevented the tests from exercising the SSH checks. 【3ff5fa†L94-L118】
- Interactive debugging from pytest is blocked by the container TTY limitation; further CLI automation (or adapting `collect_sshd_pre_nixos_debug.py` to grab `systemctl status sshd --no-pager`) is needed to capture the sshd unit state directly.
- `systemctl_show_sshd.txt` and `systemctl_list_jobs.txt` only captured the echoed command (`'` / `:`). The full job table and ordering details are present in the neighbouring files noted above, but the script should probably write each command's output into the matching file to avoid confusion.
