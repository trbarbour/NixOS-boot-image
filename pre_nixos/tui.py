"""Interactive TUI for manual disk provisioning.

This module renders the storage plan, allows basic edits, and lets the
user apply the plan.  It intentionally covers only a subset of possible
customisations; advanced users can edit the plan file directly.
"""
from __future__ import annotations

import curses
import json
from typing import Any

from . import inventory, planner, apply, network


def _draw_plan(stdscr: curses.window, plan: dict[str, Any]) -> None:
    """Display the current plan and network info."""
    stdscr.clear()
    status = network.get_lan_status()
    height, width = stdscr.getmaxyx()
    stdscr.addstr(0, 0, f"IP: {status}")
    lines = json.dumps(plan, indent=2).splitlines()
    for idx, line in enumerate(lines[: height - 3]):
        stdscr.addstr(idx + 1, 0, line[: width - 1])
    stdscr.addstr(height - 2, 0, "[E]dit  [S]ave  [L]oad  [A]pply  [Q]uit")
    stdscr.refresh()


def _edit_plan(stdscr: curses.window, plan: dict[str, Any]) -> None:
    """Simple editor for arrays and logical volumes."""
    curses.echo()
    stdscr.clear()
    stdscr.addstr("Edit (array/lv/add): ")
    choice = stdscr.getstr().decode().strip()
    if choice == "array" and plan.get("arrays"):
        for idx, arr in enumerate(plan["arrays"]):
            line = f"{idx}: {arr['name']} level={arr['level']} devices={' '.join(arr['devices'])}"
            stdscr.addstr(f"{line}\n")
        stdscr.addstr("Select array: ")
        try:
            idx = int(stdscr.getstr().decode().strip())
            arr = plan["arrays"][idx]
            stdscr.addstr("New level (blank to keep): ")
            level = stdscr.getstr().decode().strip() or arr["level"]
            stdscr.addstr("Devices (space separated, blank to keep): ")
            devices_str = stdscr.getstr().decode().strip()
            if devices_str:
                arr["devices"] = devices_str.split()
            arr["level"] = level
        except Exception:
            pass
    elif choice == "lv" and plan.get("lvs"):
        for idx, lv in enumerate(plan["lvs"]):
            line = f"{idx}: {lv['name']} size={lv['size']} vg={lv['vg']}"
            stdscr.addstr(f"{line}\n")
        stdscr.addstr("Select LV: ")
        try:
            idx = int(stdscr.getstr().decode().strip())
            lv = plan["lvs"][idx]
            stdscr.addstr("New name (blank to keep): ")
            name = stdscr.getstr().decode().strip() or lv["name"]
            stdscr.addstr("New size (blank to keep): ")
            size = stdscr.getstr().decode().strip() or lv["size"]
            lv.update({"name": name, "size": size})
        except Exception:
            pass
    elif choice == "add":
        stdscr.addstr("LV name: ")
        name = stdscr.getstr().decode().strip()
        stdscr.addstr("VG name: ")
        vg = stdscr.getstr().decode().strip()
        stdscr.addstr("Size (e.g. 10G): ")
        size = stdscr.getstr().decode().strip()
        if name and vg and size:
            plan.setdefault("lvs", []).append({"name": name, "vg": vg, "size": size})
    curses.noecho()


def _save_plan(stdscr: curses.window, plan: dict[str, Any]) -> None:
    """Prompt for a path and save the plan as JSON."""
    curses.echo()
    stdscr.clear()
    stdscr.addstr("Save to file: ")
    path = stdscr.getstr().decode().strip()
    if path:
        try:
            with open(path, "w", encoding="utf-8") as fh:
                json.dump(plan, fh, indent=2)
        except Exception:
            pass
    curses.noecho()


def _load_plan(stdscr: curses.window, plan: dict[str, Any]) -> dict[str, Any]:
    """Prompt for a path and load a plan from JSON."""
    curses.echo()
    stdscr.clear()
    stdscr.addstr("Load from file: ")
    path = stdscr.getstr().decode().strip()
    curses.noecho()
    if path:
        try:
            with open(path, encoding="utf-8") as fh:
                return json.load(fh)
        except Exception:
            pass
    return plan


def run() -> None:
    """Launch the interactive provisioning TUI."""
    disks = inventory.enumerate_disks()
    ram_gb = inventory.detect_ram_gb()
    plan = planner.plan_storage("fast", disks, ram_gb=ram_gb)

    def _main(stdscr: curses.window) -> None:
        nonlocal plan
        while True:
            _draw_plan(stdscr, plan)
            ch = stdscr.getkey().lower()
            if ch == "q":
                break
            if ch == "e":
                _edit_plan(stdscr, plan)
            if ch == "s":
                _save_plan(stdscr, plan)
            if ch == "l":
                plan = _load_plan(stdscr, plan)
            if ch == "a":
                stdscr.clear()
                stdscr.addstr(0, 0, "Applying plan...\n")
                stdscr.refresh()
                apply.apply_plan(plan)
                stdscr.addstr(1, 0, "Done. Press any key to exit.")
                stdscr.getkey()
                break

    curses.wrapper(_main)

