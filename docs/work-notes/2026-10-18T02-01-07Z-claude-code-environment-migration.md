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

---

## Follow-up session (2026-10-18 02:10Z–02:47Z): the three agreed fixes

The user approved three steps, done in this order: (1) a helper for the flake inputs, (2) hermetic tests, (3) setup and VM-test tools.

### Step 1: `scripts/nix_git_inputs.py` (commit `5c13f59`, version 0.9.0)

Design debate and decisions:

- **Form.** A Python module with a CLI, rather than a shell wrapper. It is unit-testable, and the VM fixtures and debug scripts can import it.
- **Where revisions come from.** Parsed from `flake.lock`, not hard-coded, so the lock stays the single source of truth.
- **Activation.** An explicit opt-in, `PRE_NIXOS_NIX_GIT_INPUTS=1`, validated strictly: only unset, `0` or `1` are accepted. Two alternatives were rejected. Auto-detection would need a network probe that could be flaky. Always-on would make normal hosts slower.
- **Integrity** (requirements §3: repeatable, deterministic builds). An override drops the locked `narHash`.
  - Experiment: `narHash` cannot go in a `git+https` URL. Nix 2.34 passes it through to git as part of the remote URL, and git gets a 403 even when the hash is correct.
  - Experiment: a git checkout hashes the same as the GitHub tarball for all four inputs (disko, flake-utils, systems, nixpkgs).
  - So the helper runs `nix flake metadata --json` with the overrides and compares every `narHash` against `flake.lock`. Any mismatch is a hard error.
- **Equivalence check.**
  - Commit `4bb90dd`, evaluated with the helper's overrides, gives `rmhwpzbb…`, identical to the hand-written overrides used earlier.
  - Later commits give other derivations because `src = ./.` takes in every tracked file. Queued as "narrow the flake's package source".

### Step 2: hermetic tests (commit `3cd63ea`, version 0.9.1)

- Design: (a) an autouse stub returning `[]`, or (b) an autouse stub that fails unless the test declares a scenario. Chose (b), because it exposes hidden dependencies on host storage.
- Experiment: a `BaseException` subclass escapes `except Exception`, pytest reports it as an ordinary failure, and the following tests still run. The stub uses one so that the production code's broad exception handlers can't hide an undeclared scan.
- Result: 9 tests reached the host scan, not 4. Five had been passing by accident.
- Added failure-path tests for the scanner, CLI, TUI header and TUI apply.

### Step 3: SessionStart hook (commit `e359f25`, version 0.9.2)

Facts from the docs (code.claude.com/docs/en/cloud-environments, read 2026-10-18):

- The setup script runs as root before Claude Code launches. Its result is cached as a filesystem snapshot for about 7 days.
- A SessionStart hook in the repo runs on every start and resume, with `$CLAUDE_PROJECT_DIR` set.
- Archive and codeload URLs get a 403 for repositories not attached to the session, public ones included.

Decisions:

- Project setup lives in the repo hook, not the environment's setup box.
- One APT list and one set of venv logic live in `scripts/lib/` and are shared with `codex-setup.sh`. `openssh-client` was added to the list.
- The hook installs only what is missing, and refreshes the venv only when its inputs' hash changes.
- The hook sets the git-input variable through `CLAUDE_ENV_FILE`.

Validation:

- The first run took 15 s; it installed `openssh-client` and refreshed the venv. The second run took 0.17 s and did nothing.
- `shellcheck -x -P SCRIPTDIR` is clean.
- **Anomaly while testing:** my "outside the cloud" check wrongly ran the hook, because this shell has `CLAUDE_CODE_REMOTE=true`. Re-run with the variable unset or `false`, the hook exits silently, as intended. That behaviour is now pinned by `tests/test_session_start_hook.py`.

### Observation: the ISO built without the variable set

- Hypothesis H1: tarballs are no longer blocked. **Refuted.** `nix flake prefetch github:numtide/flake-utils/b1d9ab7…`, a revision that was not in the store, still got a 403; the same revision over `git+https` worked.
- Hypothesis H2, consistent with the evidence: Nix reused sources already in the store with the same `narHash`, fetched by the earlier git-override runs.
- Consequence: a run that succeeds on a warm store doesn't prove fetching works. A fresh session needs the hook's variable.
