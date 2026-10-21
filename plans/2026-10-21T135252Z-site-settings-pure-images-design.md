# Site settings for boot images, without impurity or keys in the repo (design)

User request (2026-10-21): supply the root SSH public key **without putting it in the repository** and without `--impure`, for **every** image (x86 ISO and AArch64 SD), through a `mkSdImage`-style function and a gitignored location.

Requirements traced:
- reqs §2.7: "Builders must replace the embedded key with their own before creating an image";
- reqs §2.3: auto-install is a build-time choice (today `PRE_NIXOS_AUTO_INSTALL`);
- the user's preference for referential transparency.

## 0. Facts (experiments, 2026-10-21, Nix 2.34.6, throwaway repos)

| Experiment | Result |
|---|---|
| `pre_nixos/root_key.pub` present but gitignored, pure build | **not seen.** A git flake only contains tracked files. |
| The same file staged with `git add -f`, pure | seen, but only by tracking the key: rejected |
| `PRE_NIXOS_ROOT_KEY` with `--impure` / pure | seen / not seen |
| A `flake = false` input `path:./nix/no-…` (empty default), then `--override-input <input> path:<dir>` | **pure, and the override is seen.** `flake.lock` still records the default. |
| The override pointing at a **gitignored** directory inside the checkout (relative or absolute path) | **seen.** A `path:` input reads the filesystem, not git. |
| `scripts/nix_git_inputs.py` with a `path` input | unaffected: it only rewrites `github` inputs |

**Also found:** the key is resolved **twice**, in the flake (`rootPub`, embedded in the package) and in `modules/pre-nixos.nix` (`rootKeyCandidate`, used for the login notice). Each has its own `getEnv` and fallback, which is not DRY.

## 1. Design choices (debate)

### D1. Where the settings live
- **Choice: outside git.** Either in a directory of the user's own (any path), or in a gitignored `site/` inside the checkout.
- A file inside the repo that this repo's own flake reads cannot also be untracked (§0). So the repo only supplies an **empty default**.

### D2. The interface: how settings reach the build
- **(a) `lib.mkBootImage { system, format, site }`, for a wrapper flake of the user's own:** pure and explicit, and composable (the user's flake can also pin this repo by commit). It needs a second flake.
- **(b) A `site` input, overridden on the command line:**
  - `nix build .#bootImageSd --override-input site path:./site`
  - Pure, with no second flake, and the same for every image.
  - The command is longer.
- **(c) Environment variables with `--impure`** (today): the result depends on unrecorded state.
- **Choice: (a) and (b), both built on one function.**
  - `packages.<system>.bootImage*` are `mkBootImage` applied to the `site` input, so (b) is (a) with the repo's own input.
  - **(c) stays as a fallback, used only when the site sets nothing.** The VM-test fixtures, `manual_vm_debug.py` and the user's habit all rely on it. If both are set and they conflict, that is an **evaluation error** rather than a silent precedence.
  - Moving the fixtures off (c) is queued, not done here, to keep the change bounded.

### D3. What a site is
- **A directory** containing `pre-nixos-site.nix`, a plain attribute set:
  ```nix
  {
    rootKey = ./root_key.pub;   # path, or null (default)
    autoInstall = true;         # bool (default false)
  }
  ```
- Paths resolve relative to the site directory, so the key sits next to the file.
- **Validated:** an unknown attribute or a wrong type is an evaluation error (`lib.types` checks, done once in the flake). A typo is not silently ignored.
- **Why a file, not one input per setting:** one override covers the key and auto-install together, and future settings (for example a static install IP) need no new input.

### D4. One path from the setting to the image (DRY)
- **Module options:**
  - `services.pre-nixos.rootKey` (`nullOr path`) and `services.pre-nixos.autoInstall` (`bool`);
  - `services.pre-nixos.package`, defaulting to `pkgs.pre-nixos` built **with `cfg.rootKey`**.
- **The module reads only these options.** Its `getEnv` calls move to the flake's fallback (D2c), which is one place.
- **The pre-nixos package becomes a function of `rootKey`** (`makePreNixosPackage { system, rootKey }`). The login notice and the embedded key can then no longer disagree.

### D5. Formats
- **`format = "iso"`:** `x86_64-linux`, the existing ISO modules.
- **`format = "sd"`:** `aarch64-linux`, the stock installer SD modules plus the Pi boot chain (plan items 6 and 8).
- **Any other format/system pair is an evaluation error**, naming the supported pairs.

### D6. Repository changes for the user's question
- `.gitignore` gains **`/site/`**, the conventional place for a checkout-local site. The existing `pre_nixos/root_key*` patterns stay.
- `nix/site-default/pre-nixos-site.nix` (tracked) is the empty default: `{ }`.

**Refinement (implementation, 2026-10-21).** D4 does not add a `package` option, because that would touch every use of `pkgs.pre-nixos` in the module. Instead, `mkBootConfigurationWith { format, settings }` uses one resolved `settings` value both to build the package (`makePreNixosPackage { rootKey }`) and to set `services.pre-nixos.rootKey` and `autoInstall`, so the two cannot disagree. The limit: a third party using `nixosModules.pre-nixos` alone must build the package with the same key.

**Also removed:** the in-repo `pre_nixos/root_key.pub` fallback. Being gitignored, it was invisible to every flake build, pure or impure, so it was dead code (§0).

## 2. Tests

All of these are **flake checks**: pure, run by `nix flake check` (CI tier 1), and never skipped (tests/AGENTS.md). An earlier draft proposed pytest tests that skip without nix, which tests/AGENTS.md forbids.

- **`site-settings`:** uses `tests/fixtures/site-example/`, a tracked fixture site with a throwaway test public key and `autoInstall = true`. It asserts that `mkBootImage`'s configuration:
  - embeds exactly that key in the package;
  - sets the service's `PRE_NIXOS_AUTO_INSTALL=1`;
  - does both for the ISO and for the SD image (configurations evaluated, nothing built).
- **`site-default`:** the repo's own default site gives no key and auto-install off.
- **`site-validation`:** an unknown attribute, a wrong type, and an unsupported format/system pair each fail evaluation (`builtins.tryEval`).
- **`site-env-conflict`:** the key resolution is a pure function `resolveSettings { site; env; }`. It is tested directly with a fake `env`: a conflict throws, and the env fallback applies only when the site sets nothing.
- **VM tests:** unchanged. They still pass the key through the D2c fallback, which exercises it end to end.

## 3. Unknowns
None blocking; §0 covered the Nix mechanics. A follow-up: `--override-input` with a relative `path:` resolves against the current directory. That is documented, and an absolute path always works.
