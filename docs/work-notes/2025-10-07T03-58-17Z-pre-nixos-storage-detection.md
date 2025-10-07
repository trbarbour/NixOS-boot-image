# Pre-NixOS storage detection failure investigation

## Context
- Date: 2025-10-07T03:58:17Z (UTC)
- Observer: Automation agent
- Trigger: Boot image VM continued to report `pre-nixos: Storage detection encountered an error; provisioning ran in plan-only mode.` on clean disks.

## Reproduction
1. Build the boot image via `nix build .#bootImage --no-link` (already present in store at `/nix/store/3xbxic9853jf4yzlsclfi4b2f21hk8hw-nixos-24.05.20241230.b134951-x86_64-linux.iso`).
2. Launch the VM harness (`BootImageVM`) against a fresh 4 GiB virtio disk.
3. Capture the systemd journal for `pre-nixos.service` immediately after the storage status file appears.

## Findings
- The unit log shows `pre-nixos-detect-storage` probing `/dev/fd0` and failing when `wipefs -n /dev/fd0` exits with status 1.
- Because the detection helper treats any non-zero exit status (except the explicit `1` signalling "no existing storage") as fatal, the failure forced the service into `plan-only` mode with `DETAIL=detection-error`.
- QEMU exposes a legacy floppy device by default; it should be ignored for provisioning checks just like the existing `/dev/loop`, `/dev/sr`, etc. prefixes.

## Journal excerpt
```
Oct 07 03:50:43 nixos pre-nixos-start[748]: pre-nixos-detect-storage: command wipefs -n /dev/fd0 exited with status 1
Oct 07 03:50:43 nixos pre-nixos-start[720]: pre-nixos: storage detection failed (exit 2), defaulting to plan-only
```

## Follow-up
- Update the storage detection ignore list to exclude `/dev/fd*` devices so that floppy controllers do not trigger fatal errors.
- Ensure the VM test emits the collected `journalctl -u pre-nixos.service` output when provisioning expectations fail (implemented alongside this investigation).
