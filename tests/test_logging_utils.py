import json
from pathlib import Path

from pre_nixos.logging_utils import log_event


def test_log_event_emits_json_to_stderr(capsys) -> None:
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
