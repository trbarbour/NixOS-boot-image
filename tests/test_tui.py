import json
from pre_nixos import inventory
import pre_nixos.tui as tui


def test_tui_exposes_run():
    assert callable(tui.run)


def _sample_state():
    plan = {
        "partitions": {
            "nvme0n1": [
                {"name": "nvme0n1p1", "type": "efi"},
                {"name": "nvme0n1p2", "type": "lvm"},
            ]
        },
        "arrays": [],
        "vgs": [{"name": "main", "devices": ["nvme0n1p2"]}],
        "lvs": [{"name": "root", "vg": "main", "size": "50G"}],
    }
    disks = [inventory.Disk(name="nvme0n1", rotational=False, nvme=True)]
    return tui._initial_state(plan, disks)


def test_draw_plan_displays_ip(monkeypatch):
    class FakeWin:
        def __init__(self):
            self.lines = {}

        def clear(self):
            pass

        def getmaxyx(self):
            return (25, 80)

        def addstr(self, y, x, s):
            self.lines[y] = s

        def refresh(self):
            pass

    win = FakeWin()
    monkeypatch.setattr(tui.network, "get_lan_status", lambda: "203.0.113.7")
    state = _sample_state()
    tui._draw_plan(win, state)
    assert "203.0.113.7" in win.lines[0]
    canvas = [line for y, line in win.lines.items() if y >= 2]
    assert any("Disk nvme0n1" in line for line in canvas)


def test_draw_plan_displays_messages(monkeypatch):
    class FakeWin:
        def __init__(self):
            self.lines = {}

        def clear(self):
            pass

        def getmaxyx(self):
            return (25, 80)

        def addstr(self, y, x, s):
            self.lines[y] = s

        def refresh(self):
            pass

    win = FakeWin()
    monkeypatch.setattr(tui.network, "get_lan_status", lambda: "missing SSH public key")
    state = _sample_state()
    tui._draw_plan(win, state)
    assert "missing SSH public key" in win.lines[0]


def test_save_and_load_plan(tmp_path, monkeypatch):
    class FakeWin:
        def __init__(self, inputs):
            self._inputs = inputs

        def clear(self):
            pass

        def addstr(self, *args):
            pass

        def getstr(self):
            return self._inputs.pop(0)

    monkeypatch.setattr(tui.curses, "echo", lambda: None)
    monkeypatch.setattr(tui.curses, "noecho", lambda: None)

    plan = {"a": 1}
    path = tmp_path / "plan.json"

    win = FakeWin([str(path).encode()])
    tui._save_plan(win, plan)
    assert json.loads(path.read_text()) == plan

    win = FakeWin([str(path).encode()])
    loaded = tui._load_plan(win, {"old": 0})
    assert loaded == plan
