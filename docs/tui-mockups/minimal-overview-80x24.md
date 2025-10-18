# TUI Mock — Minimal Auto-Scaled View (80×24 Terminal)

This sketch shows the renderer after probing an 80×24 terminal and falling back to the **minimal** profile. Non-focused branches collapse into counts and abbreviated labels so the canvas fits within the constrained viewport.

```
IP: 203.0.113.17 (lan)  View: Planned (minimal)  Focus: Disk nvme0n1  Legend: ■ SSD  ● HDD  ☐ EFI  ≡ RAID

▶ Disk nvme0n1  ⟟  ESP+main (2 parts)   ⇒  md0 ≡ R1 (SSD)   ⇒  VG main (3 LVs)
  Disk nvme1n1  ⟟  member only
  Disk nvme2n1  ⟟  spare bucket (main_1)

  HDD bucket A (6 disks)   ⇒  md2 ≡ R6   ⇒  VG large (2 LVs)
  HDD bucket B (2 disks)   ⇒  swap mirror waiting (blocked)
```

* The focus row expands just enough detail to confirm the EFI + primary partition while still respecting the width budget.
* Rows that would overflow (`md0`, `VG main`, LV list) compress to single-line summaries with counts (`(3 LVs)`).
* Pending blockers (no swap mirror yet) surface as parenthetical annotations instead of extra columns.
