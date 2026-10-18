# Migrating the dev environment from Codex to Claude Code cloud

## Context
- UTC window: 2026-10-18 01:56:17Z – 02:15:51Z (from `date -u`).
- Commit under test: `4bb90dd` (pre-nixos 0.8.8).
- Request: the user pasted the full text of `scripts/codex-setup.sh` into the
  Claude Code cloud environment's *Setup script* field. They asked (1) does this
  work, and (2) can the tests be run?
- Host: Ubuntu 24.04 VM, x86_64, 4 vCPU, 15 GiB RAM, **no `/dev/kvm`**, Python
  3.13.16, Nix 2.34.6 pre-installed (`/nix/var/nix/profiles/default/bin/nix`),
  outbound traffic through the agent proxy.

## Finding 1 — the pasted setup script cannot work as pasted

Observed at session start: no `.venv`, no `qemu-system-x86`, no
`~/.config/nix/nix.conf`. In other words, nothing the script produces was present.

Hypothesis: the script finds the repo from its own location
(`REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"`) and then runs
`source "${REPO_ROOT}/scripts/lib/nix_environment.sh"`. A pasted copy is not in
`scripts/`, so that `source` fails and `set -e` aborts before any work is done.

Experiment (isolated): copied the script to a scratch directory outside the repo
and ran `bash pasted.sh --help` there:

```
pasted.sh: line 9: <scratch>/scripts/lib/nix_environment.sh: No such file or directory
exit=1
```

The hypothesis is confirmed: the pasted copy exits 1 at line 9, before
`apt-get`, venv creation or Nix configuration. (The cloud docs say a non-zero
setup script stops the session from starting, yet this session started. Why is
unknown; it may have been started before the script was saved. Recorded as an
open question, see U1.)

Other problems with pasting, apart from the crash:
- It duplicates repo content outside version control (not DRY, and it will drift).
- The script installs no `openssh-client`, but the VM fixtures need `ssh` and
  `ssh-keygen` (`tests/vm/fixtures.py::_require_executable`). The Codex image
  must have shipped them.
- The `.venv` it creates lives inside the clone. The cloud docs say sessions
  start from a fresh clone, so whether a repo-local venv survives the
  environment snapshot is unverified (U2).

## Finding 2 — `github:` flake inputs cannot be fetched through the proxy

`nix build .#bootImage --impure` failed:

```
unable to download 'https://github.com/numtide/flake-utils/archive/11707dc….tar.gz': HTTP error 403
{"message":"GitHub access to this repository is not enabled for this session. …"}
```

Experiments:
| Probe | Result |
| --- | --- |
| `curl` `github.com/<o>/<r>/archive/<rev>.tar.gz` | 403 |
| `curl` `codeload.github.com/<o>/<r>/tar.gz/<rev>` | 403 |
| `curl` `api.github.com/repos/<o>/<r>/tarball/<rev>` | 403 |
| `nix flake prefetch 'git+https://github.com/numtide/flake-utils?rev=…&shallow=1'` | OK; NAR hash `sha256-l0KFg5…` equals `flake.lock` |
| Toy flake with a locked `github:` input whose content was **already in the store**, `nix eval` and `nix eval --offline` | still tries the tarball → 403 |

Conclusion: the proxy serves **git** transport for public repos but not
tarballs. Pre-populating the store does not help with Nix 2.34.6. What works is
overriding every input to a shallow `git+https` fetch of the same revision:

```
nix build .#bootImage --impure --no-link --print-out-paths \
  --override-input nixpkgs     'git+https://github.com/NixOS/nixpkgs?rev=c8aa8cc00a5cb57fada0851a038d35c08a36a2bb&shallow=1' \
  --override-input flake-utils 'git+https://github.com/numtide/flake-utils?rev=11707dc2f618dd54ca8739b309ec4fc024de578b&shallow=1' \
  --override-input disko       'git+https://github.com/nix-community/disko?rev=af087d076d3860760b3323f6b583f4d828c1ac17&shallow=1' \
  --override-input flake-utils/systems 'git+https://github.com/nix-systems/default?rev=da67096a3b9bf56a91d16901293e51ba5b49a27e&shallow=1'
```

This built
`/nix/store/27zkmaya3ay89pzkk9jxcg5jx0kk5wnd-nixos-minimal-25.05.20251022.c8aa8cc-x86_64-linux.iso`
in 5m11s (01:59:34Z → 02:04:45Z).

## Finding 3 — four unit tests are non-hermetic (fault; ticket text below)

`pytest -m "not vm"`: **4 failed, 202 passed**.
- `tests/test_cli.py::test_cli_interactive_confirms_before_apply`
- `tests/test_cli.py::test_cli_abort_when_confirmation_declined`
- `tests/test_tui.py::test_draw_plan_assigns_initial_focus`
- `tests/test_tui.py::test_handle_apply_plan_runs_auto_install`

Root cause (proven): these tests do not stub
`storage_detection.detect_existing_storage`, so they scan the host's real disks.
Here `wipefs -n /dev/vda` exits 1 (`probing initialization failed: Operation
not permitted`), so the scan raises. Experiment: an autouse fixture that stubs
only that function to return `[]` gives **206 passed**, so the host scan is
necessary and sufficient for the failures.

I could not open a GitHub issue: the API returned `403 Resource not
accessible by integration`. Per AGENTS.md, this report stands in for the
ticket until one can be filed. Proposed fix: stub the scan in these tests (or in
a shared `conftest.py` fixture), and add an explicit test for the "scan raised"
branch.

## Test results in this session
| Suite | Prerequisites added by hand this session | Result |
| --- | --- | --- |
| `pytest -m "not vm"` | `python3 -m venv .venv`; `pip install -r requirements-dev.txt` | 202 passed, 4 failed (Finding 3) |
| `pytest -m vm` attempt 1 | + `apt-get install qemu-system-x86 qemu-utils` | 4 errors: `ssh-keygen` missing |
| `pytest -m vm` attempt 2 | + `apt-get install openssh-client`, flakes enabled in `~/.config/nix/nix.conf` | 4 errors: flake input 403 (Finding 2) |
| `pytest -m vm` attempt 3 | + session-local `nix` wrapper on `PATH` adding the overrides above to `nix build` | **4 passed in 644 s** (02:05:06Z → 02:15:51Z), TCG emulation (no KVM); logs in `notes/2026-10-18T020839Z-vm-run/`, `notes/2026-10-18T021158Z-vm-run/` |

## Unknowns (to resolve before the setup design is finalised)
- U1: Why did the session start despite a setup script that exits 1? Was it saved
  before this session was created?
- U2: Is the repository already cloned when the setup script runs, at what path,
  and does the snapshot keep files written inside the clone (e.g. `.venv`)?
  Test: a setup script that logs `pwd`, `ls /home/user`, `date -u` to
  `/root/setup-probe.log`, then inspect it in the next session.
- U3: Can the setup script finish in under ~5 min, the limit for the environment
  to be cached? (APT for qemu takes about a minute here; the ISO build does not
  belong in the setup script.)

## Design options (to be decided by the user)
Requirements: R1, a fresh cloud session can run the **whole** suite without manual
steps; R2, provisioning lives in the repo (versioned, traceable, DRY);
R3, the cloud setup script must exit 0, and finish in under ~5 min to be cached.

Where provisioning lives:
- A. Keep pasting the script. Rejected: breaks R2, and the copy crashes as shown.
- B. The setup field holds a one-line bootstrap that calls a repo script for
  VM-level packages (apt: qemu, openssh-client; Nix flakes config). This depends
  on U2.
- C. A SessionStart hook in `.claude/settings.json` (versioned) runs an
  idempotent project script: venv + `pip install -e .[test]`. Runs every session;
  APT installs here would not be cached.
- Recommended: B for the system layer plus C for the project layer, which is the
  split the cloud docs recommend.

How to fetch flake inputs:
- F1. Change `flake.nix` inputs to `git+https://…&shallow=1`. Works everywhere,
  but changes the project for one environment's sake, and
  `scripts/update_nixos_stable.py` rewrites `github:` URLs.
- F2. Leave the flake alone. The VM fixture appends extra `nix build` arguments
  from an environment variable, and a repo script derives the
  `--override-input` list from `flake.lock` (DRY, explicit, testable).
- F3. Install a `nix` wrapper on `PATH` (what this session did). Least code, but
  hidden behaviour; rejected for permanent use.
- Recommended: F2.
