# Drop the legacy build-time environment fallback (design)

_2026-11-23T02:01:04Z. Task queue item 57; user decision on item 56 (2026-11-16): "drop the fallback"._

**Background.** Site-settings design D2c (`plans/2026-10-21T135252Z-site-settings-pure-images-design.md`) kept `PRE_NIXOS_ROOT_KEY` and `PRE_NIXOS_AUTO_INSTALL`, read with `builtins.getEnv` under `--impure`, as a fallback for settings a site leaves unset. Item 19 moved the last users in this repository (the VM fixtures and two debug scripts) to sites, so nothing here needed it.

**Scope.** Only the *build-time* variables. `PRE_NIXOS_AUTO_INSTALL` is also the name of the boot service's *run-time* environment variable, which `modules/pre-nixos.nix` sets from the site's `autoInstall` and `pre_nixos.py` / `tui.py` read. That one stays.

## 1. Requirement
- **R-A3** (automated-pre-nixos-reqs.md §2.7): the image's build-time settings (root key, auto-install, primary console, hashed root password) come from a site alone. An attempt to set them through the former environment variables is an evaluation error that names the replacing site setting; it is never silently ignored.

## 2. Facts (verified by experiment, 2026-11-23T01:48Z)
- In a **pure** flake evaluation, `builtins.getEnv` returns `""`. With `PRE_NIXOS_ROOT_KEY=/x` exported, a toy flake gives `""` without `--impure` and `/x` with it (Nix 2.34.6).
- So the variables can only ever reach an `--impure` evaluation. Nothing in the flake needs `--impure` otherwise (no `currentSystem`, `currentTime` or other `getEnv`).

## 3. Design debate
### What an exported variable does now
- **(A) Silently ignored.** It is simplest, but an old habit (`export PRE_NIXOS_ROOT_KEY=…; nix build --impure`) would then build an image without the key it meant to embed. That only shows at the machine, as an SSH login that fails. Rejected.
- **(B) Chosen: an evaluation error** naming the variable(s) and the site setting that replaces each (`rootKey = ./root_key.pub;`, `autoInstall = true; or false;`). The error is caught at build time, with the fix in the message. Pure builds, the norm, are unaffected because they read `""`.
- **(C) A warning** (`lib.warn`). It is easily lost in `nix build` output, and the image is still wrong. Rejected.

### Where the guard sits
- `nix/site.nix` `refuseLegacyEnv env` is a pure function, so a flake check can test it with any `env`. `flake.nix` reads the two variables (`legacyEnv`) and asserts the guard in `settingsFor`. Every image goes through `settingsFor`: the flake's own `packages`, `nixosConfigurations` and `lib.mkBootImage`.
- `resolveSettings` now takes the site alone (`resolveSettings site`). `parseEnvBool` is gone with its only user.

### The harness
- `tests/vm/site_build.build_environment()` only cleared the two variables. A pure build cannot see them (§2), so it is gone, and the fixtures and scripts inherit the environment unchanged.
- `tests/vm/test_disko_offline_closure.py` still built with `--impure`, a leftover from the fallback. With a stale export it would now stop. It now builds purely. A test keeps `--impure` out of every string literal in `scripts/` and `tests/vm/` (docstrings aside).

## 4. Tests
- Flake check `site-legacy-env-refused` (replaces `site-env-conflict`). It checks that:
  - the guard fails for either variable, set to any value;
  - it passes for an empty environment;
  - `resolveSettings` gives `noSettings` for an empty site and the fixture's key and auto-install for the fixture site.
- Written first. It and the three other site checks failed to evaluate ("attribute 'refuseLegacyEnv' missing"; "resolveSettings called without required argument 'site'"), then passed.
- `tests/test_scripts_use_sites.py::test_no_harness_or_script_evaluates_impurely`: failed first on `tests/vm/test_disko_offline_closure.py:39`, then passed.
- End to end, `nix eval .#packages.x86_64-linux.bootImage.name`:
  - with `--impure` and `PRE_NIXOS_ROOT_KEY` set: the new error;
  - with both variables set: one error naming both;
  - with `--impure` and nothing set: the image name;
  - pure, with the variable exported: the image name.
