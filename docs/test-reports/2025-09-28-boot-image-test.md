# Boot Image Test Report — 2025-09-28

- **Tester:** Automated CI agent
- **Command:** `pytest tests/test_boot_image_vm.py`
- **Environment:** Ubuntu 24.04 container; Nix 2.18.1 (`nix-bin` via APT); QEMU 8.2; Python 3.11 with `pexpect`
- **Result:** ❌ Failed — the Nix build step cannot download required sources because outbound HTTPS requests to the Nix binary cache (`cache.nixos.org`) and GNU mirrors are blocked by the execution environment's proxy.

## Failure Details

The integration tests invoke `nix build .#bootImage --no-link --print-out-paths`. The build aborts immediately when Nix attempts to fetch `nix-cache-info` and subsequently the `bash-5.2.tar.gz` source tarball. Both downloads terminate with `Failure when receiving data from the peer (56)` and the proxy returns HTTP 403. Without access to the binary cache or source mirrors, Nix falls back to building from source, which is impossible under these network restrictions, so the VM tests cannot proceed.

Full pytest output (abridged):

```
warning: error: unable to download 'https://cache.nixos.org/nix-cache-info': Failure when receiving data from the peer (56)
...
error: builder for '/nix/store/5jrd75v747s76s16zxk59384xfcjqn58-bash-5.2.tar.gz.drv' failed with exit code 1
```

## Next Steps

- Ensure the test environment can reach `https://cache.nixos.org/` and GNU source mirrors (`https://ftp.gnu.org/` or `https://ftpmirror.gnu.org/`).
- Re-run `pytest tests/test_boot_image_vm.py` once network access is restored to confirm the boot image builds and boots inside QEMU.
