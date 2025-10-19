# Embedded SSH key verification (task queue item 1)

- **Objective:** Confirm that the freshly built boot ISO embeds the generated root SSH public key (`pre_nixos/root_key.pub`).
- **Context:** Follow-up for task queue item 1 from `docs/task-queue.md`.

## Actions

1. Generated a disposable ED25519 key pair for the ISO build.

   ```bash
   ssh-keygen -t ed25519 -f tmp/queue-root -N '' -C 'queue-task'
   ```

   - Fingerprint: `SHA256:DUq8gJ+MNyxWGS6BY8bciCHWP/fFDimtAvkdp/DuwNM`.

2. Rebuilt the boot image with the public key injected via `PRE_NIXOS_ROOT_KEY` using the dev-shell workflow.

   ```bash
   PRE_NIXOS_ROOT_KEY=$PWD/tmp/queue-root.pub \
     nix develop .#bootImageTest -c \
     nix build .#bootImage --impure --no-link --print-out-paths
   ```

   - Resulting store path: `/nix/store/ba9hvgndqa3c4kswri6cpwkw4rn1d0fg-nixos-24.05.20241230.b134951-x86_64-linux.iso`.

3. Extracted `nix-store.squashfs` from the ISO and listed the packaged key.

   ```bash
   nix shell nixpkgs#xorriso -c \
     xorriso -osirrox on \
     -indev "$ISO_FILE" \
     -extract /nix-store.squashfs tmp/iso-extract/nix-store.squashfs

   nix shell nixpkgs#squashfsTools -c \
     sh -c 'unsquashfs -ll tmp/iso-extract/nix-store.squashfs | grep -n "root_key.pub"'
   ```

   - Located the key at `…/4gcw7c6j07w2z9d27kq9kmswi8j0h975-pre-nixos-0.1.0/lib/python3.11/site-packages/pre_nixos/root_key.pub` inside the SquashFS image.

4. Extracted the packaged key and compared it with the generated public key.

   ```bash
   nix shell nixpkgs#squashfsTools -c \
     unsquashfs -d tmp/iso-extract/squashfs \
       tmp/iso-extract/nix-store.squashfs \
       4gcw7c6j07w2z9d27kq9kmswi8j0h975-pre-nixos-0.1.0/lib/python3.11/site-packages/pre_nixos/root_key.pub

   cmp -s tmp/queue-root.pub \
     tmp/iso-extract/squashfs/4gcw7c6j07w2z9d27kq9kmswi8j0h975-pre-nixos-0.1.0/lib/python3.11/site-packages/pre_nixos/root_key.pub
   ```

   - `cmp` reported `Keys match`, confirming the embedded key is identical to the generated key.

## Outcome

- Verified that the ISO produced by the dev-shell workflow embeds the provided root public key.
- Task queue item 1 is complete; the key is present under the expected `pre_nixos` package path inside the ISO SquashFS payload.
- Preserve `tmp/queue-root.pub` for subsequent queue items that depend on the same fingerprint.
