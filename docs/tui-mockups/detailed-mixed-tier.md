# TUI Mock — Detailed Planned View (Mixed SSD + HDD Tiers)

This mock illustrates the **detailed** density profile on an 110×34 terminal. All columns are fully expanded and the focus cursor rests on the `VG large` row so proportional zooming highlights that subtree without collapsing sibling content.

```
IP: 198.51.100.42 (lan)    View: Planned (detailed)           Focus: VG large          Legend: ■ SSD  ● HDD  ☐ EFI  ≡ RAID  ✱ mismatch

Disk nvme0n1  ⟟ ─[☐ EFI]─[■ nvme0n1p2]─────────────┐
                                                ├── md0 ≡ RAID1 (SSD) ── VG main ── slash 40G (ext4)
Disk nvme1n1  ⟟ ───────────────[■ nvme1n1p1]───────┘                         └─ nix 120G (ext4, dense)
                                                                             └─ var 30G (ext4)
Disk nvme2n1  ⟟ ───────────────[■ (unused)]             (spare SSD bucket → VG main_1, unmounted)

Disk sda      ◎ ─[● sda1 swap-mirror]──────┐
                                          ├── md1 ≡ RAID1 (HDD mirror) ── VG swap ── swap 64G (mkswap)
Disk sdb      ◎ ─[● sdb1 swap-mirror]──────┘
             ◎ ─[● sdb2 data]──────────────┐
Disk sdc      ◎ ─[● sdc1 data]─────────────┴── md2 ≡ RAID6 (HDD) ── ▶ VG large ── data 6T (ext4)
Disk sdd      ◎ ─[● sdd1 data]──────────────┘                         └─ backups 2T (ext4) ✱ ← missing on disk
Disk sde      ◎ ─[● sde1 data]───────────────┐
Disk sdf      ◎ ─[● sdf1 data]───────────────┘
```

* **Focus indicator (`▶`)** forces the `VG large` branch to stay expanded even if the renderer later chooses the compact profile for siblings.
* **Mismatch badge (`✱ ← missing on disk`)** demonstrates how planned-only LVs are called out without relying on vertical separators.
* SSD spares show as annotations so operators know why devices are idle yet still part of the plan.
