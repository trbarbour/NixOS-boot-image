"""``write-image``: build a pre-nixos image as you, write it as root (R-W1..R-W5).

Examples::

    nix run .#write-image -- --format iso --site ./site --verify
    nix run .#write-image -- --format sd --image result/sd-image/….img.zst --device mmcblk0
    nix run .#write-image -- --list

The build runs as the invoking user.  Only the write runs as root, through
``sudo``, in :mod:`write_image.helper`, which re-checks the device.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from dataclasses import asdict
from pathlib import Path
from typing import Callable, List, Optional, Sequence, TextIO, Tuple

from write_image import devices, image
from write_image.devices import Candidate, Format, Refusal, SystemView

EXIT_OK = 0
EXIT_ERROR = 1
EXIT_REFUSED = 2

ATTRIBUTES = {"iso": "bootImage", "sd": "bootImageSd"}
# The helper runs from this package's own directory (the Nix store, in the
# flake app), never from the invoking user's environment: -I ignores
# PYTHON* variables and the user's site directory.
LIBDIR = str(Path(__file__).resolve().parent.parent)
BOOTSTRAP = (
    "import sys; sys.path.insert(0, {libdir!r}); "
    "from write_image.helper import main; sys.exit(main(sys.argv[1:]))"
)

Runner = Callable[[List[str], bool], Tuple[int, str]]


def _run(cmd: List[str], capture: bool) -> Tuple[int, str]:
    """Run ``cmd``; stderr (build logs, sudo's prompt) stays on the terminal."""

    result = subprocess.run(cmd, stdout=subprocess.PIPE if capture else None, text=True, check=False)
    return result.returncode, result.stdout or ""


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="write-image", description=__doc__.splitlines()[0])
    parser.add_argument("--format", choices=sorted(ATTRIBUTES), default="iso")
    source = parser.add_mutually_exclusive_group()
    source.add_argument("--site", type=Path, help="build the image from this site directory")
    source.add_argument("--image", type=Path, help="write an image that is already built")
    parser.add_argument("--flake", default=".", help="the pre-nixos flake to build (default: .)")
    parser.add_argument("--device", help="whole-disk kernel name, e.g. sdb or mmcblk0")
    parser.add_argument("--verify", action="store_true", help="read the device back and compare SHA-256")
    parser.add_argument("--yes", action="store_true", help="do not ask for the typed confirmation")
    parser.add_argument("--list", action="store_true", help="list eligible and refused devices")
    parser.add_argument("--json", action="store_true", help="with --list: JSON output")
    return parser


def listing(view: SystemView, fmt: Format) -> Tuple[List[Candidate], List[Refusal]]:
    candidates, refusals = devices.scan(view)
    return devices.preferred(candidates, fmt), refusals


def _print_listing(view: SystemView, fmt: Format, as_json: bool, out: TextIO) -> None:
    candidates, refusals = listing(view, fmt)
    if as_json:
        json.dump(
            {"candidates": [asdict(c) for c in candidates], "refusals": [asdict(r) for r in refusals]},
            out,
        )
        out.write("\n")
        return
    for candidate in candidates:
        out.write(f"  {candidate.describe()}\n")
    for refusal in refusals:
        out.write(f"  refused /dev/{refusal.name}: {refusal.reason}\n")


def _choose(view: SystemView, fmt: Format, prompt: Callable[[str], str], out: TextIO) -> Optional[Candidate]:
    candidates, _ = listing(view, fmt)
    if not candidates:
        out.write("no eligible device: insert a USB stick or an SD card (see --list)\n")
        return None
    for number, candidate in enumerate(candidates, 1):
        out.write(f"  {number}) {candidate.describe()}\n")
    answer = prompt("Device number: ").strip()
    if not answer.isdigit() or not 1 <= int(answer) <= len(candidates):
        out.write(f"no device {answer!r}\n")
        return None
    return candidates[int(answer) - 1]


def main(
    argv: Optional[Sequence[str]] = None,
    *,
    run: Runner = _run,
    view: Callable[[], SystemView] = devices.live_view,
    prompt: Callable[[str], str] = input,
    euid: Callable[[], int] = os.geteuid,
    out: TextIO = sys.stdout,
) -> int:
    args = _parser().parse_args(list(argv) if argv is not None else None)
    fmt: Format = args.format
    if args.list:
        _print_listing(view(), fmt, args.json, out)
        return EXIT_OK
    if args.site is None and args.image is None:
        out.write("give --site DIR (build) or --image PATH\n")
        return EXIT_ERROR

    # The device first: nothing is built for a device that would be refused.
    if args.device is not None:
        verdict = devices.check(view(), args.device)
        if isinstance(verdict, Refusal):
            out.write(f"refusing /dev/{verdict.name}: {verdict.reason}\n")
            return EXIT_REFUSED
        target: Candidate = verdict
    else:
        chosen = _choose(view(), fmt, prompt, out)
        if chosen is None:
            return EXIT_REFUSED
        target = chosen

    out.write(f"Target: {target.describe()}\n")
    if not args.yes:
        typed = prompt(f"Everything on {target.path} will be overwritten. Type {target.name} to continue: ")
        if typed.strip() != target.name:
            out.write("not confirmed; nothing written\n")
            return EXIT_REFUSED

    if args.image is not None:
        img = image.image_at(args.image.resolve())
    else:
        site = args.site.resolve()
        status, stdout = run(
            [
                "nix", "build", f"{args.flake}#{ATTRIBUTES[fmt]}", "--no-link", "--print-out-paths",
                "--override-input", "site", f"path:{site}",
            ],
            True,
        )
        lines = [line for line in stdout.splitlines() if line.strip()]
        if status != 0 or not lines:
            out.write(f"the build failed (exit {status}); nothing written\n")
            return EXIT_ERROR
        try:
            img = image.find_image(Path(lines[-1]), fmt)
        except image.ImageNotFound as exc:
            out.write(f"{exc}\n")
            return EXIT_ERROR

    helper_cmd = [
        sys.executable, "-I", "-c", BOOTSTRAP.format(libdir=LIBDIR),
        "--device", target.name, "--image", str(img.path),
    ]
    if args.verify:
        helper_cmd.append("--verify")
    if euid() != 0:
        helper_cmd = ["sudo", "--", *helper_cmd]
    status, _ = run(helper_cmd, False)
    return status


if __name__ == "__main__":
    sys.exit(main())
