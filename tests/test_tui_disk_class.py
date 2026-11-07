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


def test_toggle_on_a_disk_row_switches_and_replans(user_pc_state) -> None:
    user_pc_state.focus = ("disk", "sda", None)
    tui._toggle_focused_disk_class(_window(), user_pc_state)
    assert user_pc_state.class_answers == {"sda": DiskClass.SSD}
    assert "main" in _vgs(user_pc_state) and _vgs(user_pc_state)["main"] == ["sda3"]
    assert user_pc_state.focus == ("disk", "sda", None)

    tui._toggle_focused_disk_class(_window(), user_pc_state)
    assert user_pc_state.class_answers == {"sda": DiskClass.HDD}
    assert _vgs(user_pc_state)["main"] == ["md0"]


def test_toggle_works_on_any_disk(user_pc_state) -> None:
    """R-S4: not only the ambiguous one (here an HDD planned as an SSD)."""

    user_pc_state.class_answers = {"sda": DiskClass.SSD}
    user_pc_state.focus = ("disk", "sdb", None)
    tui._toggle_focused_disk_class(_window(), user_pc_state)
    assert user_pc_state.class_answers == {"sda": DiskClass.SSD, "sdb": DiskClass.SSD}
    assert user_pc_state.plan["disk_classes"] == {"sda": "ssd", "sdb": "ssd"}


def test_toggle_needs_a_disk_row(user_pc_state) -> None:
    user_pc_state.focus = ("vg", "main", None)
    before = user_pc_state.plan
    window = _window("x")
    tui._toggle_focused_disk_class(window, user_pc_state)
    assert user_pc_state.plan is before and user_pc_state.class_answers == {}
    assert any("Select a disk's row" in text for text in window.lines.values())


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
