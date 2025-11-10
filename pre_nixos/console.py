"""Console broadcasting utilities."""

from __future__ import annotations

import argparse
import os
from pathlib import Path
from typing import Iterable, Sequence, Tuple

_DEFAULT_ACTIVE_PATH = Path("/sys/class/tty/console/active")
_DEFAULT_FALLBACK = Path("/dev/console")


def _normalize_path(path: Path) -> Path:
    """Return a normalized absolute console ``path``."""

    resolved = Path(path)
    if not resolved.is_absolute():
        resolved = Path("/dev") / resolved
    return resolved


def get_console_paths(
    active_path: Path = _DEFAULT_ACTIVE_PATH,
    *,
    extra_paths: Iterable[Path] | None = None,
) -> list[Path]:
    """Return the ordered set of active console device paths.

    Args:
        active_path: Path to ``/sys/class/tty/console/active`` (override in tests).
        extra_paths: Optional iterable of additional console paths to include.

    Returns:
        List of distinct console device paths.  The ``/dev/console`` fallback is
        appended when not already present.
    """

    paths: list[Path] = []

    try:
        contents = active_path.read_text(encoding="utf-8", errors="ignore")
    except FileNotFoundError:
        contents = ""
    except OSError:
        contents = ""

    for token in contents.split():
        normalized = _normalize_path(Path(token.strip()))
        if normalized not in paths:
            paths.append(normalized)

    if extra_paths is not None:
        for candidate in extra_paths:
            normalized = _normalize_path(Path(candidate))
            if normalized not in paths:
                paths.append(normalized)

    if _DEFAULT_FALLBACK not in paths:
        paths.append(_DEFAULT_FALLBACK)

    return paths


def broadcast_line(
    message: str,
    *,
    active_path: Path = _DEFAULT_ACTIVE_PATH,
    console_paths: Sequence[Path] | None = None,
) -> dict[Path, bool]:
    """Write ``message`` to each console and return per-device success."""

    if console_paths is None:
        targets = get_console_paths(active_path)
    else:
        seen: list[Path] = []
        for candidate in console_paths:
            normalized = _normalize_path(Path(candidate))
            if normalized not in seen:
                seen.append(normalized)
        targets = seen or get_console_paths(active_path)

    results: dict[Path, bool] = {}
    for device in targets:
        try:
            with device.open("w", buffering=1, encoding="utf-8") as handle:
                handle.write(message + "\r\n")
                handle.flush()
            results[device] = True
        except OSError:
            results[device] = False

    return results


def broadcast_to_consoles(
    message: str,
    *,
    active_path: Path = _DEFAULT_ACTIVE_PATH,
    console_paths: Sequence[Path] | None = None,
    execute: bool | None = None,
) -> Tuple[bool, list[Path], dict[Path, bool]]:
    """Broadcast ``message`` when execution is enabled.

    Args:
        message: Text to announce on each console.
        active_path: Location of the kernel console list.
        console_paths: Optional explicit console targets.
        execute: Override for the ``PRE_NIXOS_EXEC`` environment flag.  When
            ``None`` the environment variable is consulted.

    Returns:
        Tuple containing:

        * ``bool`` indicating if any console write succeeded.
        * ``list`` of console device paths that were targeted.
        * ``dict`` mapping targeted console paths to their success results.

        When execution is disabled, ``False`` and empty collections are
        returned without performing any broadcast.
    """

    if execute is None:
        execute = os.environ.get("PRE_NIXOS_EXEC") == "1"

    if not execute:
        return False, [], {}

    results = broadcast_line(
        message,
        active_path=active_path,
        console_paths=console_paths,
    )
    targets = list(results.keys())
    return any(results.values()), targets, results


def _broadcast_cli(args: argparse.Namespace) -> int:
    message = " ".join(args.message)
    results = broadcast_line(message, active_path=args.active_path)
    if any(results.values()):
        return 0
    return 1


def main(argv: Sequence[str] | None = None) -> int:
    """Entry point for ``python -m pre_nixos.console``."""

    parser = argparse.ArgumentParser(description="pre-nixos console utilities")
    subparsers = parser.add_subparsers(dest="command", required=True)

    broadcast_parser = subparsers.add_parser("broadcast", help="broadcast a line to consoles")
    broadcast_parser.add_argument("message", nargs="+", help="Message to broadcast")
    broadcast_parser.add_argument(
        "--active-path",
        type=Path,
        default=_DEFAULT_ACTIVE_PATH,
        help="Path to the kernel console list",
    )
    broadcast_parser.set_defaults(func=_broadcast_cli)

    parsed = parser.parse_args(argv)
    return parsed.func(parsed)


if __name__ == "__main__":  # pragma: no cover - CLI entry point
    raise SystemExit(main())
