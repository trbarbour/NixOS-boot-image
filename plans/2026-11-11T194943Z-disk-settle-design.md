# The boot-time plan waits for the disks, and writes only to the disks it planned for (design)

_2026-11-11T19:49:43Z. Task queue item 50._

**Problem (found 2026-11-11, item 48):** `pre-nixos.service` is only `wantedBy = multi-user.target`. A disk that appears after it starts is missing from the boot-time inventory, and an auto-provisioning run would plan without it. Examples: a slow HBA scan finishing after the switch to the real root, or a driver loaded in stage 2. On the user's PC the HBA disk appeared at 67.8 s.

**User decision (2026-11-11):** options 1 and 3.
- (1) Before the inventory, wait until the disk set has been unchanged for a quiet period (about 15 s), with an upper bound (about 2 min). Both are settable on the kernel command line.
- (3) Take the inventory again just before anything is written. If it differs from the plan's, stop (plan-only) and name the change.

## 1. Requirements (traceability)
- **R-D1 (option 1):** at boot, before storage detection and the plan, pre-nixos waits until the set of candidate disks has been unchanged for the quiet period. The quiet period defaults to 15 s (`pre-nixos-disk-quiet=SECONDS`).
  - The wait has an upper bound, 120 s by default (`pre-nixos-disk-wait-max=SECONDS`).
  - `pre-nixos-disk-quiet=0` turns the wait off.
- **R-D2:** if the set is still changing at the bound, the boot run continues, but plan-only: it does not provision or install. The status says why (`DETAIL=disks-unsettled`).
- **R-D3 (option 3):** a plan records the disks it was made from. Before the first write to storage (the cleanup of existing storage, then disko), the inventory is taken again.
  - If the disks differ, nothing is written. The run stops, says which disks were added, removed or changed, and the boot run reports plan-only (`DETAIL=disks-changed`).
  - This holds for the CLI, the boot service and the TUI.
- **R-D4:** a plan with no recorded disks (a plan saved by an older version, or written by hand) is not applied; the user re-plans on this machine.

## 2. Design debates
### D1. Where the wait runs
- (a) Inside `pre-nixos`, before its inventory. But the boot service runs `pre-nixos-detect-storage` first, which reads the same disks to decide whether existing storage forces plan-only. A late disk with data on it would be missed there.
- (b) **Chosen:** a separate command, `pre-nixos-wait-disks`, run first by the service script, before detection. Both detection and the plan then see the settled set. Interactive runs (the TUI, a CLI at a shell) do not wait: by then the boot has long settled, and R-D3 guards them.
- (c) systemd ordering (`systemd-udev-settle.service`). It is deprecated, and it waits for the udev queue to drain, not for a controller's scan to finish. A late disk is not in the queue yet.

### D2. What "the disk set" is
- The candidates `inventory.enumerate_disks` returns (whole, non-removable, non-virtual disks), each identified by `(name, size, serial)`.
  - The name alone misses a disk swapped under the same name.
  - The model and rotational flag are not identity, and the model comes from a VPD page that a slow device can report late.
- R-D1 compares all candidates. R-D3 compares the plan's candidates: the inventory after the protected (running-system) disks are excluded, which is what the plan was made from.
- One pure function, `inventory.disk_identities(disks) -> frozenset[DiskIdentity]`, serves both. `inventory.describe_changes(before, after) -> list[str]` names each added, removed or changed disk.

### D3. The wait loop
- Pure and clock-injected: `settle.wait_for_stable(read, *, quiet, limit, clock, sleep, poll=1.0) -> SettleResult(settled, elapsed, identities, changes)`.
  - The quiet period restarts at every change.
  - The loop ends when the set has been unchanged for `quiet`, or when `limit` has passed since the start.
- Preconditions (asserted): `quiet >= 0`, `limit >= 0`, `poll > 0`.
  - Kernel parameters that do not parse as non-negative integers fall back to the default, with a warning in the journal: a typo must not stop the boot.
  - If `limit < quiet`, the bound wins: a set unchanged for the whole of `limit` but not for `quiet` counts as unsettled. Saying so is clearer than guessing.
- No disks at all is a set like any other: an empty set unchanged for 15 s is settled.

### D4. At the bound (R-D2)
- (a) Continue normally. A disk still appearing could then be missed by an auto-provision, which is the very hazard.
- (b) **Chosen:** continue, plan-only. The user can still apply from the TUI, which re-checks the disks (R-D3).
- (c) Fail the service. That gives no plan and no network announcement, which is worse for the user.
- Exit codes of `pre-nixos-wait-disks`: 0 settled, 2 unsettled at the bound, 1 error. The service script maps 2 to `--plan-only`, `DETAIL=disks-unsettled`; 1 to `--plan-only`, `DETAIL=disk-wait-error`.

### D5. Where the re-check runs (R-D3)
- The first write is not disko: it is the cleanup of existing storage (`_handle_existing_storage` in the CLI, the cleanup prompt in the TUI). So the re-check runs before that, in both front ends, through one function: `inventory.verify_plan_disks(plan, protected) -> list[str]` (the changes; empty when unchanged).
- The plan records the identities under `plan["inventory"]` (a sorted list of `{name, size, serial}`), added where the plan is made: `inventory.record_disks(plan, disks)`.
- On a change:
  - The CLI prints the changes and exits with `EXIT_DISKS_CHANGED = 4`. It records the auto-install status as skipped, with reason `disks-changed`, as R-S3's stop does.
  - The service script maps 4 to plan-only with `DETAIL=disks-changed`.
  - The TUI shows the changes and asks the user to re-plan (`r`); it does not apply.
- A run that only plans (`--plan-only` without a forced cleanup) or a `--dry-run` writes nothing, so it does not check.

### D6. Plans without a record (R-D4)
- (a) Apply them unchecked. A plan made on another machine, or before a disk was swapped, would be applied blind.
- (b) **Chosen:** refuse, naming the reason: "this plan does not record its disks; re-plan on this machine".

## 3. Tests (written first)
- `tests/test_disk_settle.py`, with a fake clock and a scripted disk list:
  - settles after the quiet period, which restarts on each change;
  - unsettled at the bound;
  - quiet 0 returns at once;
  - `limit < quiet`;
  - parsing of the kernel parameters, including bad values, which fall back to the default;
  - the command's exit codes.
- `tests/test_inventory.py` (extended):
  - identities;
  - the change descriptions (added, removed, same name with another serial or size);
  - `record_disks`;
  - `verify_plan_disks`, including a plan without a record.
- CLI:
  - a disk added between plan and write: no cleanup and no apply, exit 4, status `disks-changed`;
  - unchanged: applied as before;
  - `--plan-only` does not check.
- TUI: a changed disk set refuses to apply and says so; nothing is wiped.
- Service script: the flake check gains the new branches (wait exit 2 and 1, pre-nixos exit 4).
- VM test: a disk hot-plugged shortly after boot (QMP `device_add`, about 5 s after the service starts) is in the boot-time plan, and the service waited for it.
