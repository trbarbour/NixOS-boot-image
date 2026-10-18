# USB-stick boot spike for #306 — 2026-10-18

Task: "Spike the USB-disk VM test for #306" (user request). Fault ticket: trbarbour/NixOS-boot-image#309. Requirement:
`automated-pre-nixos-reqs.md` §2.3 (the boot medium is never planned, wiped or
provisioned, and does not count as existing storage).

Evidence in `notes/2026-10-18T190817Z-usb-stick-spike/`: `spike.py` (the
script), `run1.log`, `run2.log`, `run2-serial.log`.

## Unknowns and how each was resolved

| # | Unknown | Result |
|---|---------|--------|
| 1 | Does SeaBIOS boot the hybrid ISO from a QEMU USB stick? | Yes: `-device qemu-xhci -device usb-storage,removable=off,bootindex=0` with a raw copy of the ISO. Login after 191 s (run1) and 205 s (run2), TCG. |
| 2 | Does the guest see it the way a real thumb drive with RM=0 looks? | Yes: `sda RM=0 TRAN=usb 1.3G`, `sda1` on `/iso` (iso9660), `/sys/block/sda/removable` = 0. |
| 3 | Is the stick modified? | No: SHA-256 is the same before and after (run1, run2). |
| 4 | Is the empty target auto-provisioned? | **No, this is a bug.** `storage-status`: `STATE=plan-only DETAIL=existing-storage`; `vda` left empty. |

## Runs

- run1, 2026-10-18 17:34:40Z to 17:40:14Z. ISO
  `/nix/store/51b98157…-nixos-minimal-25.05.20251022.c8aa8cc-x86_64-linux.iso`
  (0.10.6, built at `69c03df`). Result: the observations above.
- run2, started at about 17:42:25Z. Same ISO, with diagnostics run in the
  guest after pre-nixos finished:

  ```
  pre-nixos-detect-storage (PRE_NIXOS_LOG_EVENTS=1):
    resolve_boot_disk: boot_disk "/dev/dev/sda"
      probe /iso -> /dev/sda1, parent "/dev/sda", resolved "/dev/dev/sda"
    device_filtered /dev/fd0 (ignored_prefix, removable_media)
    device_detected /dev/sda reasons [partitions, signatures]
    device_filtered /dev/vda (no_signatures)
    detect_rc=0   (0 = existing storage -> service runs --plan-only)
  pre-nixos --plan-only:
    resolve_protected_disks: protected ["/dev/dev/sda", "/dev/sda"]
  ```

## Root cause (proven by run2's events)

Two faults, and both were needed to produce the symptom:

1. **B1. The boot disk resolves to `/dev/dev/sda`.**
   `_resolve_boot_disk_with_probes` ran `lsblk -npo PKNAME`. With `-p`, that
   prints a full path (`/dev/sda`), and the code prefixed `/dev/` again. Every
   unit-test fake returned a bare `sda`, which the real tool never prints, so
   the tests passed while the code was wrong. On a CD-ROM boot (`sr0`) the
   wrong value went unnoticed, because `/dev/sr*` is skipped by prefix.
2. **B2. The boot-time gate ignores the protected set.**
   `pre-nixos-detect-storage` (`storage_detection.main`), which the service
   uses to decide between auto-apply and plan-only, excluded only that boot
   disk. It never used the protected set from #308. So the stick's ISO
   partitions counted as existing storage.

`pre-nixos` itself kept the stick safe: its protected set still contained
`/dev/sda`, found through the `/iso` mount (#308). That is why the stick was
unchanged.

## Fix (0.10.8)

- `_parent_disk()` uses the `lsblk -p` output as it is, and raises if the
  output is not a path (fail safe: the gate then reports a detection error
  and the run is plan-only).
- `detection_exit_status(env)` is the gate. It is based on
  `_detect_existing_storage`, which applies the protected set.
- The test fakes now print what the real `lsblk -p` prints.
- New regression tests:
  - `tests/test_protected_disks.py::test_boot_disk_is_not_doubly_prefixed`
  - `tests/test_protected_disks.py::test_boot_time_gate_ignores_the_boot_stick`
  - three existing `tests/test_storage_detection.py` tests now fail on the old
    code.
- Permanent VM test `tests/vm/test_usb_stick_boot.py`, using the fixture
  `boot_image_vm_from_usb_stick` and the module `tests/vm/boot_medium.py`.

## Process notes

- run2's first attempt failed at once (`ModuleNotFoundError: pexpect`) because
  it used the system `python3`. The spike must run with `.venv/bin/python`.
- The filename timestamp of this note comes from `date -u`. An earlier draft
  reference used an invented one, which was corrected before commit.
