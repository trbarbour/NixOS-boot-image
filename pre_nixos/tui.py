"""Interactive TUI for manual disk provisioning.

The refreshed interface renders the storage plan pictorially with
disk→array→VG→LV lanes, adapts density to the current terminal, and still
exposes the existing editing and apply workflows.
"""
from __future__ import annotations

from dataclasses import dataclass, field
import curses
import json
import os
from typing import Any, Iterable, Optional, Sequence, Tuple

from . import (
    apply,
    install,
    inventory,
    network,
    planner,
    storage_cleanup,
    storage_detection,
)


FocusKey = Tuple[str, str, Optional[str]]


@dataclass
class RenderResult:
    """Container for the rendered canvas."""

    lines: list[str]
    row_tokens: list[FocusKey | None]
    focusables: list[FocusKey]
    profile: str
    warnings: list[str]
    fits: bool = True


@dataclass
class RowData:
    """Intermediate representation for tabular rows."""

    columns: list[str]
    focus: FocusKey | None
    branch: str | None


PROFILE_SEQUENCE: Sequence[str] = ("auto", "detailed", "compact", "minimal")


def _trim(text: str, width: int) -> str:
    """Return ``text`` truncated to ``width`` columns with ellipsis."""

    if width <= 0:
        return ""
    if len(text) <= width:
        return text
    if width == 1:
        return text[:1]
    return text[: width - 1] + "…"


class PlanRenderer:
    """Prepare textual representations of a storage plan."""

    LEGEND = "Legend: ■ SSD  ● HDD  ☐ EFI  ≡ RAID"

    _PROFILE_SETTINGS = {
        "detailed": {
            "min_widths": (28, 22, 18, 20),
            "weights": (0.40, 0.20, 0.20, 0.20),
        },
        "compact": {
            "min_widths": (22, 18, 16, 16),
            "weights": (0.40, 0.25, 0.20, 0.15),
        },
    }

    def __init__(self, plan: dict[str, Any], disks: list[inventory.Disk]):
        self.plan = plan or {}
        self.disks = {disk.name: disk for disk in disks}

        partitions = self.plan.get("partitions", {})
        self.partitions: dict[str, list[dict[str, str]]] = {
            disk: list(parts) for disk, parts in partitions.items()
        }
        self.arrays = {arr["name"]: arr for arr in self.plan.get("arrays", [])}
        self.device_to_array: dict[str, str] = {}
        for arr in self.plan.get("arrays", []):
            for dev in arr.get("devices", []):
                self.device_to_array[dev] = arr["name"]

        self.device_to_vgs: dict[str, list[str]] = {}
        for vg in self.plan.get("vgs", []):
            for dev in vg.get("devices", []):
                self.device_to_vgs.setdefault(dev, []).append(vg["name"])

        self.vg_to_lvs: dict[str, list[dict[str, str]]] = {}
        for lv in self.plan.get("lvs", []):
            self.vg_to_lvs.setdefault(lv["vg"], []).append(lv)

        self.partition_to_disk: dict[str, str] = {}
        for disk_name, parts in self.partitions.items():
            for part in parts:
                self.partition_to_disk[part["name"]] = disk_name

        self.disk_order = list(self.partitions.keys())
        if not self.disk_order and self.disks:
            self.disk_order = sorted(self.disks.keys())

        self.array_to_disks: dict[str, set[str]] = {}
        for name, arr in self.arrays.items():
            members = set()
            for dev in arr.get("devices", []):
                disk = self.partition_to_disk.get(dev)
                if disk:
                    members.add(disk)
            self.array_to_disks[name] = members

        self.vg_to_disks: dict[str, set[str]] = {}
        for vg in self.plan.get("vgs", []):
            disks_for_vg: set[str] = set()
            for dev in vg.get("devices", []):
                if dev in self.arrays:
                    disks_for_vg.update(self.array_to_disks.get(dev, set()))
                else:
                    disk = self.partition_to_disk.get(dev)
                    if disk:
                        disks_for_vg.add(disk)
            self.vg_to_disks[vg["name"]] = disks_for_vg

        self.disk_to_vgs: dict[str, list[str]] = {}
        for disk_name, parts in self.partitions.items():
            seen: set[str] = set()
            ordered: list[str] = []
            for part in parts:
                key = self.device_to_array.get(part["name"], part["name"])
                for vg_name in self.device_to_vgs.get(key, []):
                    if vg_name not in seen:
                        ordered.append(vg_name)
                        seen.add(vg_name)
            self.disk_to_vgs[disk_name] = ordered

    # ------------------------------------------------------------------
    # Public helpers
    # ------------------------------------------------------------------
    def describe_focus(self, focus: FocusKey | None) -> str:
        if focus is None:
            return "none"
        kind, primary, secondary = focus
        if kind == "disk":
            return f"Disk {primary}"
        if kind == "array":
            return f"Array {primary}"
        if kind == "vg":
            return f"VG {primary}"
        if kind == "lv" and secondary:
            return f"LV {secondary} (VG {primary})"
        return primary

    def disks_for_focus(self, focus: FocusKey | None) -> set[str]:
        if focus is None:
            return set()
        kind, primary, _ = focus
        if kind == "disk":
            return {primary}
        if kind == "array":
            return set(self.array_to_disks.get(primary, set()))
        if kind in {"vg", "lv"}:
            return set(self.vg_to_disks.get(primary, set()))
        return set()

    # ------------------------------------------------------------------
    # Rendering pipeline
    # ------------------------------------------------------------------
    def render(
        self,
        width: int,
        height: int,
        focus: FocusKey | None,
        profile_hint: str,
        expanded: Iterable[FocusKey],
    ) -> RenderResult:
        order: list[str]
        if profile_hint == "auto":
            order = ["detailed", "compact", "minimal"]
        else:
            order = [profile_hint] + [p for p in ("detailed", "compact", "minimal") if p != profile_hint]

        fallback: RenderResult | None = None
        for profile in order:
            if profile == "minimal":
                layout = self._build_minimal_layout(width, height, focus, expanded)
            else:
                layout = self._build_tabular_layout(width, height, profile)
            if layout is None:
                continue
            layout.profile = profile
            if layout.fits:
                return layout
            fallback = layout

        if fallback is None:
            line = _trim("No planned storage to display", width)
            return RenderResult(
                lines=[line],
                row_tokens=[None],
                focusables=[],
                profile="minimal",
                warnings=["no storage plan"],
                fits=True,
            )

        if len(fallback.lines) > height:
            overflow = len(fallback.lines) - height
            fallback.lines = fallback.lines[:height]
            fallback.row_tokens = fallback.row_tokens[:height]
            fallback.warnings.append(f"truncated {overflow} line(s)")
        fallback.fits = True
        return fallback

    # ------------------------------------------------------------------
    # Tabular layout (detailed & compact)
    # ------------------------------------------------------------------
    def _build_tabular_layout(
        self, width: int, height: int, profile: str
    ) -> RenderResult | None:
        settings = self._PROFILE_SETTINGS.get(profile)
        if not settings:
            return None
        col_widths = self._column_widths(width, settings)
        if col_widths is None:
            return None

        rows = self._generate_rows(profile)
        if not rows:
            line = _trim("No planned storage to display", width)
            return RenderResult(
                lines=[line],
                row_tokens=[None],
                focusables=[],
                profile=profile,
                warnings=[],
                fits=True,
            )

        focusables: list[FocusKey] = []
        seen_focus: set[FocusKey] = set()
        lines: list[str] = []
        row_tokens: list[FocusKey | None] = []
        for row in rows:
            padded = [self._pad(col, col_widths[idx]) for idx, col in enumerate(row.columns)]
            line = "  ".join(padded).rstrip()
            lines.append(_trim(line, width))
            row_tokens.append(row.focus)
            if row.focus and row.focus not in seen_focus:
                focusables.append(row.focus)
                seen_focus.add(row.focus)

        fits = len(lines) <= height
        return RenderResult(
            lines=lines,
            row_tokens=row_tokens,
            focusables=focusables,
            profile=profile,
            warnings=[],
            fits=fits,
        )

    def _generate_rows(self, profile: str) -> list[RowData]:
        rows: list[RowData] = []
        seen_array_vgs: set[tuple[str, str]] = set()
        for disk_name in self.disk_order:
            partitions = self.partitions.get(disk_name, [])
            disk_label = self._format_disk_label(profile, disk_name, partitions)
            data_parts = [part for part in partitions if part.get("type") != "efi"]

            if not data_parts:
                rows.append(
                    RowData([disk_label, "", "", ""], ("disk", disk_name, None), disk_name)
                )
                continue

            disk_row_started = False
            for part in data_parts:
                source_name = self.device_to_array.get(part["name"])
                source_label = self._format_source_label(profile, source_name, part, disk_name)
                connector = self._continuation()
                vgs = self._vgs_for_source(source_name, part)

                if not vgs:
                    columns = [disk_label if not disk_row_started else "", source_label, "", ""]
                    focus: FocusKey | None
                    if source_name:
                        focus = ("array", source_name, None)
                    else:
                        focus = ("disk", disk_name, None)
                    rows.append(RowData(columns, focus, disk_name))
                    disk_row_started = True
                    continue

                source_first = True
                for vg_name in vgs:
                    if source_name:
                        key = (source_name, vg_name)
                        if key in seen_array_vgs:
                            columns = [
                                disk_label if not disk_row_started else "",
                                source_label if source_first else connector,
                                "",
                                "",
                            ]
                            focus: FocusKey | None
                            if source_name:
                                focus = ("array", source_name, None)
                            else:
                                focus = ("disk", disk_name, None)
                            rows.append(RowData(columns, focus, disk_name))
                            disk_row_started = True
                            source_first = False
                            continue
                        seen_array_vgs.add(key)

                    vg_label = self._format_vg_label(profile, vg_name)
                    lvs = self.vg_to_lvs.get(vg_name, [])
                    vg_connector = connector

                    if not lvs:
                        columns = [
                            disk_label if not disk_row_started else "",
                            source_label if source_first else connector,
                            vg_label if source_first else vg_connector,
                            "",
                        ]
                        rows.append(RowData(columns, ("vg", vg_name, None), disk_name))
                        disk_row_started = True
                        source_first = False
                        continue

                    lv_first = True
                    for lv in lvs:
                        columns = [
                            disk_label if not disk_row_started else "",
                            source_label if source_first and lv_first else connector,
                            vg_label if source_first and lv_first else vg_connector,
                            self._format_lv_label(profile, lv),
                        ]
                        rows.append(RowData(columns, ("lv", vg_name, lv["name"]), disk_name))
                        disk_row_started = True
                        lv_first = False
                        source_first = False

            # end partitions
        return rows

    # ------------------------------------------------------------------
    # Minimal layout (auto-collapsing)
    # ------------------------------------------------------------------
    def _build_minimal_layout(
        self,
        width: int,
        height: int,
        focus: FocusKey | None,
        expanded: Iterable[FocusKey],
    ) -> RenderResult:
        lines: list[str] = []
        row_tokens: list[FocusKey | None] = []
        focusables: list[FocusKey] = []

        focus_disks = self.disks_for_focus(focus)
        expanded_disks: set[str] = set()
        for token in expanded:
            expanded_disks.update(self.disks_for_focus(token))

        disks_iter = self.disk_order or sorted(self.disks.keys())
        if not disks_iter:
            line = _trim("No planned storage to display", width)
            return RenderResult(
                lines=[line],
                row_tokens=[None],
                focusables=[],
                profile="minimal",
                warnings=[],
                fits=True,
            )

        for disk_name in disks_iter:
            summary = self._minimal_disk_summary(disk_name)
            token: FocusKey = ("disk", disk_name, None)
            lines.append(_trim(summary, width))
            row_tokens.append(token)
            if token not in focusables:
                focusables.append(token)

            if disk_name not in focus_disks and disk_name not in expanded_disks:
                continue

            for vg_name in self.disk_to_vgs.get(disk_name, []):
                vg_line = f"   ⇒ {self._minimal_vg_summary(vg_name)}"
                vg_token: FocusKey = ("vg", vg_name, None)
                lines.append(_trim(vg_line, width))
                row_tokens.append(vg_token)
                if vg_token not in focusables:
                    focusables.append(vg_token)

                for lv in self.vg_to_lvs.get(vg_name, []):
                    lv_line = f"      - {self._format_lv_label('minimal', lv)}"
                    lv_token: FocusKey = ("lv", vg_name, lv["name"])
                    lines.append(_trim(lv_line, width))
                    row_tokens.append(lv_token)
                    if lv_token not in focusables:
                        focusables.append(lv_token)

        fits = len(lines) <= height
        return RenderResult(
            lines=lines,
            row_tokens=row_tokens,
            focusables=focusables,
            profile="minimal",
            warnings=[],
            fits=fits,
        )

    # ------------------------------------------------------------------
    # Formatting helpers
    # ------------------------------------------------------------------
    def _column_widths(self, width: int, settings: dict[str, Sequence[float]]) -> list[int] | None:
        min_widths = list(settings["min_widths"])
        weights = list(settings["weights"])
        gaps = (len(min_widths) - 1) * 2
        base_total = sum(min_widths) + gaps
        if width < base_total:
            return None

        extra = width - base_total
        col_widths = min_widths[:]
        for idx, weight in enumerate(weights):
            if extra <= 0:
                break
            add = int(extra * weight)
            col_widths[idx] += add
            extra -= add
        idx = 0
        while extra > 0:
            col_widths[idx % len(col_widths)] += 1
            extra -= 1
            idx += 1
        return col_widths

    def _pad(self, text: str, width: int) -> str:
        if len(text) >= width:
            return _trim(text, width)
        return text.ljust(width)

    def _disk_icon(self, disk_name: str) -> str:
        disk = self.disks.get(disk_name)
        if disk is None:
            return "◆"
        if disk.rotational:
            return "◎"
        return "⟟"

    def _partition_symbol(self, disk_name: str) -> str:
        disk = self.disks.get(disk_name)
        if disk and disk.rotational:
            return "●"
        return "■"

    def _format_disk_label(
        self, profile: str, disk_name: str, partitions: list[dict[str, str]]
    ) -> str:
        icon = self._disk_icon(disk_name)
        pieces = [f"Disk {disk_name}", icon]
        if partitions:
            part_texts: list[str] = []
            for part in partitions:
                if part.get("type") == "efi":
                    label = "EFI" if profile != "compact" else "E"
                    part_texts.append(f"[☐ {label}]")
                else:
                    name = part.get("name", "?")
                    if profile == "compact":
                        name = name[-4:]
                    part_texts.append(f"[{self._partition_symbol(disk_name)} {name}]")
            if part_texts:
                pieces.append(" ".join(part_texts))
        return "  ".join(pieces).strip()

    def _format_source_label(
        self,
        profile: str,
        array_name: str | None,
        part: dict[str, str],
        disk_name: str,
    ) -> str:
        if array_name:
            array = self.arrays.get(array_name)
            if not array:
                return array_name
            level = array.get("level", "").upper()
            if level and level.startswith("RAID") and profile == "compact":
                level = level.replace("RAID", "R")
            if level == "SINGLE":
                level = "single"
            typ = array.get("type")
            tier = ""
            if typ:
                tier = typ.upper()
            connector = "≡ " if array.get("level") != "single" else ""
            text = f"{array_name} {connector}{level}".strip()
            if tier:
                text = f"{text} ({tier})"
            return text

        name = part.get("name", "?")
        if profile == "compact":
            name = name[-4:]
        return f"PV {name}"

    def _format_vg_label(self, profile: str, vg_name: str) -> str:
        return f"VG {vg_name}"

    def _format_lv_label(self, profile: str, lv: dict[str, str]) -> str:
        size = lv.get("size")
        if profile == "minimal":
            if size:
                return f"{lv.get('name')} {size}"
            return lv.get("name", "LV")
        if size:
            return f"{lv.get('name')} {size}"
        return lv.get("name", "LV")

    def _minimal_disk_summary(self, disk_name: str) -> str:
        icon = self._disk_icon(disk_name)
        vgs = self.disk_to_vgs.get(disk_name, [])
        if not vgs:
            suffix = "no VGs planned"
        else:
            parts: list[str] = []
            for vg in vgs:
                count = len(self.vg_to_lvs.get(vg, []))
                if count == 0:
                    parts.append(f"{vg}")
                elif count == 1:
                    parts.append(f"{vg} (1 LV)")
                else:
                    parts.append(f"{vg} ({count} LVs)")
            suffix = "  ".join(parts)
        return f"Disk {disk_name} {icon}  {suffix}".strip()

    def _minimal_vg_summary(self, vg_name: str) -> str:
        lvs = self.vg_to_lvs.get(vg_name, [])
        if not lvs:
            return f"VG {vg_name}"
        names = [lv.get("name", "LV") for lv in lvs[:3]]
        text = ", ".join(names)
        if len(lvs) > 3:
            text += ", …"
        return f"VG {vg_name} → {text}"

    def _continuation(self) -> str:
        return "└─"

    def _vgs_for_source(self, array_name: str | None, part: dict[str, str]) -> list[str]:
        key = array_name if array_name else part.get("name")
        if not key:
            return []
        return list(self.device_to_vgs.get(key, []))


@dataclass
class TUIState:
    """Mutable state shared between frames."""

    plan: dict[str, Any]
    disks: list[inventory.Disk]
    renderer: PlanRenderer
    focus: FocusKey | None = None
    profile_override: str = "auto"
    expanded: set[FocusKey] = field(default_factory=set)
    cleanup_notice: list[str] = field(default_factory=list)
    lan_config: network.LanConfiguration | None = None
    auto_install_enabled: bool = False
    last_auto_install: install.AutoInstallResult | None = None


def _initial_state(
    plan: dict[str, Any],
    disks: list[inventory.Disk],
    lan_config: network.LanConfiguration | None,
) -> TUIState:
    """Create a :class:`TUIState` from the current plan and inventory."""

    state = TUIState(
        plan=plan,
        disks=disks,
        renderer=PlanRenderer(plan, disks),
        lan_config=lan_config,
    )
    state.cleanup_notice = _initial_cleanup_notice()
    state.auto_install_enabled = lan_config is not None
    return state


def _short_cleanup_description(text: str) -> str:
    """Return a concise label for a cleanup option description."""

    if " (" in text:
        return text.split(" (", 1)[0]
    return text


def _format_cleanup_notice(
    devices: Sequence[storage_detection.ExistingStorageDevice],
) -> list[str]:
    """Return header notice lines describing existing storage cleanup choices."""

    if not devices:
        return []

    count = len(devices)
    sample = [entry.device for entry in devices[:3]]
    device_list = ", ".join(sample)
    if count > 3:
        device_list += ", …"

    summary_line = f"Existing storage on {count} device(s): {device_list}".strip()

    option_parts = [
        f"{option.key}={_short_cleanup_description(option.description)}"
        for option in storage_cleanup.CLEANUP_OPTIONS
    ]
    options_line = (
        "Press [A]pply to choose a wipe method before applying the plan. Options: "
        + ", ".join(option_parts)
    )

    return [summary_line, options_line]


def _initial_cleanup_notice() -> list[str]:
    """Inspect the system to pre-compute cleanup guidance for the header."""

    try:
        devices = storage_detection.detect_existing_storage()
    except Exception as exc:  # pragma: no cover - rare command failures
        message = str(exc).splitlines()[0]
        return [
            "Existing storage scan failed; wipe options will appear when applying.",
            f"Error: {message}",
        ]
    return _format_cleanup_notice(devices)


def _draw_plan(stdscr: curses.window, state: TUIState) -> RenderResult:
    """Display the current plan using the adaptive renderer."""

    stdscr.clear()
    status = network.get_lan_status()
    height, width = stdscr.getmaxyx()
    header_rows = 2 + len(state.cleanup_notice)
    footer_rows = 1
    canvas_height = max(height - header_rows - footer_rows, 0)
    canvas_width = max(width - 2, 10)

    render = state.renderer.render(
        canvas_width, canvas_height, state.focus, state.profile_override, state.expanded
    )

    if render.focusables:
        if state.focus not in render.focusables:
            state.focus = render.focusables[0]
    else:
        state.focus = None

    focus_label = state.renderer.describe_focus(state.focus)
    auto_status = "On" if state.auto_install_enabled else "Off"
    if state.last_auto_install is not None:
        auto_status = f"{auto_status} ({state.last_auto_install.status})"
    header = (
        f"IP: {status}  View: Planned  Focus: {focus_label}  Profile: {render.profile}  "
        f"Auto-install: {auto_status}"
    )
    stdscr.addstr(0, 0, _trim(header, width - 1))
    stdscr.addstr(1, 0, _trim(PlanRenderer.LEGEND, width - 1))
    for idx, line in enumerate(state.cleanup_notice):
        stdscr.addstr(2 + idx, 0, _trim(line, width - 1))

    start_y = header_rows
    max_lines = min(canvas_height, len(render.lines))
    for idx in range(max_lines):
        line = render.lines[idx]
        token = render.row_tokens[idx] if idx < len(render.row_tokens) else None
        prefix = "▶ " if token is not None and token == state.focus else "  "
        stdscr.addstr(start_y + idx, 0, _trim(prefix + line, width - 1))

    footer_parts = [
        "[↑/↓] Move",
        "[Enter] Expand",
        "[Z] Zoom",
        "[E]dit",
        "[S]ave",
        "[L]oad",
        "[A]pply",
        "[I]nstall toggle",
        "[Q]uit",
    ]
    footer = "  ".join(footer_parts)
    if render.warnings:
        footer = f"{footer}  ⚠ {' | '.join(render.warnings)}"
    stdscr.addstr(height - 1, 0, _trim(footer, width - 1))
    stdscr.refresh()
    return render


def _move_focus(state: TUIState, render: RenderResult, direction: int) -> None:
    """Move the focus cursor up or down by one logical row."""

    tokens = render.row_tokens
    if not tokens:
        return
    if state.focus is None:
        for token in tokens:
            if token is not None:
                state.focus = token
                return
        return

    try:
        current_index = next(i for i, tok in enumerate(tokens) if tok == state.focus)
    except StopIteration:
        current_index = -1 if direction > 0 else len(tokens)

    if direction > 0:
        search = range(current_index + 1, len(tokens))
        wrap = range(0, len(tokens))
    else:
        search = range(current_index - 1, -1, -1)
        wrap = range(len(tokens) - 1, -1, -1)

    for idx in search:
        token = tokens[idx]
        if token is not None:
            state.focus = token
            return
    for idx in wrap:
        token = tokens[idx]
        if token is not None:
            state.focus = token
            return


def _cycle_profile(current: str) -> str:
    """Return the next profile override value."""

    try:
        idx = PROFILE_SEQUENCE.index(current)
    except ValueError:
        idx = 0
    return PROFILE_SEQUENCE[(idx + 1) % len(PROFILE_SEQUENCE)]


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


def _show_modal(stdscr: curses.window, lines: Sequence[str]) -> None:
    """Display *lines* and wait for a key press."""

    stdscr.clear()
    height, width = stdscr.getmaxyx()
    for idx, line in enumerate(lines):
        stdscr.addstr(idx, 0, _trim(line, width - 1))
    prompt_row = len(lines)
    stdscr.addstr(prompt_row, 0, _trim("Press any key to continue.", width - 1))
    stdscr.refresh()
    while True:
        try:
            stdscr.getkey()
            break
        except curses.error:
            continue


def _prompt_storage_cleanup(
    stdscr: curses.window,
    devices: Sequence[storage_detection.ExistingStorageDevice],
) -> str | None:
    """Prompt the operator for a storage cleanup action."""

    message = ""

    while True:
        stdscr.clear()
        height, width = stdscr.getmaxyx()
        row = 0
        stdscr.addstr(
            row,
            0,
            _trim("Existing storage detected on the following devices:", width - 1),
        )
        row += 2
        for entry in devices:
            reasons = storage_detection.format_existing_storage_reasons(entry.reasons)
            stdscr.addstr(row, 0, _trim(f"- {entry.device} ({reasons})", width - 1))
            row += 1
        row += 1
        stdscr.addstr(
            row,
            0,
            _trim(
                "Choose how to erase the existing data before applying the plan:",
                width - 1,
            ),
        )
        row += 2
        for option in storage_cleanup.CLEANUP_OPTIONS:
            stdscr.addstr(
                row,
                0,
                _trim(f"[{option.key}] {option.description}", width - 1),
            )
            row += 1
        stdscr.addstr(row, 0, _trim("Selection [q]: ", width - 1))
        if message:
            stdscr.addstr(row + 1, 0, _trim(message, width - 1))
        stdscr.refresh()

        try:
            key = stdscr.getkey()
        except curses.error:
            continue

        normalized = key.lower()
        if normalized in {"\n", "\r"}:
            normalized = "q"
        elif normalized == "key_enter":
            normalized = "q"
        elif len(key) == 1:
            normalized = key.strip().lower()
            if not normalized:
                normalized = "q"

        for option in storage_cleanup.CLEANUP_OPTIONS:
            if normalized == option.key:
                return option.action
        message = "Please choose one of the listed options."


def _handle_apply_plan(stdscr: curses.window, state: TUIState) -> bool:
    """Handle the apply-plan workflow. Returns ``True`` when exiting."""

    execute = os.environ.get("PRE_NIXOS_EXEC") == "1"
    try:
        devices = storage_detection.detect_existing_storage()
    except Exception as exc:  # pragma: no cover - rare detection errors
        _show_modal(stdscr, [f"Failed to inspect existing storage: {exc}"])
        return False

    if devices:
        action = _prompt_storage_cleanup(stdscr, devices)
        if action is None:
            _show_modal(stdscr, ["Aborting without modifying storage."])
            return False
        if action != storage_cleanup.SKIP_CLEANUP:
            targets = [entry.device for entry in devices]
            try:
                storage_cleanup.perform_storage_cleanup(
                    action,
                    targets,
                    execute=execute,
                )
            except Exception as exc:  # pragma: no cover - subprocess failure is rare
                _show_modal(stdscr, [f"Failed to wipe storage: {exc}"])
                return False

    stdscr.clear()
    stdscr.addstr(0, 0, "Applying plan...\n")
    stdscr.refresh()
    auto_message_row = 1
    try:
        apply.apply_plan(state.plan)
    except Exception as exc:  # pragma: no cover - subprocess failure is rare
        _show_modal(stdscr, [f"Failed to apply plan: {exc}"])
        return False

    if state.auto_install_enabled and execute:
        stdscr.addstr(auto_message_row, 0, "Running auto-install...\n")
        stdscr.refresh()

    try:
        auto_result = install.auto_install(
            state.lan_config,
            state.plan,
            enabled=state.auto_install_enabled,
            dry_run=not execute,
        )
    except Exception as exc:  # pragma: no cover - unexpected errors
        state.last_auto_install = install.AutoInstallResult(status="failed", reason=str(exc))
        _show_modal(stdscr, [f"Auto-install failed: {exc}"])
        return False

    state.last_auto_install = auto_result
    if auto_result.status == "failed":
        message = auto_result.reason or "unknown error"
        _show_modal(stdscr, [f"Auto-install failed: {message}"])
        return False

    summary_parts = ["Done."]
    if auto_result.status == "success":
        summary_parts.append("Auto-install completed.")
    elif auto_result.status == "skipped" and auto_result.reason:
        summary_parts.append(f"Auto-install skipped ({auto_result.reason}).")
    stdscr.addstr(auto_message_row, 0, " ".join(summary_parts) + " Press any key to exit.")
    stdscr.refresh()
    while True:
        try:
            stdscr.getkey()
            break
        except curses.error:
            continue
    return True


def run() -> None:
    """Launch the interactive provisioning TUI."""

    lan_config = network.configure_lan()
    disks = inventory.enumerate_disks()
    ram_gb = inventory.detect_ram_gb()
    plan = planner.plan_storage("fast", disks, ram_gb=ram_gb)
    state = _initial_state(plan, disks, lan_config)

    def refresh_renderer() -> None:
        state.renderer = PlanRenderer(state.plan, state.disks)
        state.focus = None
        state.expanded.clear()

    def _main(stdscr: curses.window) -> None:
        try:
            stdscr.keypad(True)
        except curses.error:
            pass

        try:
            curses.curs_set(0)
        except curses.error:
            pass

        while True:
            render = _draw_plan(stdscr, state)
            try:
                key = stdscr.getkey()
            except curses.error:
                continue

            key_lower = key.lower() if len(key) == 1 else key

            if key_lower == "KEY_RESIZE":
                continue
            if key_lower == "q":
                break
            if key_lower == "e":
                _edit_plan(stdscr, state.plan)
                refresh_renderer()
                continue
            if key_lower == "s":
                _save_plan(stdscr, state.plan)
                continue
            if key_lower == "l":
                state.plan = _load_plan(stdscr, state.plan)
                refresh_renderer()
                continue
            if key_lower == "a":
                if _handle_apply_plan(stdscr, state):
                    break
                refresh_renderer()
                continue
            if key_lower == "i":
                state.auto_install_enabled = not state.auto_install_enabled
                continue
            if key_lower in {"KEY_UP", "k"}:
                _move_focus(state, render, -1)
                continue
            if key_lower in {"KEY_DOWN", "j"}:
                _move_focus(state, render, 1)
                continue
            if key_lower in {"KEY_ENTER", "\n", "\r"}:
                if state.focus is not None:
                    if state.focus in state.expanded:
                        state.expanded.remove(state.focus)
                    else:
                        state.expanded.add(state.focus)
                continue
            if key_lower == "z":
                state.profile_override = _cycle_profile(state.profile_override)
                continue

    curses.wrapper(_main)

