# VM run ledger repair (2026-10-19T133558Z)

PR trbarbour/NixOS-boot-image#315 (Codex review) found corrupt JSONL in `notes/vm-run-ledger.jsonl`.

- **Cause (proven):** the buffered append hit ENOSPC part-way. The harness logs of runs `2026-10-19T011942Z` (01:31:46Z) and `2026-10-19T055002Z` (06:03:22Z) show `OSError(28, 'No space left on device')` together with "Failed to append VM run entry to the ledger". The next run's entry was then appended onto the partial line.
- **Fix:** `tests/vm/metadata._append_line` writes the whole line or truncates the file back to its length before the write. Test: `tests/test_vm_run_ledger.py`.
- **Repair:** the incomplete prefixes were removed, and the complete entry that followed each one was kept. Those two runs have no ledger entry; their logs are archived in their `notes/*-vm-run/` directories.

Dropped prefixes (original line number: text):

- 42: `{"harness_log": "/home/user/NixOS-boot-image/notes/2026-10-19T011942Z-vm-run/logs/harness.log", "metadata": "/home/user/NixOS-boot-image/notes/2026-10-19T011942Z-vm-run/logs/metadata.json", "outcome": "failed", "pytest_args": ["-m", "vm", "-v", "tests/vm"], "qemu": {"command": ["/usr/bin/qemu-system-x86_64", "-m", "2048", "-smp", "2", "-display", "none", "-no-reboot", "-serial", "stdio", "-boot", "d", "-cdrom", "/nix/store/gv743s42pjmb64cmcy38mmgl4n7jqk6m-nixos-minimal-26.05.20261015.26f4107-x86_64-linux.iso/iso/nixos-minimal-26.05.20261015.26f4107-x86_64-linux.iso", "-drive", "file=/tmp/pytest-of-root/pytest-109/boot-image-disk-primary0/disk.img,if=virtio,format=raw", "-qmp", "unix:/tmp/qmp-6a0oezc2/qmp.sock,server=on,wait=off", "-device", "virtio-rng-pci", "-netdev", "user,id=net0,hostfwd=tcp:127.0.0.1:54421-:22", "-device", "virtio-net-pci,netdev=net0"], "version": "QEMU emulator version 8.2.2 (Debian 1:8.2.2+ds-0ubuntu1.18)"}, "serial_log": "/home/user/NixOS-boot-image/notes/2026-10-19T011942Z-vm-run/logs/serial.log", "session_ceiling_exceeded": false, "ssh": {"host": "127.0.0.1", "port": 54421}, "timeouts": {"login_seconds": 300, "spawn_seconds": 900}, "timestamp": "2026-10-19T01:31:46.117509+00:00", "timings": {"boot_to_login_seconds": 133.225, "boot_to_ssh_seconds": 238.424, "build_seconds": 2`
- 47: `{"harness_log": "`
