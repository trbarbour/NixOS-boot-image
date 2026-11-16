# The VM harness and scripts under `mypy --strict` (design)

_2026-11-16T00:42:09Z. Task queue item 7._

**Problem.** `tests/vm/` (the VM harness and its tests) and `scripts/` (the VM debug tools) were outside the strict mypy list in `pyproject.toml`. An API change in the harness could leave a script or a test calling the old API, and only a run would show it. Item 19 had just shown this: two callers of `build_boot_image` were missed and only an ad-hoc AST test caught them (Codex on #360).

## 1. Requirement
- **R-T1:** every Python module under `tests/vm/` and `scripts/` passes `mypy --strict` in CI, as `pre_nixos/` and `write_image/` modules do. A new module there is checked from its first commit.
- Traces to the user's preferences (bugs at compile time; strong static typing) and to item 7's own aim, "drift between script and harness APIs is caught at check time rather than at run time".

## 2. Design debate
### Scope
- **(A) Chosen: the whole of both directories, tests included.** The test files call the harness APIs as much as the scripts do. Measured cost: 120 errors over 14 files (2026-11-16T00:36:52Z), most of them mechanical.
- (B) Only the harness's support modules and the scripts: 58 errors. It leaves the test files' calls unchecked, which is half of the drift the item is about.

### How the directories are listed
- **(A) Chosen: the directories themselves** (`"scripts"`, `"tests/vm"` in `files`). A new module is checked at once; there is no list to forget.
- (B) One entry per file, as for `pre_nixos/`. That list is a ratchet for a package that is not yet clean; these two directories are clean in full, so a ratchet adds nothing.

### pexpect, which ships no type information
- **(A) Chosen: typeshed's stubs, `types-pexpect==4.9.0.20260518`** in `requirements-dev.txt`. It exists on PyPI (checked with `pip download` and `pip index versions`) and matches `pexpect>=4.9`. `spawn` is typed and generic (`spawn[str]` with an encoding).
- (B) `ignore_missing_imports` for pexpect: everything from pexpect becomes `Any`, so the controller's central object is unchecked.
- (C) A local `Protocol` for the child process (`sendline`, `expect`, `before`, …; nine members are used). The controller would then depend on an interface, and the test doubles would be checked against it. Rejected for now: the real child is always `pexpect.spawn`, and the doubles each implement only what one test needs. (A) gives the real types at no cost to the code. Worth revisiting if the doubles drift from pexpect.

### Module names
- `tests/` has no `__init__.py`, so mypy saw `tests/vm/__init__.py` both as `vm` and as `tests.vm`.
- **(A) Chosen: `explicit_package_bases = true`.** Config only; module names are taken from the repository root, as the code imports them (`tests.vm…`, `scripts…`).
- (B) Add `tests/__init__.py`. It changes how pytest imports every test module (rootdir-relative package names), for a type-checker's sake. Rejected.

### Test doubles that replace methods
- The controller's unit tests patch methods on an instance (`vm.run = fake_run`) and put stand-ins in `vm.child`. mypy reports these as `method-assign` and `assignment`.
- **Chosen:** keep the patches, with `# type: ignore[<code>]` naming the exact code. mypy's `warn_unused_ignores` (part of `--strict`) then reports any that become unnecessary. Lambdas whose type mypy cannot infer became typed local functions. A fake for `_raise_with_transcript` now declares `NoReturn`, as the real method does.
- Rejected: `monkeypatch.setattr` everywhere. It hides the same mismatch with no comment to show it.

## 3. Real defects found
- `_raise_with_transcript` always raises but was annotated `-> None`, so mypy saw four "missing return" paths. It is now `-> NoReturn`.
- `BootImageVM.run` passed `child.before` (typed `str | None`) to `clean_command_output`. A `None` there would have raised `AttributeError`; it now fails an assertion that names the command.
- Three copies of the free-port helper (`fixtures.allocate_ssh_forward_port`, `manual_vm_debug.allocate_ssh_port`, `collect_sshd_pre_nixos_debug.reserve_ssh_port`), plus a fourth in `test_installed_system_vm.py`. They are now one, in `tests/vm/fixtures.py` (DRY). `manual_vm_debug.allocate_ssh_port` stays as a thin wrapper, because other scripts and old notes import that name.
- `test_controller_unit.py` carried a "pexpect missing" branch with a fake pexpect module. pexpect is a declared test dependency, and the controller imports it unconditionally, so that branch could never run. Removed.
- **Not a typing error, found while checking:** `python scripts/manual_vm_debug.py` failed with `No module named 'scripts'`. Unlike its siblings, it did not put the repository root on `sys.path`. Test first: `tests/test_script_imports.py::test_script_runs_by_path` runs each script by path with `--help` from another directory; only `manual_vm_debug` failed. Fixed with the siblings' preamble.

## 4. Verification
- `mypy`: "Success: no issues found in 72 source files". Before the fixes: 120 errors in 14 files.
- Unit tests: 842 passed.
- Every script runs by path with `--help`.
- The VM test `tests/vm/test_pre_nixos_vm.py` checks the harness changes (the controller, fixtures and metadata) end to end.
