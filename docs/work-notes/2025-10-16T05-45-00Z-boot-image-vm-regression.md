# 2025-10-16T05:45:00Z boot-image VM regression attempt

- Executed `TMPDIR=/tmp NIX_LOG=debug nix develop .#bootImageTest -c pytest tests/test_boot_image_vm.py -vv`.
- Pytest session stalled while `nix build .#bootImage --impure --no-link --print-out-paths` rebuilt the ISO with a freshly generated `PRE_NIXOS_ROOT_KEY`.
- After ~115s the `boot_image_build` fixture failed because the ISO derivation `/nix/store/26zylzprcx44248ypkg39yk6hp66qcf5-nixos-24.05.20241230.b134951-x86_64-linux.iso.drv` exited with status 1 before producing a build log.
- Retried `nix build .#bootImage --impure --print-build-logs` with the generated public key. The build progressed through `pre-nixos-0.1.0` and began `mksquashfs`, then stalled for >15 minutes with active `mksquashfs` processes (`ps -ef | grep mksquashfs` showed >99% CPU) but never emitted a failure message.
- Unable to obtain `/nix/store/26zylzprcx44248ypkg39yk6hp66qcf5-nixos-24.05...iso.drv` logs because `nix log` reports "build log ... is not available".
- Next steps: determine why the ISO builder silently fails (or stalls) under `--impure` with a temporary `PRE_NIXOS_ROOT_KEY`. Inspect nix-daemon logs or rerun with `--keep-failed` once sufficient wall-clock time is available; capture `mksquashfs` output to confirm whether the process exits or deadlocks.
