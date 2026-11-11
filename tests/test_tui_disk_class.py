"""The TUI and disk classes (R-S3, R-S4; task queue item 34;
plans/2026-11-07T161535Z-ssd-model-name-design.md, D3 (a), (b))."""

from __future__ import annotations

import pytest

import pre_nixos.tui as tui
from pre_nixos.boot_layout import BootLayout
from pre_nixos.disk_class import DiskClass
from pre_nixos.planner import plan_storage
from tests.test_disk_class import USER_PC
from tests.test_tui import FakeWindow


@pytest.fixture
def user_pc_state(existing_storage) -> tui.TUIState:
    """The TUI's state at start on the user's PC (the kernel's plan), blank disks."""

    existing_storage.devices = []

    plan = plan_storage("fast", USER_PC, ram_gb=16, boot_layout=BootLayout.X86_BIOS)
    state = tui._initial_state(plan, list(USER_PC), None)
    state.ram_gb = 16
    state.boot_layout = BootLayout.X86_BIOS
    return state


def _vgs(state: tui.TUIState) -> dict[str, list[str]]:
    return {vg["name"]: vg["devices"] for vg in state.plan["vgs"]}


def _window(*keys: str) -> FakeWindow:
    window = FakeWindow()
    window.key_queue = list(keys)
    return window


def test_start_up_question_answered_ssd_replans(user_pc_state) -> None:
    window = _window("x", "S")  # an unrelated key is ignored; only S or H answers
    tui._ask_disk_classes(window, user_pc_state)
    assert user_pc_state.class_answers == {"sda": DiskClass.SSD}
    assert _vgs(user_pc_state) == {"main": ["sda3"], "swap": ["md0"]}
    assert user_pc_state.plan["disk_classes"] == {"sda": "ssd"}
    assert not user_pc_state.disks[0].rotational
    assert user_pc_state.kernel_disks[0].rotational  # the kernel's view is kept
    assert window.key_queue == []
    assert any("G.SKILL 128GB SSD" in text for text in window.lines.values())


def test_start_up_question_answered_hdd_keeps_the_kernel_plan(user_pc_state) -> None:
    tui._ask_disk_classes(_window("h"), user_pc_state)
    assert user_pc_state.class_answers == {"sda": DiskClass.HDD}
    assert _vgs(user_pc_state) == {"main": ["md0"], "large": ["sda1"]}


def test_no_question_without_an_ambiguous_disk(user_pc_state) -> None:
    user_pc_state.kernel_disks = USER_PC[1:]
    before = user_pc_state.plan
    window = _window()
    tui._ask_disk_classes(window, user_pc_state)
    assert user_pc_state.plan is before and window.lines == {}


def test_toggle_lists_every_disk_and_switches_the_chosen_one(user_pc_state) -> None:
    window = _window("1")
    tui._toggle_disk_class(window, user_pc_state)
    listed = "\n".join(window.lines.values())
    assert "[1] sda (G.SKILL 128GB SSD): HDD (kernel)" in listed
    assert "[2] sdb (ST3750528AS): HDD (kernel)" in listed
    assert "[3] sdd (ST3750528AS): HDD (kernel)" in listed
    assert user_pc_state.class_answers == {"sda": DiskClass.SSD}
    assert _vgs(user_pc_state) == {"main": ["sda3"], "swap": ["md0"]}

    window = _window("1")
    tui._toggle_disk_class(window, user_pc_state)
    assert "[1] sda (G.SKILL 128GB SSD): SSD (your answer)" in "\n".join(window.lines.values())
    assert user_pc_state.class_answers == {"sda": DiskClass.HDD}
    assert _vgs(user_pc_state)["main"] == ["md0"]


def test_toggle_reaches_disks_whose_rows_focus_lvs_or_arrays(user_pc_state, monkeypatch) -> None:
    """Codex on #335 (P2): after answering sda as SSD, the detailed layout
    offers no ``disk`` focus for either HDD (their rows focus the swap LV
    and md0), yet R-S4 says any disk's class can be set."""

    user_pc_state.class_answers = {"sda": DiskClass.SSD}
    tui._replan(user_pc_state)
    render = user_pc_state.renderer.render(200, 40, None, "detailed", set())
    assert not any(token and token[0] == "disk" and token[1] == "sdb" for token in render.focusables)

    tui._toggle_disk_class(_window("2"), user_pc_state)
    assert user_pc_state.class_answers == {"sda": DiskClass.SSD, "sdb": DiskClass.SSD}
    assert user_pc_state.plan["disk_classes"] == {"sda": "ssd", "sdb": "ssd"}


@pytest.mark.parametrize("key", ["q", "\x1b"])
def test_toggle_can_be_cancelled(user_pc_state, key) -> None:
    before = user_pc_state.plan
    window = _window("z", key)  # an unlisted key is ignored
    tui._toggle_disk_class(window, user_pc_state)
    assert user_pc_state.plan is before and user_pc_state.class_answers == {}
    assert window.key_queue == []


def test_apply_refuses_while_a_disk_is_unconfirmed(user_pc_state, monkeypatch) -> None:
    def no_scan():
        raise AssertionError("must stop before inspecting storage")

    monkeypatch.setattr(tui.storage_detection, "detect_existing_storage", no_scan)
    window = _window("x")
    assert tui._handle_apply_plan(window, user_pc_state) is False
    assert any("Disk type unconfirmed" in text for text in window.lines.values())


def test_footer_lists_the_toggle(user_pc_state, monkeypatch) -> None:
    monkeypatch.setattr(tui.network, "get_lan_status", lambda: "none")
    window = FakeWindow(width=300)
    tui._draw_plan(window, user_pc_state)
    assert "[T] SSD/HDD" in window.lines[window.height - 1]


class BoundedWindow(FakeWindow):
    """Like curses: writing below the last row is an error."""

    def addstr(self, *args):
        if len(args) == 3 and not 0 <= args[0] < self.height:
            raise tui.curses.error("addwstr() returned ERR")
        super().addstr(*args)

    def clear(self) -> None:
        self.lines = {}


def _many_disks_state(existing_storage, count: int) -> tui.TUIState:
    from pre_nixos.inventory import Disk

    existing_storage.devices = []
    disks = [Disk(name=f"sd{chr(97 + i // 26)}{chr(97 + i % 26)}", model="HDD", size=500 * 1024**3, rotational=True) for i in range(count)]
    plan = plan_storage("fast", disks, ram_gb=16, boot_layout=BootLayout.X86_BIOS)
    state = tui._initial_state(plan, disks, None)
    state.ram_gb = 16
    state.boot_layout = BootLayout.X86_BIOS
    return state


def test_disk_list_pages_to_fit_the_terminal(existing_storage) -> None:
    """Codex on #335 (P2, second review): with more disks than rows, the list
    wrote below the window and curses raised.  It now pages ([N]/[P])."""

    state = _many_disks_state(existing_storage, 40)
    window = BoundedWindow(height=12, width=80)  # 8 disks per page: 5 pages
    window.key_queue = ["n", "p", "n", "n", "1"]  # page 3, its first disk
    tui._toggle_disk_class(window, state)
    names = [disk.name for disk in state.kernel_disks]
    assert list(state.class_answers) == [names[16]]
    shown = "\n".join(window.lines.values())
    assert "Page 3 of 5" in shown and f"[1] {names[16]} (HDD)" in shown


def test_disk_list_reaches_the_last_disk(existing_storage) -> None:
    state = _many_disks_state(existing_storage, 40)
    window = BoundedWindow(height=10, width=80)
    window.key_queue = ["p", "1"]  # [P] on the first page wraps to the last
    tui._toggle_disk_class(window, state)
    (picked,) = state.class_answers
    names = [disk.name for disk in state.kernel_disks]
    assert names.index(picked) > len(names) - 10


# --- task queue item 50 (R-D3): the TUI writes only to the disks it planned for


def test_apply_refuses_when_the_disks_changed(user_pc_state, monkeypatch) -> None:
    """A disk that appears after the TUI planned: nothing is wiped or applied,
    and the user is told to re-plan (plans/2026-11-11T194943Z-disk-settle-design.md, D5)."""

    from pre_nixos.inventory import Disk

    late = Disk(name="sde", model="ST3750528AS", size=750 * 1024**3, rotational=True, serial="E")
    user_pc_state.class_answers = {"sda": DiskClass.SSD}
    monkeypatch.setattr(tui.inventory, "enumerate_disks", lambda: [*USER_PC, late])

    def no_scan():
        raise AssertionError("must stop before inspecting storage")

    monkeypatch.setattr(tui.storage_detection, "detect_existing_storage", no_scan)
    monkeypatch.setattr(tui.apply, "apply_plan", no_scan)
    window = _window("x")
    assert tui._handle_apply_plan(window, user_pc_state) is False
    shown = " ".join(window.lines.values())
    assert "added sde (750 GiB, serial E)" in shown and "[R]" in shown


def test_rescan_plans_for_the_disks_present_now(user_pc_state, monkeypatch) -> None:
    """[R] takes the inventory again and re-plans; answers for disks still
    present are kept, those for disks gone are dropped (item 50, D5)."""

    from pre_nixos import inventory
    from pre_nixos.inventory import Disk

    late = Disk(name="sde", model="ST3750528AS", size=750 * 1024**3, rotational=True, serial="E")
    user_pc_state.class_answers = {"sda": DiskClass.SSD, "sdz": DiskClass.HDD}
    monkeypatch.setattr(tui.inventory, "enumerate_disks", lambda: [*USER_PC, late])
    tui._rescan(_window(), user_pc_state)
    assert [d.name for d in user_pc_state.kernel_disks] == ["sda", "sdb", "sdd", "sde"]
    assert user_pc_state.class_answers == {"sda": DiskClass.SSD}
    assert [e["name"] for e in user_pc_state.plan[inventory.PLAN_KEY]] == ["sda", "sdb", "sdd", "sde"]
    assert inventory.verify_plan_disks(user_pc_state.plan, user_pc_state.protected_disks) == []


def test_rescan_asks_about_a_new_disk_named_ssd_but_rotating(user_pc_state, monkeypatch) -> None:
    from tests.test_disk_class import GSKILL

    user_pc_state.class_answers = {}
    user_pc_state.kernel_disks = []
    monkeypatch.setattr(tui.inventory, "enumerate_disks", lambda: [GSKILL])
    window = _window("h")
    tui._rescan(window, user_pc_state)
    assert user_pc_state.class_answers == {"sda": DiskClass.HDD}
    assert window.key_queue == []
