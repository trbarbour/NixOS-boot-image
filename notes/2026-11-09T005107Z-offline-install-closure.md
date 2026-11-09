# Offline nixos-install: what the installed system needs that the ISO lacks (#340)

_2026-11-09. Task queue item 43; user report from the first BIOS PC (0.26.2)._

## Reproduction
- **VM** (`tests/vm/test_offline_install_closure_vm.py`, run `notes/2026-11-09T003327Z-vm-run`): after provisioning, a dry-run build of the configuration pre-nixos wrote, with every substituter disabled, planned **1751** derivations, including `stage0-posix` and `hex0-seed` (the user's PC: 1907).
  - The first run passed wrongly: the parser missed the header (terminal escapes, `\r\r\n`). That parser is now fixed and unit-tested.
- **Host, isolated:**
  - copied exactly the ISO's closure (`closure-info`, 781 paths, 3.2 GB) into an empty store;
  - instantiated an installed configuration there (the GRUB fixture plus pre-nixos's BIOS loader and network modules, with `nixpkgs.hostPlatform` forced to x86_64: the fixture's hardware file says aarch64);
  - `nix-store -r --dry-run --option substituters ''` listed **1766** derivations, matching the user's failure.

## Analysis
- **H1, rejected:** the installed system uses the same nixpkgs as the ISO. Its `gawk` is `xj3xxr99…-gawk-5.4.1`, the ISO's, in the user's log and here.
- **The dry run over-reports.** It lists every partly-present multi-output derivation. The exact set (walk from the top; build a derivation only when an output a dependant needs is missing) is **1266** derivations.
- **The final `stdenv-linux` (`zifs9cd5…`) is in the ISO** (via `makeBinaryWrapper`). The configuration derivations (`/etc` files, units, initrd parts) can be built with it. The other six `stdenv-linux` derivations are bootstrap stages, reached only by rebuilding packages.
- **What the configuration needs that the ISO lacks:**
  - `info` outputs, for `system-path` (gawk, coreutils, sed, grep, tar, gzip, diffutils, findutils, which, time, nano, mtools, bash-interactive, e2fsprogs), plus `texinfo` and `texinfo-interactive`;
  - packages absent from the ISO: `dhcpcd`, `openresolv`, `logrotate`, `strace`, `fontconfig` (bin), `shared-mime-info`, `desktop-file-utils`, `hicolor-icon-theme`, `sound-theme-freedesktop`, `getconf`;
  - GRUB's installer (`install-grub.pl`): `perl-5.42.3-env` with XML-LibXML, XML-SAX, XML-SAX-Base, XML-NamespaceSupport, File-Copy-Recursive and List-Compare (for any GRUB install, BIOS or EFI);
  - `dbus-1`: configuration-specific, built on the target.
- Each missing package output forces a rebuild from source. That needs build inputs (`dev` outputs, tarballs) the ISO lacks, and ends in the compiler bootstrap.
- **Size of the missing runtime packages:** 52 paths, about 50 MiB unpacked (binary cache NAR sizes); texinfo is 28 MiB of it.

## Correction: the VM test passed twice, wrongly
- **Run 1** (`notes/2026-11-09T003327Z-vm-run`): the parser missed the header behind terminal escapes and `\r\r\n`.
- **Run 2** (`notes/2026-11-09T004548Z-vm-run`): the serial log again shows 1751 derivations including `stage0-posix`, but `BootImageVM.run` (`clean_command_output`) strips every line, and the parser required the two-space indent, so it collected nothing.
- **Fixed:** the parser accepts both forms, and the test now fails if a build list was printed but none was parsed. `test_dry_run_list_from_a_serial_transcript` covers the controller-cleaned form; it fails with the previous parser.
- The host-side isolated-store reproduction above does not depend on this parser.

## Fix: reference installed systems in the image (`modules/pre-nixos/reference-installed.nix`)
- The x86 image's `system.extraDependencies` now holds two reference installed systems (BIOS GRUB with pre-nixos's boot module; UEFI systemd-boot). Each is the generator's loader lines plus pre-nixos's network module plus the package-relevant settings of install.py's managed block.
- It also holds the build tools for the per-machine configuration derivations: `desktop-file-utils`, `findXMLCatalogs`, `getconf`, `libxslt.bin`, `lndir`, `texinfo`. These are build-time inputs, so the references' runtime closures do not carry them.
- **Cost:** the references add 130 paths, 87 MiB unpacked (including their own initrd, `hwdb.bin` and `system-path`, which a real install rebuilds); the tools add 7 paths, 14.3 MiB.
- **Check** (host, isolated store; the ISO's closure plus these). A configuration that differs from the references the way real machines do (managed block, static address, root key, RAID, other kernel modules and file systems):

  | Store | Must build | Toolchain/bootstrap |
  |---|---|---|
  | ISO alone | 1247 | 46 |
  | ISO + references + tools | 63 | 0 |

  The 63 are all that machine's own configuration (`/etc`, fstab, initrd, units, GRUB config, `perl-5.42.3-env` as a buildEnv of modules now present, the root key).
- An install still needs the network (R-I1); this removes the rebuild cascade and most downloads.
