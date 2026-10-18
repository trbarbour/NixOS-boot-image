# Claude Code cloud environment migration audit

- Start: 2026-10-18 01:56:34Z. Note written: 2026-10-18 02:01:07Z.
- Trigger: the user pasted `scripts/codex-setup.sh` into the Claude Code environment's *Setup script* box, and the setup failed.
- Ticket: creating GitHub issues returned `403 Resource not accessible by integration`, so this note stands in for the two tickets below (F1 and F2).

## Host facts

- Nix 2.34.6 is preinstalled in the image (`/nix/receipt.json`, NixOS/nix-installer), and `/etc/nix/nix.conf` enables `nix-command flakes`. `nix store info` reports `Store URL: local`, `Trusted: 1`.
- Python 3.13.16. apt is available, and we run as root.
- There is no `/dev/kvm`, so QEMU can only use TCG software emulation.
- The block devices `vda`…`vdf` exist, but `wipefs -n /dev/vda` fails with `probing initialization failed: Operation not permitted`.

## F2: the setup script fails when pasted

- Hypothesis: the pasted script can't find `scripts/lib/nix_environment.sh`, because `REPO_ROOT` is derived from `BASH_SOURCE[0]`.
- Experiment: I copied the script to a scratch directory outside the repo and ran it.
  Result: `.../scripts/lib/nix_environment.sh: No such file or directory`, exit 1. Hypothesis confirmed.
  Caveat: I have not seen the environment's own setup log, so this is the *likely* cause of the user's failure, not a proven one.
- Control: `./scripts/codex-setup.sh` run from inside the repo exits 0. It installed the apt packages (including `qemu-system-x86_64` and `qemu-img`), created `.venv`, installed `requirements-dev.txt` (pytest 9.1.1, pexpect 4.9.0), and linked the nix binaries into `/usr/local/bin`.

## Test run (`.venv/bin/pytest -q`)

`4 failed, 202 passed, 4 errors in 9.29s`.

### F1: non-hermetic unit tests (4 failures)

- Failing tests: `test_cli.py::test_cli_interactive_confirms_before_apply`, `test_cli.py::test_cli_abort_when_confirmation_declined`, `test_tui.py::test_draw_plan_assigns_initial_focus` and `test_tui.py::test_handle_apply_plan_runs_auto_install`.
- Evidence:
  - The CLI test's captured stdout says `Failed to inspect existing storage: command wipefs -n /dev/vda exited with status 1`.
  - Calling `storage_detection.detect_existing_storage()` directly raises the same `RuntimeError`.
  - The TUI header shows `Existing storage scan failed; …` (from `tui._initial_cleanup_notice`), which moves the focus marker the test expects.
- Root cause: these tests run the real storage scan against the host's disks.
- Proposed fix: fake `detect_existing_storage` in those tests, or in an autouse fixture in `tests/conftest.py`.

### VM tests (4 errors)

- `ssh-keygen` and `ssh` are missing, so the VM fixtures fail (the intended behaviour). Fix: add `openssh-client` to the setup script's apt package list.
- No KVM means boots run under TCG. Whether they finish within the harness timeouts has not been measured.

## The proxy blocks `github:` flake inputs

- `nix eval --raw .#bootImage.drvPath` fails with HTTP 403 when fetching
  `https://github.com/numtide/flake-utils/archive/11707dc….tar.gz`
  ("GitHub access to this repository is not enabled for this session"). The session proxy serves anonymous *git* reads of public repos, but not archive tarballs.
- Workaround (verified): override every input with `git+https://…?rev=<locked>&shallow=1`:

  ```
  nix eval --raw .#bootImage.drvPath \
    --override-input flake-utils 'git+https://github.com/numtide/flake-utils?rev=11707dc2f618dd54ca8739b309ec4fc024de578b&shallow=1' \
    --override-input flake-utils/systems 'git+https://github.com/nix-systems/default?rev=da67096a3b9bf56a91d16901293e51ba5b49a27e&shallow=1' \
    --override-input disko 'git+https://github.com/nix-community/disko?rev=af087d076d3860760b3323f6b583f4d828c1ac17&shallow=1' \
    --override-input nixpkgs 'git+https://github.com/NixOS/nixpkgs?rev=c8aa8cc00a5cb57fada0851a038d35c08a36a2bb&shallow=1'
  ```

  This took 1m29s and produced `/nix/store/rmhwpzbb80vi82nhfih0a3fgpm98iay6-nixos-minimal-25.05.20251022.c8aa8cc-x86_64-linux.iso.drv`.
- Fetching from `cache.nixos.org` works (`nix build nixpkgs#hello` was substituted).
- The ISO has not been built yet.

## Unknowns and plan

1. Is the repo already cloned when the setup script runs? → Check the environment documentation, or test with a one-line setup script that logs `pwd` and `ls`.
2. How long does a VM boot take under TCG, and does it fit the harness timeouts? → Build the ISO once (save the store path for reuse), then run `pytest tests/vm -vv` once and record the timings.
3. Which fix for `github:` inputs is best: a helper script, `git+https` inputs in `flake.nix`, or attaching the repos to the environment? → Design debate before any change.
