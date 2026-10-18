"""Unit tests for tests/vm/qmp.py against an in-process QMP server."""
from __future__ import annotations

import json
import socket
import threading
from pathlib import Path
from typing import Any, Callable, Dict, Iterator, List, Optional

import pytest

from tests.vm.qmp import (
    UNIX_SOCKET_PATH_MAX,
    QmpClient,
    QmpError,
    allocate_qmp_socket_path,
    hotplug_virtio_disk,
)

# Maps a request to the replies to send; ``None`` closes the connection.
Handler = Callable[[Dict[str, Any]], Optional[List[Dict[str, Any]]]]
GREETING = {"QMP": {"version": {"qemu": {"major": 8, "minor": 2, "micro": 2}}, "capabilities": []}}


@pytest.fixture
def qmp_server() -> Iterator[Callable[[Handler], Path]]:
    """Start a fake QMP server; ``handler`` maps a request to the replies to send."""

    threads: List[threading.Thread] = []
    received: List[Dict[str, Any]] = []

    def start(handler: Handler) -> Path:
        path = allocate_qmp_socket_path()
        server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        server.bind(str(path))
        server.listen(1)

        def serve() -> None:
            conn, _ = server.accept()
            with conn, conn.makefile("rb") as reader:
                conn.sendall(json.dumps(GREETING).encode() + b"\n")
                for line in reader:
                    request = json.loads(line)
                    received.append(request)
                    replies = handler(request)
                    if replies is None:
                        break
                    for reply in replies:
                        conn.sendall(json.dumps(reply).encode() + b"\n")
            server.close()

        thread = threading.Thread(target=serve, daemon=True)
        thread.start()
        threads.append(thread)
        return path

    start.received = received  # type: ignore[attr-defined]
    yield start
    for thread in threads:
        thread.join(timeout=5)


def test_allocated_socket_paths_fit_the_unix_limit() -> None:
    assert len(str(allocate_qmp_socket_path())) <= UNIX_SOCKET_PATH_MAX


def test_rejects_socket_paths_over_the_unix_limit(tmp_path: Path) -> None:
    with pytest.raises(QmpError, match="limit"):
        QmpClient(Path("/tmp/" + "x" * 120))


def test_execute_skips_events_and_returns_the_result(qmp_server: Any) -> None:
    def handler(request: Dict[str, Any]) -> List[Dict[str, Any]]:
        if request["execute"] == "query-status":
            return [{"event": "RESUME"}, {"return": {"status": "running"}}]
        return [{"return": {}}]

    with QmpClient(qmp_server(handler)) as client:
        assert client.execute("query-status") == {"status": "running"}
    assert [r["execute"] for r in qmp_server.received] == ["qmp_capabilities", "query-status"]


def test_execute_raises_on_qmp_error(qmp_server: Any) -> None:
    def handler(request: Dict[str, Any]) -> List[Dict[str, Any]]:
        if request["execute"] == "device_add":
            return [{"error": {"class": "GenericError", "desc": "Duplicate ID"}}]
        return [{"return": {}}]

    with QmpClient(qmp_server(handler)) as client:
        with pytest.raises(QmpError, match="device_add failed: GenericError: Duplicate ID"):
            client.execute("device_add", {"driver": "virtio-blk-pci"})


def test_connection_closed_mid_command_is_an_error(qmp_server: Any) -> None:
    def handler(request: Dict[str, Any]) -> Optional[List[Dict[str, Any]]]:
        if request["execute"] == "quit":
            return None  # QEMU exits without replying
        return [{"return": {}}]

    with QmpClient(qmp_server(handler)) as client:
        with pytest.raises(QmpError, match="closed"):
            client.execute("quit")


def test_connect_failure_is_reported(tmp_path: Path) -> None:
    with pytest.raises(QmpError, match="cannot connect"):
        QmpClient(tmp_path / "missing.sock").connect()


def test_hotplug_issues_blockdev_add_then_device_add(qmp_server: Any, tmp_path: Path) -> None:
    path = qmp_server(lambda request: [{"return": {}}])
    with QmpClient(path) as client:
        hotplug_virtio_disk(client, image=tmp_path / "d.img", node_name="hp1", serial="residue1")

    blockdev, device = qmp_server.received[1:]
    assert blockdev == {
        "execute": "blockdev-add",
        "arguments": {
            "driver": "raw",
            "node-name": "hp1",
            "file": {"driver": "file", "filename": str(tmp_path / "d.img")},
        },
    }
    assert device == {
        "execute": "device_add",
        "arguments": {
            "driver": "virtio-blk-pci",
            "id": "dev-hp1",
            "drive": "hp1",
            "serial": "residue1",
        },
    }
