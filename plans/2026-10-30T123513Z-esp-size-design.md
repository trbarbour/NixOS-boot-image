# ESP size: design (R-B3)

_2026-10-30T12:35:13Z. User request._

## 1. Requirement

The user's request (2026-10-30):

> The 1GB EFI partition seems too small (it does not hold many generations, at
> about 200MB / generation). 4GB would be better, provided there is sufficient
> storage. Maybe it should be the greater of 1GB or 3% of the device, up to a
> limit of 4GB. This applies to the installed system, but it should also apply
> to the boot image, at least for AArch64 (where the system may run from the SD
> card if there is no other storage).

Recorded as **R-B3** (reqs §2.3): the installed system's ESP is 3% of its
disk, at least 1 GiB and at most 4 GiB.

## 2. The boot image: no change

The premise for the boot image does not hold, so the boot image is left
unchanged. Checked against the pinned nixpkgs
(`26f4107e47e3ad0ffd0db220469ba83b6f6d96e8`,
`nixos/modules/installer/sd-card/sd-image{,-aarch64}.nix`):

- The SD image has two partitions. The first is the FAT `/boot/firmware`
  (`sdImage.firmwareSize`, 30 MiB by default). It holds only the Pi firmware,
  U-Boot and the device trees (`populateFirmwareCommands`).
- The kernels and initrds of every generation go to `/boot/extlinux` and
  `/boot/nixos` on the **ext4 root** (`populateRootCommands` runs the extlinux
  builder with `-d ./files/boot`). The root grows to fill the card on first boot
  (`sdImage.expandOnBoot`).
- So a system that runs from its SD card can keep as many generations as its
  root filesystem has room for, up to extlinux's `configurationLimit` (20 by
  default). The FAT partition's size does not limit them.

Changing the SD layout would also go against R-P2, which keeps the stock image's
boot chain.

The ISO is read-only media, so it has no generations to keep.

## 3. Design debate

### D1. The size rule

- **(a) Fixed 4 GiB.** Simple. *Against:* on a small disk (for example a 32 GB
  eMMC) it takes 12.5% of the disk.
- **(b) 3% of the disk, clamped to [1 GiB, 4 GiB]** (chosen; the user's
  proposal). Below 33 GiB it stays at today's 1 GiB, and from about 133 GiB it
  is 4 GiB. 4 GiB holds about 20 generations.
- **(c) Size from a generation count and a measured closure.** *Against:* the
  kernel and initrd sizes are not known when the plan is made, and they change
  with every update.

The arithmetic is in integers (`size * 3 // 100`), aligned down to a MiB. The
partition is MiB-aligned like the others, and there is no floating point.

### D2. Which disk's size, when `main` is an array

When `main` is a RAID set, each member gets an ESP (`EFI`, `EFI2`, …).

- **(a) Each disk's own size.** *Against:* the members' ESPs can differ by a
  MiB or so, so they are no longer interchangeable copies of each other.
- **(b) The smallest member's size, for every member** (chosen). The ESPs are
  identical, so the primary can be copied to the others. The data partitions
  differ only as the disks do, and mdadm uses the smallest anyway. The planner
  groups disks within 1% of each other, so the cost is negligible.

### D3. Where the size lives

- **(a) Computed again where the disko layout is made.** *Against:* two places
  compute the same fact, and the disko layout does not know the disk sizes.
- **(b) Recorded on each `efi` partition of the plan (`"size": "1966M"`), and
  the disko layout copies it** (chosen). The plan shows it, and there is one
  source.

An `efi` partition without a size is a programming error: the disko layout
asserts that it has one rather than falling back to a default.

### D4. Small disks

A disk smaller than the 1 GiB floor keeps today's behaviour: the data slice
clamps to zero. Only the floor and the cap are configuration; the user did not
ask for a site setting, so none is added.

## 4. Traceability

| Requirement | Facility | Test |
| --- | --- | --- |
| R-B3 size rule | `pre_nixos/planner.py`: `efi_partition_size`, `EFI_PARTITION_{MIN_SIZE,MAX_SIZE,PERCENT}` | `tests/test_efi_partition_size.py`: examples at the floor, in between and at the cap; bounds, MiB alignment and monotonicity over 0 to 200 GiB; negative size rejected |
| R-B3 equal ESPs on an array (D2) | `plan_storage.record_partitions` | `test_raid_members_get_equal_esps_from_smallest_disk` |
| R-B3 one source for the size (D3) | plan `efi` partition `size`; `_plan_to_disko_devices` | `test_plan_records_esp_size_and_disko_uses_it`, `test_disko_refuses_esp_without_size` |
| R-B3 capacity accounting | `record_partitions` deducts the ESP | `test_esp_is_deducted_from_main_capacity`, `tests/test_plan_storage.py` |
| R-P2 SD image unchanged | none (no change) | existing flake check of the SD image's boot settings |

## 5. Follow-up

`docs/task-queue.md` item 32: the boot loaders' `configurationLimit` does not
follow the ESP size. extlinux's 20 generations overflow a 1 GiB ESP, and
systemd-boot has no limit.

## 6. Verification (2026-10-30, applied on `claude/gallant-dijkstra-n9lqn1` as c13665e)

- **Unit tests:** 441 passed, including the 15 new tests. mypy is clean, `nix flake check` passes, and the SD image evaluates.
- **disko** (`disko --dry-run`) renders the planned sizes as sgdisk arguments: `--new=1:0:+1966M` for a 64 GiB disk, and `+3G` on both members of a RAID-1 pair of 100 GiB SSDs.
- **sgdisk** on a sparse 64 GiB image creates partition 1 at sectors 2048–4028415, exactly 1966 MiB.
- **VM tests:** `tests/vm/test_pre_nixos_vm.py` and `tests/vm/test_raid_provisioning.py` passed 4/4 (17 min 39 s). Their disks are small, so they exercise the 1 GiB floor and RAID provisioning end to end.
- **Not run:** a VM with a disk above 33 GiB. The sizes above the floor are covered by the disko and sgdisk checks instead.
