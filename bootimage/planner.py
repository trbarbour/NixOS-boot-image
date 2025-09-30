"""Planner that emits Disko configuration and applies it via the Disko CLI."""

from __future__ import annotations

from collections import OrderedDict
from dataclasses import dataclass, field
import json
import os
import subprocess
import tempfile
from typing import Any, Callable, Dict, Iterable, List, Mapping, MutableMapping, Optional


def _ensure(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def _normalise_disk_name(device: str, fallback: str = "disk") -> str:
    token = device.strip().replace("/", "-").strip("-")
    return token or fallback


@dataclass
class DiskoPlan:
    """Normalised plan ready to be rendered and executed by Disko."""

    config: Mapping[str, Any]
    mode: str = "destroy,format,mount"
    flags: List[str] = field(default_factory=list)

    def render(self) -> str:
        """Render the configuration to Nix syntax."""

        return _to_nix(self.config) + "\n"

    def command(self, *, nix_bin: str, disko_ref: str, config_path: str) -> List[str]:
        """Assemble the Disko invocation command."""

        cmd = [
            nix_bin,
            "--experimental-features",
            "nix-command flakes",
            "run",
            disko_ref,
            "--",
            "--mode",
            self.mode,
        ]
        cmd.extend(self.flags)
        cmd.append(config_path)
        return cmd


def generate_disko_plan(plan: Mapping[str, Any]) -> DiskoPlan:
    """Generate a :class:`DiskoPlan` from a high-level plan mapping."""

    disks: Iterable[Mapping[str, Any]] = plan.get("disks", [])  # type: ignore[assignment]
    _ensure(disks, "plan requires at least one disk entry")

    devices: MutableMapping[str, Any] = OrderedDict()

    for disk in disks:
        device = disk.get("device")
        _ensure(isinstance(device, str) and device, "disk entry missing 'device'")
        name = disk.get("name") or _normalise_disk_name(device)
        partitions = disk.get("partitions", [])
        _ensure(partitions, f"disk '{name}' requires at least one partition")

        disk_entry: Dict[str, Any] = OrderedDict()
        disk_entry["device"] = device
        disk_entry["type"] = "disk"

        content: Dict[str, Any] = OrderedDict()
        content["type"] = disk.get("scheme", "gpt")
        content["partitions"] = _build_partitions(partitions)
        disk_entry["content"] = content

        devices[name] = disk_entry

    config: MutableMapping[str, Any] = OrderedDict()
    config["disko.devices"] = OrderedDict([("disk", devices)])

    mode = _normalise_mode(plan.get("mode"))
    raw_flags = plan.get("disko_flags", [])
    if isinstance(raw_flags, str):
        raw_flags = [raw_flags]
    flags = list(raw_flags)
    for flag in flags:
        _ensure(isinstance(flag, str), "disko_flags entries must be strings")

    return DiskoPlan(config=config, mode=mode, flags=flags)


def _build_partitions(partitions: Iterable[Mapping[str, Any]]) -> Mapping[str, Any]:
    result: MutableMapping[str, Any] = OrderedDict()
    for partition in partitions:
        name = partition.get("name")
        _ensure(isinstance(name, str) and name, "partition missing 'name'")
        entry: Dict[str, Any] = OrderedDict()

        for key in ("size", "type", "start", "end", "priority", "label"):
            if key in partition:
                entry[key] = partition[key]

        if "content" in partition:
            entry["content"] = partition["content"]
        else:
            filesystem = partition.get("filesystem")
            _ensure(
                isinstance(filesystem, Mapping),
                f"partition '{name}' missing filesystem definition",
            )
            fmt = filesystem.get("format")
            _ensure(isinstance(fmt, str) and fmt, f"partition '{name}' missing filesystem format")
            fs_entry: Dict[str, Any] = OrderedDict()
            fs_entry["type"] = "filesystem"
            fs_entry["format"] = fmt
            for key, value in filesystem.items():
                if key == "format":
                    continue
                fs_entry[key] = value
            entry["content"] = fs_entry

        result[name] = entry
    return result


def _normalise_mode(value: Optional[Any]) -> str:
    if value is None:
        return "destroy,format,mount"
    if isinstance(value, str):
        return value
    if isinstance(value, Iterable):
        parts: List[str] = []
        for mode in value:
            _ensure(isinstance(mode, str), "mode entries must be strings")
            parts.append(mode)
        _ensure(parts, "mode iterable cannot be empty")
        return ",".join(parts)
    raise ValueError("mode must be a string or iterable of strings")


def _to_nix(value: Any, indent: int = 0) -> str:
    pad = " " * indent
    if isinstance(value, Mapping):
        items = []
        items.append("{")
        for key, val in value.items():
            rendered = _to_nix(val, indent + 2)
            if "\n" in rendered:
                rendered = "\n".join(" " * (indent + 2) + line for line in rendered.splitlines())
                items.append(f"{' ' * (indent + 2)}{key} =\n{rendered};")
            else:
                items.append(f"{' ' * (indent + 2)}{key} = {rendered};")
        items.append(f"{pad}" + "}")
        return "\n".join(items)
    if isinstance(value, list):
        if not value:
            return "[ ]"
        inner = [
            " " * (indent + 2) + _to_nix(item, indent + 2)
            for item in value
        ]
        return "[\n" + "\n".join(inner) + f"\n{pad}]"
    if isinstance(value, bool):
        return "true" if value else "false"
    if value is None:
        return "null"
    if isinstance(value, (int, float)):
        return json.dumps(value)
    if isinstance(value, str):
        return json.dumps(value)
    raise TypeError(f"unsupported type for Nix serialisation: {type(value)!r}")


Runner = Callable[[List[str]], None]


class DiskoExecutor:
    """Apply Disko plans by invoking the Disko CLI through nix."""

    def __init__(
        self,
        *,
        runner: Optional[Runner] = None,
        nix_bin: str = "nix",
        disko_ref: str = "github:nix-community/disko/latest",
    ) -> None:
        self._runner = runner or self._default_runner
        self._nix_bin = nix_bin
        self._disko_ref = disko_ref

    @staticmethod
    def _default_runner(cmd: List[str]) -> None:
        subprocess.run(cmd, check=True)

    def apply(self, plan: Mapping[str, Any], *, workdir: Optional[str] = None) -> None:
        disko_plan = generate_disko_plan(plan)
        rendered = disko_plan.render()
        fd: Optional[tempfile.NamedTemporaryFile] = None
        path: Optional[str] = None
        try:
            fd = tempfile.NamedTemporaryFile("w", suffix=".nix", delete=False, dir=workdir)
            fd.write(rendered)
            fd.flush()
            path = fd.name
        finally:
            if fd is not None:
                fd.close()
        assert path is not None
        try:
            cmd = disko_plan.command(nix_bin=self._nix_bin, disko_ref=self._disko_ref, config_path=path)
            self._runner(cmd)
        finally:
            try:
                os.remove(path)
            except OSError:
                pass
