# 2025-10-15T00:47:19Z Boot image VM regression run

## Summary
- Rebuilt the boot ISO via `nix build .#bootImage`; the resulting symlink resolved to `/nix/store/hyr4rdw42b7935kbczzk8h30fqfbhd1y-nixos-24.05.20241230.b134951-x86_64-linux.iso`.
- Attempted to run `pytest tests/test_boot_image_vm.py -vv` inside `nix develop .#bootImageTest` with `TMPDIR=/tmp`. The fixture's impure `nix build .#bootImage` call failed immediately, aborting both VM tests before the QEMU harness started.
- Re-ran the exact `nix build .#bootImage --impure --no-link --print-out-paths` command (first with the host `nix`, then via `nix develop .#bootImageTest -c ...`). Both invocations succeeded, so the failure appears to be isolated to the fixture execution.

## Command log
```shell
# rebuild ISO
nix build .#bootImage
readlink -f result

# pytest run inside the devshell (fails during fixture setup)
TMPDIR=/tmp nix develop .#bootImageTest -c pytest tests/test_boot_image_vm.py -vv

# manual retries of the fixture command
PRE_NIXOS_ROOT_KEY=/tmp/nix-shell.qywJXF/pytest-of-root/pytest-0/boot-image-ssh-key0/id_ed25519.pub \
  nix build .#bootImage --impure --no-link --print-out-paths
TMPDIR=/tmp nix develop .#bootImageTest -c env PRE_NIXOS_ROOT_KEY=/tmp/nix-shell.qywJXF/pytest-of-root/pytest-0/boot-image-ssh-key0/id_ed25519.pub \
  nix build .#bootImage --impure --no-link --print-out-paths
```

## Observations
- The pytest fixture failed after ~31 seconds, reporting that `/nix/store/sxdfwpm10pwks6cppwbk2w9vqyxk8dpg-nixos-24.05.20241230.b134951-x86_64-linux.iso.drv` exited non-zero. No additional diagnostics were emitted before pytest aborted the session.
- Manual replays of the same command (both outside and inside the devshell) completed successfully, producing `/nix/store/49m7n0iaz9v4clk8zl9hf2srbn7gap9p-nixos-24.05.20241230.b134951-x86_64-linux.iso`.
- The failure only occurs when pytest drives the build, so we likely need to capture the failing derivation's full log during the fixture run or determine whether the devshell's `nix` environment is mutating `TMPDIR`/impurity inputs mid-build.

## Next steps
- Instrument the pytest fixture to preserve `stderr` from the failed impure build so we can see why `nixos-24.05...iso.drv` terminated.
- Compare the devshell's environment (e.g., `nix.conf`, `TMPDIR`, `NIX_CONFIG`) during fixture execution versus manual runs.
- Once the fixture build succeeds, rerun the full VM tests to gather provisioning and networking logs.
