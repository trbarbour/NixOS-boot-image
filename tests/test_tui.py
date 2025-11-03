import json
import pytest

from pre_nixos import inventory
import pre_nixos.tui as tui


class FakeWindow:
    """Minimal stand-in for a curses window used in tests."""

    def __init__(self, height: int = 25, width: int = 100):
        self.height = height
        self.width = width
        self.lines: dict[int, str] = {}
        self.buffer: list[str] = []

    def clear(self) -> None:  # pragma: no cover - behaviour is a no-op
        pass

    def refresh(self) -> None:  # pragma: no cover - behaviour is a no-op
        pass

    def getmaxyx(self) -> tuple[int, int]:
        return (self.height, self.width)

    def addstr(self, *args):
        if len(args) == 1:
            self.buffer.append(args[0])
            return
        y, _x, text = args
        self.lines[y] = text

    def getstr(self):  # pragma: no cover - only used for save/load tests
        raise NotImplementedError("FakeWindow requires explicit inputs")


@pytest.fixture
def sample_plan() -> dict:
    return {
        "partitions": {
            "nvme0n1": [
                {"name": "nvme0n1p1", "type": "efi"},
                {"name": "nvme0n1p2", "type": "lvm"},
            ],
            "sda": [
                {"name": "sda1", "type": "lvm"},
                {"name": "sda2", "type": "lvm"},
            ],
        },
        "arrays": [
            {
                "name": "md0",
                "level": "raid1",
                "devices": ["nvme0n1p2", "sda1"],
                "type": "ssd",
            }
        ],
        "vgs": [
            {"name": "main", "devices": ["md0"]},
            {"name": "bulk", "devices": ["sda2"]},
        ],
        "lvs": [
            {"name": "slash", "vg": "main", "size": "50G"},
            {"name": "home", "vg": "main", "size": "100G"},
            {"name": "data", "vg": "bulk", "size": "1T"},
        ],
    }


@pytest.fixture
def sample_disks() -> list[inventory.Disk]:
    return [
        inventory.Disk(name="nvme0n1", rotational=False, nvme=True),
        inventory.Disk(name="sda", rotational=True, nvme=False),
    ]


@pytest.fixture
def renderer(sample_plan, sample_disks) -> tui.PlanRenderer:
    return tui.PlanRenderer(sample_plan, sample_disks)


@pytest.fixture
def state(sample_plan, sample_disks) -> tui.TUIState:
    return tui._initial_state(sample_plan, sample_disks)


def test_tui_exposes_run():
    assert callable(tui.run)


def test_plan_renderer_prefers_detailed_profile(renderer):
    render = renderer.render(100, 20, None, "auto", expanded=())
    assert render.profile == "detailed"
    assert render.focusables[0] == ("lv", "main", "slash")
    assert render.lines[0].startswith("Disk nvme0n1")


def test_plan_renderer_deduplicates_array_vgs():
    plan = {
        "partitions": {
            "nvme0n1": [
                {"name": "nvme0n1p1", "type": "efi"},
                {"name": "nvme0n1p2", "type": "lvm"},
            ],
            "nvme1n1": [
                {"name": "nvme1n1p1", "type": "efi"},
                {"name": "nvme1n1p2", "type": "lvm"},
            ],
        },
        "arrays": [
            {
                "name": "md0",
                "level": "raid0",
                "devices": ["nvme0n1p2", "nvme1n1p2"],
                "type": "ssd",
            }
        ],
        "vgs": [
            {"name": "main", "devices": ["md0"]},
        ],
        "lvs": [
            {"name": "slash", "vg": "main", "size": "50G"},
        ],
    }
    disks = [
        inventory.Disk(name="nvme0n1", rotational=False, nvme=True),
        inventory.Disk(name="nvme1n1", rotational=False, nvme=True),
    ]
    render = tui.PlanRenderer(plan, disks).render(120, 40, None, "detailed", ())

    vg_lines = [line for line in render.lines if "VG main" in line]
    lv_lines = [line for line in render.lines if "slash 50G" in line]

    assert len(vg_lines) == 1
    assert len(lv_lines) == 1
    assert not any("Disk nvme1n1" in line and "VG main" in line for line in render.lines)
    assert any("Disk nvme1n1" in line and "md0" in line for line in render.lines)


def test_plan_renderer_falls_back_to_minimal(renderer):
    render = renderer.render(40, 10, None, "auto", expanded=())
    assert render.profile == "minimal"
    assert render.focusables[0] == ("disk", "nvme0n1", None)
    assert any("Disk nvme0n1" in line for line in render.lines)


def test_minimal_layout_expands_focus(renderer):
    focus = ("vg", "main", None)
    render = renderer.render(40, 10, focus, "minimal", expanded={focus})
    assert any("⇒ VG main" in line for line in render.lines)
    assert any("slash 50G" in line for line in render.lines)
    assert focus in render.focusables


def test_draw_plan_assigns_initial_focus(monkeypatch, state):
    win = FakeWindow(height=20, width=100)
    monkeypatch.setattr(tui.network, "get_lan_status", lambda: "203.0.113.7")
    render = tui._draw_plan(win, state)
    assert "203.0.113.7" in win.lines[0]
    assert state.focus is not None
    first_canvas_row = min(y for y in win.lines if y >= 2)
    assert win.lines[first_canvas_row].startswith("▶ ")
    assert render is not None


def test_draw_plan_displays_messages(monkeypatch, state):
    win = FakeWindow(height=20, width=100)
    monkeypatch.setattr(tui.network, "get_lan_status", lambda: "missing SSH public key")
    tui._draw_plan(win, state)
    assert "missing SSH public key" in win.lines[0]


def test_move_focus_wraps_and_skips_empty_tokens():
    state = tui._initial_state({}, [])
    render = tui.RenderResult(
        lines=["", "", "", ""],
        row_tokens=[None, ("disk", "one", None), None, ("vg", "vg1", None)],
        focusables=[("disk", "one", None), ("vg", "vg1", None)],
        profile="minimal",
        warnings=[],
        fits=True,
    )

    state.focus = None
    tui._move_focus(state, render, 1)
    assert state.focus == ("disk", "one", None)

    tui._move_focus(state, render, -1)
    assert state.focus == ("vg", "vg1", None)

    tui._move_focus(state, render, 1)
    assert state.focus == ("disk", "one", None)


def test_cycle_profile_loops_through_sequence():
    sequence = ["auto", "detailed", "compact", "minimal", "auto"]
    current = sequence[0]
    for expected in sequence[1:]:
        current = tui._cycle_profile(current)
        assert current == expected


def test_save_and_load_plan(tmp_path, monkeypatch):
    class PromptWindow(FakeWindow):
        def __init__(self, inputs):
            super().__init__()
            self._inputs = inputs

        def getstr(self):
            return self._inputs.pop(0)

    monkeypatch.setattr(tui.curses, "echo", lambda: None)
    monkeypatch.setattr(tui.curses, "noecho", lambda: None)

    plan = {"a": 1}
    path = tmp_path / "plan.json"

    win = PromptWindow([str(path).encode()])
    tui._save_plan(win, plan)
    assert json.loads(path.read_text()) == plan

    win = PromptWindow([str(path).encode()])
    loaded = tui._load_plan(win, {"old": 0})
    assert loaded == plan
