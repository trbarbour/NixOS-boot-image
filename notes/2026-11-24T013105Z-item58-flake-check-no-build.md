# Item 58: `nix flake check --no-build` (2026-11-24)

Task queue item 58: on 2026-11-23, `nix flake check --no-build` stopped at `packages.x86_64-linux.default` with `error: path '…' is not valid`. Nix 2.34.6, in a Claude Code cloud container where `PRE_NIXOS_NIX_GIT_INPUTS=1` (the git overrides of `scripts/nix_git_inputs.py`).

## Reproduction (01:31Z, main = ada5c4c, clean tree)
- `scripts/nix_git_inputs.py flake check --no-build --show-trace` failed, but **not** as on 2026-11-23. It failed in the `image-file-names` check: `SD file name pre-nixos-0.33.0-20261123021506-s83fdf3aa-sd-card-… does not start with the pre-nixos version`.
- That gave two unknowns:
  - **U1:** why the image name carries no commit;
  - **U2:** the original "path … is not valid".

## U2: "path is not valid" under `--no-build`
- **H1:** `--no-build` evaluates against a read-only store, so a path that evaluation adds to the store and then reads back does not exist.
- **Experiment (01:33Z):** one toy flake per case, no inputs, one package each, `nix flake check --no-build path:<dir>`:

  | case | result |
  | --- | --- |
  | (a) `builtins.path` copy, only referenced in a string | ok |
  | (b) `builtins.path` copy, then `readFile` | `path '…-c-b.txt' is not valid` |
  | (c) `builtins.toFile`, then `readFile` | `path '…-c-c.txt' is not valid` |
  | (d) `builtins.path` copy, then `import` | `path '…-c-d.nix' is not valid` |
  | (e) `readFile` of a file in the flake source | ok |
  | (f) `import` of a file in the flake source | ok |

- **Control:** `nix eval …#packages.x86_64-linux.default.drvPath` on (b), (c) and (d) gives a `.drv` each.
- **Conclusion: H1 holds.** It is a property of Nix's `--no-build`, not a fault of the flake. The flake legitimately reads back paths it creates: the site's key (`…-pre-nixos-root-key.pub`) and generated Nix files (`…-pre-nixos-boot.nix`), the two paths seen on 2026-11-23.
- **Decision:** do not restructure the flake for `--no-build`. Instead, `scripts/eval_checks.py` evaluates every check's `drvPath`, which runs every check's assertions without building, and works (26/26).

## U1: the image name without a commit
- With the git overrides the ISO is `pre-nixos-0.33.0-20261123021506-s83fdf3aa-…`. Without them (inputs already in the store) it is `pre-nixos-0.33.0-g23374f6-…`.
- **Half-split (between 01:33:44Z and 01:36:37Z, the clock readings around it):** each of the four git overrides alone (disko, flake-utils, flake-utils/systems, nixpkgs) drops the revision. So does `--override-input site path:./nix/site-default` alone, the README's site build, giving the same `image-file-names` failure.
- **Toy flake (same interval),** one `git+file` input overridden by another:

  | tree | override | `self` has |
  | --- | --- | --- |
  | clean | none | `shortRev` |
  | clean | one input | **nothing** (neither `shortRev` nor `dirtyShortRev`) |

  An earlier toy run showed `dirtyShortRev` for "clean + override", but its `flake.lock` was uncommitted; discarded.
- **Unexplained, recorded:** a toy that also had a relative `path:./sub` input gave `dirtyShortRev` with an override on a clean tree. The repo has such an input (`site`) and gives nothing. It doesn't affect the fix, which accepts both.
- **Root cause:**
  - the flake already knows that Nix gives no revision under `--override-input`: `sourceIdOf` falls back to the commit date and a source hash (#332, flake check `source-id`);
  - but `image-file-names` still asserted `hasPrefix "pre-nixos-<version>-g"`, from 0.21.0 (de627b2, 2026-10-22), before that fallback;
  - so `nix flake check --override-input site path:<dir>` failed on any clean tree. CI never saw it: its checkout has a revision and it overrides nothing.

## Fix (0.33.1)
- `image-file-names` now asserts:
  - the name starts with `pre-nixos-<version>-<sourceRev>-`;
  - `sourceRev` starts with `g` exactly when Nix gives the flake a revision.
- **Test first:**
  - `tests/test_eval_checks.py` failed at collection (no script);
  - `scripts/eval_checks.py --override-input site path:./nix/site-default` failed with the error above before the fix.
- **After the fix:** 26 checks evaluated, in three states:
  - with the site override;
  - without overrides;
  - on a dirty tree with the git overrides.
- CI now runs `python3 scripts/eval_checks.py --override-input site path:./nix/site-default` after `nix flake check`, and a unit test keeps that step in the workflow.
