import json
from pathlib import Path

from pre_nixos.logging_utils import (
    _DEFAULT_LOG_FILE,
    _DEFAULT_LOG_FILE_PATH,
    log_event,
)


def test_log_event_emits_json_to_stderr(capsys, monkeypatch) -> None:
    monkeypatch.setenv("PRE_NIXOS_LOG_EVENTS", "1")

    log_event("pre_nixos.test", path=Path("/tmp/demo"), value=5)

    captured = capsys.readouterr()
    assert captured.out == ""
    lines = [line for line in captured.err.splitlines() if line.strip()]
    assert len(lines) == 1
    record = json.loads(lines[0])
    assert record["event"] == "pre_nixos.test"
    assert record["path"] == "/tmp/demo"
    assert record["value"] == 5
    assert "timestamp" in record


def test_default_log_file_path_packaged() -> None:
    assert _DEFAULT_LOG_FILE_PATH.exists()
    assert _DEFAULT_LOG_FILE == Path(_DEFAULT_LOG_FILE_PATH.read_text().strip())


def test_log_event_appends_to_file(tmp_path, capsys, monkeypatch) -> None:
    monkeypatch.setenv("PRE_NIXOS_LOG_EVENTS", "1")
    log_path = tmp_path / "logs" / "actions.log"
    monkeypatch.setenv("PRE_NIXOS_LOG_FILE", str(log_path))

    log_event("pre_nixos.test.file", payload={"key": "value"})

    captured = capsys.readouterr()
    stderr_lines = [line for line in captured.err.splitlines() if line.strip()]
    assert len(stderr_lines) == 1
    stderr_record = json.loads(stderr_lines[0])

    file_lines = log_path.read_text(encoding="utf-8").splitlines()
    assert len(file_lines) == 1
    file_record = json.loads(file_lines[0])

    assert file_record == stderr_record
    assert file_record["event"] == "pre_nixos.test.file"
