# TUI Mock — Existing vs. Planned Toggle with Mismatch Signals

The following pair of frames demonstrates how the UI reuses the same focus anchor (`LV data`) while switching between the live inventory and the computed plan. Both fits use the **compact** profile on a 100×28 terminal.

## Frame A — Existing layout (View: Existing)
```
IP: 192.0.2.45 (lan)  View: Existing (compact)  Focus: LV data         Legend: ■ SSD  ● HDD  ☐ EFI  ≡ RAID  ░ dim=not in plan

Disk nvme0n1  ⟟ ─[☐ EFI]─[■ nvme0n1p2]──────────┐
                                              ├── md0 ≡ RAID1 (SSD) ── VG main ── slash 35G
Disk nvme1n1  ⟟ ───────────────[■ nvme1n1p1]────┘                         └─ nix 90G (fragmented)

Disk sda      ◎ ─[● sda1 data]──────────────┐
Disk sdb      ◎ ─[● sdb1 data]──────────────┴── md2 ≡ RAID5 (HDD) ── VG large ── ▶ data 4T (ext4, 68% used)
                                                                       ░ └─ oldlogs 500G (orphan)
```

## Frame B — Planned layout (View: Planned)
```
IP: 192.0.2.45 (lan)  View: Planned (compact)   Focus: LV data         Legend: ■ SSD  ● HDD  ☐ EFI  ≡ RAID  ✱ mismatch

Disk nvme0n1  ⟟ ─[☐ EFI]─[■ nvme0n1p2]──────────┐
                                              ├── md0 ≡ RAID1 (SSD) ── VG main ── slash 40G (ext4)
Disk nvme1n1  ⟟ ───────────────[■ nvme1n1p1]────┘                         └─ nix 120G (ext4, dense)

Disk sda      ◎ ─[● sda1 data]──────────────┐
Disk sdb      ◎ ─[● sdb1 data]──────────────┴── md2 ≡ RAID6 (HDD) ── VG large ── ▶ data 3T (ext4)
                                                                       └─ backups 1T (ext4) ✱ ← level differs (R5→R6)
```

* Dimming (`░`) in the existing view marks components the plan intends to remove.
* Planned-only or changed resources render a right-column badge with an arrow summarising the drift cause.
* Because the focus stays on `LV data`, operators can immediately compare sizes and RAID levels without re-navigating.
