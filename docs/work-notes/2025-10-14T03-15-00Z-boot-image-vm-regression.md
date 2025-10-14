# Boot image VM regression follow-up (queue item 1)

**Timestamp:** 2025-10-14T03:15:00Z

## Summary

- Began executing task queue item 1 by rebuilding the boot ISO with the updated `pre_nixos.apply` command path.
- Kicked off `nix build .#bootImage`; the build pulled ~2.1 GiB of substitutes before entering the `mksquashfs` stage. After letting the compression step run for a little over six minutes it still had not progressed, so I interrupted the build to avoid tying up the session; the ISO artefact has not been produced yet.
- Could not proceed to the VM regression because the ISO build has not finished yet. Will resume once the squashfs generation completes and the derivation materialises an image.

## Command log

```console
$ nix build .#bootImage
```

Key excerpts:

- Substitution phase fetching cached dependencies and building the system closure.【6c3e8e†L1-L58】【96f315†L1-L114】
- Long-running `mksquashfs` compression step executing under the Nix builder account; still active after ~6 minutes when the build was interrupted.【c1ba30†L1-L3】【240503†L1-L4】【2c7e19†L1-L2】

## Next steps

1. Boot the freshly built ISO via `pytest tests/test_boot_image_vm.py -vv` (or the debug variant) and capture harness/serial logs for queue item 1.
2. Update the task queue with the VM regression outcome and archive new artefacts alongside this note.

---

**Update:** 2025-10-14T03:28:00Z

- Re-ran `nix build .#bootImage` and let the derivation finish; the build completed successfully after populating the ISO squashfs and writing the hybrid image.【6d3f71†L1-L2】【9d0223†L1-L4】【481be9†L1-L4】
- Confirmed the `result` symlink now points at `/nix/store/1y1dzyvl2y7kwyjv4ck4jsaq1s3lx1x7-nixos-24.05.20241230.b134951-x86_64-linux.iso` for use in subsequent VM runs.【8462bc†L1-L2】
- Executed the full `pytest` suite to baseline the codebase before the VM regression; 80 tests passed and 2 marked skips remained (the BootImageVM tests are still awaiting the rebuilt ISO).【21f190†L1-L17】【e43927†L1-L10】

### Command log

```console
$ nix build .#bootImage
$ pytest
```

Key excerpts:

- Substitution and evaluation stages fetching required derivations before the ISO build proceeded.【9bdb8b†L1-L8】【d4eaa4†L1-L6】
- Final ISO assembly showing `mksquashfs` execution and xorriso writing the hybrid image payload.【9d0223†L1-L4】【481be9†L1-L4】
- Pytest summary confirming the core suite passed with only the pre-existing BootImageVM skips.【21f190†L1-L17】【e43927†L1-L10】
