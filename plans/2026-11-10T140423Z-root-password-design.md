# A hashed root password for the installed system (design)

_2026-11-10T14:04:23Z. Task queue item 45._

**User report (2026-11-09):** an installed system was unreachable over the network (#342). The serial console could not help either: root has no password on the installed system, so nobody can log in there.

**User decision (2026-11-09):** "Yes, add item 45 for the hashed password." Agreed scope:
- an optional site setting `rootHashedPassword` (a crypt hash, e.g. from `mkpasswd -m yescrypt`), kept in the site file like `rootKey` and never in the repository;
- pre-nixos writes it as `users.users.root.hashedPassword` on the installed system;
- unset by default;
- the installer itself keeps its empty console password.

## 1. Requirements

- **reqs §2.7:** "Root login must be possible over the serial console (if functional)." On the installed system this needs a password.
- **R-A1 (new, §2.7):** a site may give a hashed root password. The installed system's root account then has that password, for console logins. SSH stays key-only (§2.7, first bullet). Without the setting, nothing changes.
- **R-A2 (new, §2.7):** the setting must be a crypt hash. A plain password, or anything that would lock root out, is a build-time error.

## 2. Facts

| # | Fact | Evidence |
|---|---|---|
| F1 | Site settings are typed and validated in `nix/site.nix` at evaluation time. One resolved value builds the package and sets the module options (design D4 of the site-settings plan). | `nix/site.nix`; `flake.nix` `mkPreInstaller`. |
| F2 | The root key reaches pre-nixos as a file embedded in the package (`pre_nixos/root_key.pub`), and the managed block writes it as `users.users.root.openssh.authorizedKeys.keys`. | `flake.nix` `makePreNixosPackage`; `install.py` (managed block). |
| F3 | With `users.mutableUsers = true` (the default, and what the installed system uses), NixOS applies `hashedPassword` only when it **creates** the `/etc/shadow` entry. An existing entry keeps its password. | nixpkgs `nixos/modules/config/update-users-groups.pl`: the loop over the existing `/etc/shadow` replaces the password only `if !$spec->{mutableUsers}`; new entries take `hashedPassword`. |
| F4 | Reinstalling over an earlier attempt's root file system happens: the user's PC did it (#342), and pre-nixos's managed block exists for that reason. An earlier attempt leaves `/etc/shadow` with root locked (`!`). | #342; F3. |
| F5 | NixOS warns, but does not fail, when a hash does not look like Modular Crypt Format (MCF). It accepts the schemes `pkgs.libxcrypt.enabledCryptSchemeIds`: `y gy sm3y 7 2b 2y 2a 6` on the pinned nixpkgs. | nixpkgs `users-groups.nix` (the `mcf` pattern and its warning). Evaluated 2026-11-10. |
| F6 | A Nix string may hold `$` freely; only `${` interpolates. The crypt alphabet (`./0-9A-Za-z`, `$`, `=`, `,`, `+`, `-`) has no `{`. | `nix eval --expr '"$y$j9T$abc$def"'` gives `"$y$j9T$abc$def"` (2026-11-10). |
| F7 | `nixos-install --no-root-passwd` does not touch root's password. | `install.py` calls it so. |
| F8 | The NixOS store is world-readable, and NixOS puts `hashedPassword` in the store (the users spec). So does the image (the package). | NixOS's documented behaviour; the image is a file anyone holding it can read. |

## 3. Design debate

### D1. The type of the setting
- **(a) A string, the hash itself** (`rootHashedPassword = "$y$j9T$…";`). It has the same name and meaning as NixOS's `hashedPassword`. **Chosen.**
- **(b) A path to a file holding the hash** (like `rootKey`). That would be one more file in the site for one line, and it gives no secrecy (F8).
- **(c) A plain password, hashed at build time.** Rejected: the plain password would sit in the site file, and hashing in a derivation puts it in the store as well.

### D2. Validation (R-A2)
- **(a) In `nix/site.nix`, at evaluation:** the value must match NixOS's own MCF pattern (F5), with the scheme ids listed in `site.nix`. A plain password, an empty string, `!`, or `*` is an error naming the setting. **Chosen:** bugs are found when the image is built, not on the machine.
  - `site.nix` takes only `lib`, so it cannot read `pkgs.libxcrypt`. A flake check compares the list in `site.nix` with `pkgs.libxcrypt.enabledCryptSchemeIds`, so a nixpkgs update that changes the schemes fails the check instead of drifting.
- **(b) Rely on NixOS's warning:** only a warning, and it comes when `nixos-install` runs on the target, too late.
- **Runtime precondition (Python):** pre-nixos re-checks the embedded hash before writing it, with the same pattern: one line, MCF, a known scheme. A failure means a broken image (an invariant violated); the install stops with `REASON=root-password-invalid`.

### D3. How the hash reaches pre-nixos
- **(a) Embedded in the package, like the key** (`pre_nixos/root_hashed_password`, from `makePreNixosPackage`). **Chosen.** It follows F2's existing path, and one resolved value still builds both the package and the module (F1).
- **(b) An environment variable from the module.** It would need plumbing to the service, the login shells and the TUI, and it is not visible to a `pre-nixos` run outside them.

### D4. Where the installed system gets it, and reinstalls (F3, F4)
- **(a) Only `users.users.root.hashedPassword` in the managed block.** This works on a fresh disk. On a reinstall over an earlier attempt, root keeps `!` (F3), so the setting silently does nothing: the #342 pattern again.
- **(b) Also set `users.mutableUsers = false`.** Then NixOS always applies the hash, but it would also take `passwd` and `useradd` away from the user on the installed system. Too much.
- **(c) The managed block's `hashedPassword`, plus pre-nixos sets root's password field in an existing `/mnt/etc/shadow` to the same hash before `nixos-install`.** **Chosen.** The end state is the same on a fresh disk and on a reinstall. The configuration still states the hash, and the user can change it later with `passwd` (mutable users).
  - Only root's line changes. Other fields and lines are kept. The file is replaced atomically, with its mode and owner kept.
  - With no setting, pre-nixos leaves `/mnt/etc/shadow` alone.
  - With no `/mnt/etc/shadow`, nothing is edited. NixOS creates the entry with the hash (F3).
  - With a shadow file that has no root line, nothing is edited either. NixOS adds root with the hash.

### D5. The installer itself
- Keeps its empty console password (the stock installer's `initialHashedPassword = ""`). Agreed; the setting affects only the installed system.

### D6. Exposure (F8)
- The hash is in the image and in both stores. The README says so and asks for a strong password and a slow scheme (yescrypt, `mkpasswd -m yescrypt`). That is the same exposure as any NixOS `hashedPassword`.

## 4. Tests (traceability)

| Requirement | Test |
|---|---|
| R-A2 at build | flake check `site-settings`: plain text, `!`, `""`, `$1$` (MD5, not enabled), a `:` are rejected; a yescrypt hash is accepted. The new check `crypt-schemes` compares the scheme list with libxcrypt's. |
| R-A1, D3 | flake check `site-settings`: the hash reaches the package (`passthru.rootHashedPassword`, the file's content). |
| R-A1, D4 | `tests/test_root_password.py`: the pure shadow rewrite (root's field only, other lines kept, no root line, a malformed line); loading and validating the embedded file; the managed block has `users.users.root.hashedPassword` only when set; `auto_install` rewrites an existing `/mnt/etc/shadow`, and stops with `root-password-invalid` on a bad hash. |
| R-A1 end to end | `tests/vm/test_installed_system_vm.py`: an image built with the test hash; the installed system's `/etc/shadow` has root's hash, checked over SSH. A planted earlier `/etc/shadow` (root `!`) covers D4. |
