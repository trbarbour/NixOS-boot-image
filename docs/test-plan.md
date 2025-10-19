# Test Plan

This document captures the end-to-end validation strategy for the Pre-NixOS
boot image and CLI tooling.  It enumerates prerequisites, outlines how to
prepare the environment, and lists the mandatory test suites.

## 1. Toolchain Installation

1. Run the automation helper from the repository root to provision the tooling
   used by the Codex environment:

   ```bash
   ./scripts/codex-setup.sh
   ```

   The script installs required APT packages, provisions the Python virtual
   environment in `.venv`, installs `pytest` and `pexpect`, and bootstraps the
   single-user Nix CLI. Subsequent container starts execute
   `scripts/codex-maintenance.sh`, which refreshes Python dependencies and keeps
   the Nix profile sourced automatically.
2. Install the Nix package manager following the official instructions at
   <https://nixos.org/download> if the automated setup is skipped or fails.
3. Enter the dedicated development shell that provides all runtime test
   dependencies (Python, pytest, pexpect, QEMU, and the Nix CLI):

   ```bash
   nix develop .#bootImageTest
   ```

   The `bootImageTest` shell is defined in `flake.nix` and guarantees a
   consistent toolchain across developer laptops and CI agents.
4. Ensure network access to the public Nix binary cache and source mirrors:
   `https://cache.nixos.org/` and `https://ftpmirror.gnu.org/`.  These hosts are
   required for building the boot image.

## 2. Python Unit Tests

Run the fast unit-test suite directly from the repository root:

```bash
pytest
```

This exercises the inventory, planner, network configuration, TUI rendering,
CLI behaviour, and packaging invariants.  The suite must be green before
running slower integration scenarios.

## 3. Boot Image Integration Tests

The boot image tests build the ISO with Nix, boot it inside QEMU, and validate
end-to-end storage provisioning and DHCP configuration.

The first `nix build .#bootImage --impure --no-link` run can take several
minutes while the derivations are realised, so run it ahead of `pytest
tests/test_boot_image_vm.py` when possible. Subsequent invocations reuse the
cached derivations and complete much faster as long as the inputs remain
unchanged. When the build appears quiet, pass `--print-build-logs` to stream
its progress or inspect `/nix/var/log/nix/drvs/` with `tail -f` so you can tell
the job is still healthy.

```bash
pytest tests/test_boot_image_vm.py
```

These tests require hardware virtualisation support and may take several
minutes.  They are non-optional: failures or skips indicate inadequate testing.
Before running the suite:

1. Generate a disposable SSH key pair and export the public key so Nix can
   embed it into the boot image:

   ```bash
   ssh-keygen -t ed25519 -N '' -f /tmp/pre-nixos-test-key
   export PRE_NIXOS_ROOT_KEY=/tmp/pre-nixos-test-key.pub
   ```

2. Invoke `nix build --impure` (the test harness does this automatically) so
   `builtins.getEnv` can read `PRE_NIXOS_ROOT_KEY` during flake evaluation.  The
   integration tests generate their own ephemeral key pair per run, forward the
   VM's SSH port to the host, and assert that `ssh -i` connects as `root` using
   the generated private key.
3. Confirm the boot environment exposes the storage tooling by running
   `command -v disko` inside the VM; the automated tests assert the command is
   available so provisioning never begins without the required binary.

Inspect the generated serial console log (stored under
`/tmp/pytest-of-*/boot-image-logs/serial.log`) when debugging regressions.
Pass `--boot-image-debug` to `pytest` to keep the VM alive after a test failure
and drop into an interactive console (`Ctrl-]` to exit) before teardown.  The
harness transcript records the debug session boundaries for later analysis.

## 4. Manual Smoke Tests (optional but recommended)

For additional assurance before releases:

1. Boot the generated ISO on representative bare-metal hardware.
2. Confirm the `pre-nixos` CLI detects disks, produces a plan, applies it with
   `disko`, and that the resulting layout matches expectations.
3. Verify SSH access using the embedded public key and ensure the primary NIC is
   renamed to `lan` with an IPv4 lease.

## 5. Reporting

Record the outcome of each run (command, date, tester, result, and any
observations) in `docs/test-reports/`.  Link CI job URLs where applicable so the
history of test executions remains auditable.
