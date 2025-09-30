# Boot Image Test Report — 2025-09-29

- **Tester:** Automated CI agent
- **Command:** `pytest tests/test_boot_image_vm.py -vv`
- **Environment:** Ubuntu 24.04 container; Nix 2.31.2 (single-user); QEMU 8.2.2; Python 3.11.12 with `pexpect` 4.9.0; virtualization without KVM acceleration.
- **Result:** ❌ Failed — the VM boots but the pre-nixos storage provisioning service reports an error and the console only presents an automatic login as the unprivileged `nixos` user, so the tests hang waiting for a root shell.

## Failure Details

The ISO build now succeeds after enabling the `nix-command` and `flakes` experimental features. QEMU successfully boots the generated image, but the serial console shows the following warning immediately after login:

```
pre-nixos: Storage detection encountered an error; provisioning ran in plan-only mode.
             Check 'journalctl -u pre-nixos' for details before continuing.
```

Because the boot sequence auto-logs into the `nixos` account, the integration harness never sees a `root@…#` prompt, so `pexpect` blocks until manual interruption. The captured console log ends with:

```
[nixos@nixos:~]$ root
-bash: root: command not found
```

## Next Steps

- Investigate the `pre-nixos` service failure (e.g., capture `journalctl -u pre-nixos` inside the VM) to understand why storage detection falls back to plan-only mode.
- Adjust the integration fixture to tolerate the automatic `nixos` login (e.g., elevate to root via `sudo -i`) so that subsequent test assertions can execute even if auto-login is enabled.
- Once storage provisioning is fixed, re-run `pytest tests/test_boot_image_vm.py` to validate both the storage and networking checks.
