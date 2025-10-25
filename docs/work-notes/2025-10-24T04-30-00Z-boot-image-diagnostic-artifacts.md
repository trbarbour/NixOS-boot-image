# BootImageVM diagnostic artifact exports (task queue item 1)

- **Objective:** Expand the BootImageVM diagnostics so timeout handlers leave behind
  structured artefacts that can be harvested by automated and manual tools.
- **Changes:**
  - Extended `write_boot_image_metadata` to create a dedicated `diagnostics`
    directory beside the harness log and record the path inside
    `metadata.json` for downstream consumers.【F:tests/test_boot_image_vm.py†L249-L295】
  - BootImageVM now provisions the diagnostics directory on startup, exposes a
    helper for writing timestamped log files, and includes the resulting paths
    in raised assertion details.【F:tests/test_boot_image_vm.py†L309-L435】
  - The storage-status, IPv4, and unit inactivity waiters persist their
    `journalctl`/`systemctl` captures to diagnostic artefacts while still
    embedding the text in the harness log and assertion message.【F:tests/test_boot_image_vm.py†L715-L833】
  - `collect_sshd_pre_nixos_debug.py` copies the generated diagnostics directory
    alongside the existing harness, serial, and metadata exports so manual
    archives retain the same evidence.【F:scripts/collect_sshd_pre_nixos_debug.py†L279-L312】
- **Result:** BootImageVM failure reports now reference durable log files for the
  captured journals and unit status outputs, simplifying offline analysis and
  ensuring manual exports retain the same provenance metadata as automated runs.
- **Verification:** `nix develop .#bootImageTest -c pytest tests/test_boot_image_vm.py -vv`
  (16m54s).【a34494†L1-L3】
