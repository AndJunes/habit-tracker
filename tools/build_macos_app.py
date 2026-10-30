"""Build the macOS app bundle that opens Habit Tracker with a double click.

    python tools/build_macos_app.py [--output DIR] [--refresh-finder]

Creates ``Registro de hábitos.app`` in the output folder (default: the Desktop):

    Registro de hábitos.app/
      Contents/
        Info.plist             bundle identifier, name and icon
        MacOS/launcher         runs "python -m habit_tracker" with the interpreter that built it
        Resources/icon.icns    drawn by this script, scaled with sips and packed with iconutil

The launcher stores the path of the interpreter, so build the app again if the virtual
environment or the interpreter moves. Only the standard library, ``sips`` and ``iconutil`` are
needed; the colors of the icon come from the theme of the app.
"""

import argparse
import math
import os
import plistlib
import shlex
import shutil
import struct
import subprocess
import sys
import tempfile
import zlib
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path

from habit_tracker.ui.theme import palette

type Color = tuple[int, int, int]
type CommandRunner = Callable[[Sequence[str]], None]

APP_NAME = "Registro de hábitos"
BUNDLE_NAME = f"{APP_NAME}.app"
BUNDLE_ID = "com.habittracker.app"
BUNDLE_VERSION = "1.0"
EXECUTABLE = "launcher"
ICON_NAME = "icon"
PACKAGE = "habit_tracker"

ICON_SIZE = 1024
ICONSET_SIZES = (16, 32, 128, 256, 512)  # each one also at 2x, for retina screens
LSREGISTER = (
    "/System/Library/Frameworks/CoreServices.framework/Frameworks"
    "/LaunchServices.framework/Support/lsregister"
)
PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"


def hex_to_rgb(value: str) -> Color:
    """``"#a98fd0"`` as ``(169, 143, 208)``."""
    digits = value.lstrip("#")
    return int(digits[0:2], 16), int(digits[2:4], 16), int(digits[4:6], 16)


# The icon: a daisy on a rounded lilac square. The amber of its heart is the only color that
# the theme does not have.
ICON_BACKGROUND = hex_to_rgb(palette.LILAC)
ICON_PETALS = hex_to_rgb(palette.PAPER)
ICON_LEAVES = hex_to_rgb(palette.ACCENT_TOTAL)
ICON_HEART: Color = (0xE6, 0xBF, 0x63)


class MacAppError(Exception):
    """Something that stops the build, worded for the person running the tool."""


# ---------- The icon (pure) ----------


def encode_png(width: int, height: int, pixels: bytes | bytearray) -> bytes:
    """A minimal RGBA PNG: a signature and a few CRC-protected chunks."""

    def chunk(kind: bytes, data: bytes) -> bytes:
        checksum = zlib.crc32(kind + data) & 0xFFFFFFFF
        return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", checksum)

    header = struct.pack(">IIBBBBB", width, height, 8, 6, 0, 0, 0)
    stride = width * 4
    # Every row of pixels is preceded by a filter byte (0 = none).
    raw = b"".join(
        b"\x00" + bytes(pixels[row * stride : (row + 1) * stride]) for row in range(height)
    )
    return (
        PNG_SIGNATURE
        + chunk(b"IHDR", header)
        + chunk(b"IDAT", zlib.compress(raw, 9))
        + chunk(b"IEND", b"")
    )


def render_icon(size: int = ICON_SIZE) -> bytearray:
    """The RGBA pixels of the icon, row by row.

    Every shape is painted with a soft 2 px edge (a ramp of transparency) so that the borders
    are not jagged.
    """
    center = size / 2
    margin = size * 0.06  # air around the square
    corner_radius = size * 0.22  # macOS-style corners
    flower_y = center + size * 0.02
    petal_radius = size * 0.130
    petal_orbit = size * 0.165  # how far from the center the petals sit
    heart_radius = size * 0.105
    softness = 2.0  # pixels of soft edge

    # Six petals around the heart, the first one pointing up.
    petals = []
    for index in range(6):
        angle = math.radians(index * 60 - 90)
        petals.append(
            (center + petal_orbit * math.cos(angle), flower_y + petal_orbit * math.sin(angle))
        )
    # Two small leaves peeking out below, on both sides of the stem.
    leaves = [
        (center - size * 0.21, flower_y + size * 0.21, size * 0.075),
        (center + size * 0.21, flower_y + size * 0.21, size * 0.075),
    ]

    def circle_coverage(x: float, y: float, cx: float, cy: float, radius: float) -> float:
        """1 inside, 0 outside and a short ramp right on the edge."""
        distance = math.hypot(x - cx, y - cy)
        return max(0.0, min(1.0, (radius - distance) / softness + 0.5))

    def square_coverage(x: float, y: float) -> float:
        """Distance to the inner rectangle of the rounded square."""
        inner = center - margin - corner_radius
        dx = max(abs(x - center) - inner, 0.0)
        dy = max(abs(y - center) - inner, 0.0)
        distance = math.hypot(dx, dy)
        return max(0.0, min(1.0, (corner_radius - distance) / softness + 0.5))

    def blend(base: Color, over: Color, amount: float) -> Color:
        return (
            round(base[0] + (over[0] - base[0]) * amount),
            round(base[1] + (over[1] - base[1]) * amount),
            round(base[2] + (over[2] - base[2]) * amount),
        )

    pixels = bytearray(size * size * 4)
    for y in range(size):
        for x in range(size):
            alpha = square_coverage(x, y)
            if alpha <= 0:
                continue  # outside the square: transparent
            color = ICON_BACKGROUND
            for leaf_x, leaf_y, leaf_radius in leaves:  # under the petals
                amount = circle_coverage(x, y, leaf_x, leaf_y, leaf_radius)
                if amount > 0:
                    color = blend(color, ICON_LEAVES, amount)
            for petal_x, petal_y in petals:
                amount = circle_coverage(x, y, petal_x, petal_y, petal_radius)
                if amount > 0:
                    color = blend(color, ICON_PETALS, amount)
            amount = circle_coverage(x, y, center, flower_y, heart_radius)  # over everything
            if amount > 0:
                color = blend(color, ICON_HEART, amount)
            position = (y * size + x) * 4
            pixels[position : position + 4] = bytes((*color, round(255 * alpha)))
    return pixels


def iconset_commands(master: Path, iconset: Path) -> list[list[str]]:
    """The ``sips`` calls that scale the master image to every size macOS asks for."""
    commands = []
    for size in ICONSET_SIZES:
        for factor, suffix in ((1, ""), (2, "@2x")):
            pixels = size * factor
            target = iconset / f"icon_{size}x{size}{suffix}.png"
            commands.append(
                ["sips", "-z", str(pixels), str(pixels), str(master), "--out", str(target)]
            )
    return commands


# ---------- The bundle (pure) ----------


def info_plist() -> dict[str, str]:
    """The contents of ``Info.plist``."""
    return {
        "CFBundleName": APP_NAME,
        "CFBundleDisplayName": APP_NAME,
        "CFBundleIdentifier": BUNDLE_ID,
        "CFBundleVersion": BUNDLE_VERSION,
        "CFBundlePackageType": "APPL",
        "CFBundleExecutable": EXECUTABLE,
        "CFBundleIconFile": ICON_NAME,
    }


def render_info_plist() -> bytes:
    return plistlib.dumps(info_plist(), fmt=plistlib.FMT_XML)


def launcher_script(python: str) -> str:
    """The shell script that starts the app with the given interpreter.

    The path goes through ``shlex.quote``: spaces, quotes, ``$`` and backticks in it must not
    reach the shell as syntax.
    """
    return (
        "#!/bin/zsh\n"
        "# Launcher of Registro de hábitos, generated by tools/build_macos_app.py.\n"
        "# Build the app again if the interpreter or the project moves.\n"
        f"exec {shlex.quote(python)} -m {PACKAGE}\n"
    )


def require_macos(platform: str) -> None:
    """The bundle, ``sips`` and ``iconutil`` only exist on macOS."""
    if platform != "darwin":
        raise MacAppError("this tool builds a macOS app bundle and only works on macOS")


# ---------- Calls to the system ----------


def run_checked(command: Sequence[str]) -> None:
    """Run a command; a failure raises an error that carries what the command said."""
    program = Path(command[0]).name
    try:
        result = subprocess.run(command, capture_output=True, text=True, check=False)
    except OSError as error:
        raise MacAppError(f"could not run {program}: {error}") from error
    if result.returncode != 0:
        detail = (result.stderr or result.stdout).strip() or "no output"
        raise MacAppError(f"{program} failed (exit code {result.returncode}): {detail}")


def make_icns(work_dir: Path, run: CommandRunner, *, size: int = ICON_SIZE) -> Path:
    """Draw the icon in ``work_dir`` and pack it as an ``.icns`` file; returns its path."""
    master = work_dir / "master.png"
    master.write_bytes(encode_png(size, size, render_icon(size)))
    iconset = work_dir / f"{ICON_NAME}.iconset"
    iconset.mkdir()
    for command in iconset_commands(master, iconset):
        run(command)
    icns = work_dir / f"{ICON_NAME}.icns"
    run(["iconutil", "-c", "icns", str(iconset), "-o", str(icns)])
    return icns


def write_bundle(app: Path, *, python: str, icns: Path) -> None:
    """Write the files of the bundle: ``Info.plist``, the launcher and the icon."""
    contents = app / "Contents"
    (contents / "MacOS").mkdir(parents=True, exist_ok=True)
    (contents / "Resources").mkdir(parents=True, exist_ok=True)
    (contents / "Info.plist").write_bytes(render_info_plist())
    launcher = contents / "MacOS" / EXECUTABLE
    launcher.write_text(launcher_script(python), encoding="utf-8")
    launcher.chmod(0o755)  # without the execute permission a double click does nothing
    shutil.copyfile(icns, contents / "Resources" / f"{ICON_NAME}.icns")


def refresh_icon_cache(app: Path, run: CommandRunner, *, restart_finder: bool) -> list[str]:
    """Ask the system to forget the icon it has cached for the bundle; returns the warnings.

    A freshly built app often shows the generic icon: touching it and registering it again
    with Launch Services fixes most cases. Restarting the Finder (it flashes for a second)
    is a last resort and only happens when asked for.
    """
    os.utime(app)
    commands = [[LSREGISTER, "-f", str(app)]]
    if restart_finder:
        commands.append(["killall", "Finder"])
    warnings = []
    for command in commands:
        try:
            run(command)
        except MacAppError as error:
            warnings.append(str(error))
    return warnings


@dataclass(frozen=True, slots=True)
class BuildResult:
    app: Path
    warnings: tuple[str, ...]


def _ignore(message: str) -> None:
    """The default progress report: say nothing."""


def build_app(
    output_dir: Path,
    *,
    python: str,
    run: CommandRunner = run_checked,
    restart_finder: bool = False,
    icon_size: int = ICON_SIZE,
    progress: Callable[[str], object] = _ignore,
) -> BuildResult:
    """Create ``Registro de hábitos.app`` in ``output_dir``.

    ``python`` is the interpreter the launcher will use. The icon is made before anything is
    written to the destination, so a failure of ``sips`` or ``iconutil`` leaves it untouched.
    """
    if not python:
        raise MacAppError("cannot tell which Python interpreter is running")
    if not output_dir.is_dir():
        raise MacAppError(f"the output folder does not exist: {output_dir}")
    app = output_dir / BUNDLE_NAME
    with tempfile.TemporaryDirectory() as work:
        progress("Drawing the icon (a few seconds)...")
        icns = make_icns(Path(work), run, size=icon_size)
        progress(f"Writing {app}...")
        write_bundle(app, python=python, icns=icns)
    warnings = refresh_icon_cache(app, run, restart_finder=restart_finder)
    return BuildResult(app, tuple(warnings))


# ---------- Command line ----------


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="build_macos_app.py",
        description=(
            f"Build '{BUNDLE_NAME}', a macOS app that opens Habit Tracker with a double click. "
            "The launcher runs 'python -m habit_tracker' with the interpreter used here."
        ),
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path.home() / "Desktop",
        metavar="DIR",
        help="folder where the app is created (default: %(default)s)",
    )
    parser.add_argument(
        "--refresh-finder",
        action="store_true",
        help=(
            "also restart the Finder (it flashes for a second) so that it drops the icon it "
            "has cached for the app; only needed when the app shows a generic icon"
        ),
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        require_macos(sys.platform)
        result = build_app(
            args.output,
            python=sys.executable,
            restart_finder=args.refresh_finder,
            progress=lambda message: print(message, flush=True),
        )
    except (MacAppError, OSError) as error:
        print(f"build_macos_app: {error}", file=sys.stderr)
        return 1
    for warning in result.warnings:
        print(f"warning: {warning}", file=sys.stderr)
    print(f"\nCreated: {result.app}")
    print("Double-click it to open the app; it can also be dragged to the Dock.")
    print(f"It runs {sys.executable} -m {PACKAGE}: build it again if that interpreter moves.")
    if not args.refresh_finder:
        print("If the Finder still shows a generic icon, run again with --refresh-finder.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
