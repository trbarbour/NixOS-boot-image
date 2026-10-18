"""Minimal QEMU Machine Protocol (QMP) client for the VM harness.

QMP is QEMU's JSON control protocol: after connecting to the socket given by
``-qmp unix:<path>,server=on,wait=off`` the client reads a greeting, sends
``qmp_capabilities`` and may then issue commands.  Each command yields one
``{"return": ...}`` or ``{"error": ...}`` reply; asynchronous ``{"event": ...}``
messages may arrive in between and are skipped.

Used to hot-plug disks after the boot-time ``pre-nixos`` run has finished, so
that run cannot provision (or tear down) disks a scenario wants to control.
"""
from __future__ import annotations

import json
import socket
import tempfile
from pathlib import Path
from typing import Any, BinaryIO, Dict, Optional

# sockaddr_un.sun_path is 108 bytes on Linux, including the terminating NUL.
UNIX_SOCKET_PATH_MAX = 107


class QmpError(RuntimeError):
    """Raised when QEMU rejects a command or the protocol is violated."""


def allocate_qmp_socket_path() -> Path:
    """Return a fresh, short socket path (log directories can exceed the limit)."""

    path = Path(tempfile.mkdtemp(prefix="qmp-")) / "qmp.sock"
    assert len(str(path)) <= UNIX_SOCKET_PATH_MAX, path
    return path


class QmpClient:
    """Blocking QMP client; use as a context manager."""

    def __init__(self, socket_path: Path, *, timeout: float = 30.0) -> None:
        if len(str(socket_path)) > UNIX_SOCKET_PATH_MAX:
            raise QmpError(
                f"QMP socket path is {len(str(socket_path))} bytes; the limit is "
                f"{UNIX_SOCKET_PATH_MAX}: {socket_path}"
            )
        self._socket_path = socket_path
        self._timeout = timeout
        self._sock: Optional[socket.socket] = None
        self._reader: Optional[BinaryIO] = None

    def __enter__(self) -> "QmpClient":
        self.connect()
        return self

    def __exit__(self, *exc_info: object) -> None:
        self.close()

    def connect(self) -> Dict[str, Any]:
        """Connect, read the greeting and negotiate capabilities."""

        sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        sock.settimeout(self._timeout)
        try:
            sock.connect(str(self._socket_path))
        except OSError as exc:
            sock.close()
            raise QmpError(f"cannot connect to QMP socket {self._socket_path}: {exc}") from exc
        self._sock = sock
        self._reader = sock.makefile("rb")
        greeting = self._read_message()
        if "QMP" not in greeting:
            raise QmpError(f"expected QMP greeting, got {greeting!r}")
        self.execute("qmp_capabilities")
        return greeting

    def close(self) -> None:
        if self._reader is not None:
            self._reader.close()
            self._reader = None
        if self._sock is not None:
            self._sock.close()
            self._sock = None

    def execute(self, command: str, arguments: Optional[Dict[str, Any]] = None) -> Any:
        """Run ``command`` and return its ``return`` value; raise on ``error``."""

        if self._sock is None:
            raise QmpError("QMP client is not connected")
        message: Dict[str, Any] = {"execute": command}
        if arguments is not None:
            message["arguments"] = arguments
        self._sock.sendall(json.dumps(message).encode("utf-8") + b"\n")
        while True:
            reply = self._read_message()
            if "return" in reply:
                return reply["return"]
            if "error" in reply:
                error = reply["error"]
                raise QmpError(
                    f"QMP {command} failed: {error.get('class')}: {error.get('desc')}"
                )
            if "event" not in reply:
                raise QmpError(f"unexpected QMP message: {reply!r}")

    def _read_message(self) -> Dict[str, Any]:
        assert self._reader is not None
        try:
            line = self._reader.readline()
        except OSError as exc:
            raise QmpError(f"QMP read failed: {exc}") from exc
        if not line:
            raise QmpError("QMP connection closed by QEMU")
        try:
            message = json.loads(line)
        except json.JSONDecodeError as exc:
            raise QmpError(f"invalid QMP JSON {line!r}: {exc}") from exc
        if not isinstance(message, dict):
            raise QmpError(f"QMP message is not an object: {message!r}")
        return message


def hotplug_virtio_disk(
    client: QmpClient, *, image: Path, node_name: str, serial: str
) -> None:
    """Attach raw ``image`` as a virtio-blk PCI disk with the given serial."""

    client.execute(
        "blockdev-add",
        {
            "driver": "raw",
            "node-name": node_name,
            "file": {"driver": "file", "filename": str(image)},
        },
    )
    client.execute(
        "device_add",
        {
            "driver": "virtio-blk-pci",
            "id": f"dev-{node_name}",
            "drive": node_name,
            "serial": serial,
        },
    )
