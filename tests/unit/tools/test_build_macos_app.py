"""tools/build_macos_app.py: everything that does not need macOS.

The icon, the launcher and the Info.plist are checked as plain values. The build runs with the
system tools (``sips``, ``iconutil``, ``lsregister``, ``killall``) replaced by a recorder, so
nothing is drawn at full size, nothing is installed and the Finder is never touched.
"""

import plistlib
import shlex
import stat
import struct
import sys
import zlib
from collections.abc import Sequence
from pathlib import Path
from types import ModuleType

import pytest

from habit_tracker.ui.theme import palette

APP_DIRECTORY = "Registro de hábitos.app"
PYTHON = "/venv/bin/python"
SMALL_ICON = 32  # the real icon is 1024 px: too slow to draw in a test


class FakeRunner:
    """Records the commands instead of running them; the ones of one program can fail."""

    def __init__(self, error: type[Exception], fail_on: str | None = None) -> None:
        self.error = error
        self.fail_on = fail_on
        self.commands: list[list[str]] = []

    def __call__(self, command: Sequence[str]) -> None:
        self.commands.append(list(command))
        program = Path(command[0]).name
        if program == self.fail_on:
            raise self.error(f"{program} failed (exit code 1): boom")
        if program == "iconutil":
            Path(command[-1]).write_bytes(b"icns")  # the file iconutil would write

    def programs(self) -> list[str]:
        return [Path(command[0]).name for command in self.commands]


def pixel_at(pixels: bytearray, size: int, x: int, y: int) -> tuple[int, ...]:
    start = (y * size + x) * 4
    return tuple(pixels[start : start + 4])


# ================= The launcher and the Info.plist =================


def test_the_launcher_runs_the_package_with_the_given_interpreter(
    build_macos_app: ModuleType,
) -> None:
    lines = build_macos_app.launcher_script(PYTHON).splitlines()
    assert lines[0] == "#!/bin/zsh"
    assert lines[-1] == f"exec {PYTHON} -m habit_tracker"


@pytest.mark.parametrize(
    "python",
    [
        "/Users/jane doe/venv/bin/python",
        '/tmp/with"quote/python',
        "/tmp/it's/python",
        "/tmp/$HOME/python",
        "/tmp/`id`/python",
        "/tmp/a;b&c|d/python",
    ],
    ids=["spaces", "double-quote", "single-quote", "dollar", "backtick", "shell-operators"],
)
def test_the_launcher_escapes_awkward_interpreter_paths(
    build_macos_app: ModuleType, python: str
) -> None:
    command = build_macos_app.launcher_script(python).splitlines()[-1]
    assert shlex.split(command) == ["exec", python, "-m", "habit_tracker"]


def test_a_dollar_sign_and_backticks_stay_inside_single_quotes(
    build_macos_app: ModuleType,
) -> None:
    command = build_macos_app.launcher_script("/tmp/$HOME/`id`/python").splitlines()[-1]
    assert "'/tmp/$HOME/`id`/python'" in command


def test_the_info_plist_has_the_bundle_identifier_and_the_names(
    build_macos_app: ModuleType,
) -> None:
    info = plistlib.loads(build_macos_app.render_info_plist())
    assert info["CFBundleIdentifier"] == "com.habittracker.app"
    assert info["CFBundleName"] == "Registro de hábitos"
    assert info["CFBundleDisplayName"] == "Registro de hábitos"
    assert info["CFBundlePackageType"] == "APPL"
    assert info["CFBundleExecutable"] == build_macos_app.EXECUTABLE
    assert info["CFBundleIconFile"] == build_macos_app.ICON_NAME


def test_the_bundle_is_named_in_spanish(build_macos_app: ModuleType) -> None:
    assert build_macos_app.BUNDLE_NAME == APP_DIRECTORY


def test_only_macos_is_accepted(build_macos_app: ModuleType) -> None:
    build_macos_app.require_macos("darwin")
    for platform in ("linux", "win32"):
        with pytest.raises(build_macos_app.MacAppError, match="macOS"):
            build_macos_app.require_macos(platform)


# ================= The icon =================


def test_hex_colors_become_rgb_triples(build_macos_app: ModuleType) -> None:
    assert build_macos_app.hex_to_rgb("#a98fd0") == (0xA9, 0x8F, 0xD0)
    assert build_macos_app.hex_to_rgb("fffdfb") == (255, 253, 251)


def test_the_icon_takes_its_colors_from_the_theme(build_macos_app: ModuleType) -> None:
    to_rgb = build_macos_app.hex_to_rgb
    assert to_rgb(palette.LILAC) == build_macos_app.ICON_BACKGROUND
    assert to_rgb(palette.PAPER) == build_macos_app.ICON_PETALS
    assert to_rgb(palette.ACCENT_TOTAL) == build_macos_app.ICON_LEAVES


def test_the_icon_has_transparent_corners_a_lilac_square_and_an_amber_heart(
    build_macos_app: ModuleType,
) -> None:
    size = 64
    pixels = build_macos_app.render_icon(size)
    assert len(pixels) == size * size * 4
    assert pixel_at(pixels, size, 0, 0)[3] == 0  # the corner is outside the rounded square
    # On the square, away from the flower and the leaves.
    assert pixel_at(pixels, size, 12, 32) == (*build_macos_app.ICON_BACKGROUND, 255)
    assert pixel_at(pixels, size, 32, 32) == (*build_macos_app.ICON_HEART, 255)  # the heart


def test_a_png_is_written_with_valid_chunks(build_macos_app: ModuleType) -> None:
    width, height = 3, 2
    pixels = bytes(range(width * height * 4))

    data = build_macos_app.encode_png(width, height, pixels)

    assert data.startswith(b"\x89PNG\r\n\x1a\n")
    chunks: dict[bytes, bytes] = {}
    position = 8
    while position < len(data):
        length, kind = struct.unpack(">I4s", data[position : position + 8])
        body = data[position + 8 : position + 8 + length]
        (checksum,) = struct.unpack(">I", data[position + 8 + length : position + 12 + length])
        assert checksum == zlib.crc32(kind + body) & 0xFFFFFFFF
        chunks[kind] = body
        position += 12 + length
    assert struct.unpack(">IIBBBBB", chunks[b"IHDR"]) == (width, height, 8, 6, 0, 0, 0)
    raw = zlib.decompress(chunks[b"IDAT"])
    row_length = 1 + width * 4
    rows = [raw[start : start + row_length] for start in range(0, len(raw), row_length)]
    assert [row[0] for row in rows] == [0, 0]  # no filter on any row
    assert b"".join(row[1:] for row in rows) == pixels
    assert b"IEND" in chunks


def test_the_iconset_has_every_size_at_one_and_two_times(build_macos_app: ModuleType) -> None:
    commands = build_macos_app.iconset_commands(
        Path("/work/master.png"), Path("/work/icon.iconset")
    )
    assert {command[0] for command in commands} == {"sips"}
    pixels_of = {Path(command[-1]).name: command[2] for command in commands}
    assert pixels_of == {
        "icon_16x16.png": "16",
        "icon_16x16@2x.png": "32",
        "icon_32x32.png": "32",
        "icon_32x32@2x.png": "64",
        "icon_128x128.png": "128",
        "icon_128x128@2x.png": "256",
        "icon_256x256.png": "256",
        "icon_256x256@2x.png": "512",
        "icon_512x512.png": "512",
        "icon_512x512@2x.png": "1024",
    }


def test_the_icns_is_made_with_sips_and_then_iconutil(
    build_macos_app: ModuleType, tmp_path: Path
) -> None:
    runner = FakeRunner(build_macos_app.MacAppError)

    icns = build_macos_app.make_icns(tmp_path, runner, size=SMALL_ICON)

    assert runner.programs() == ["sips"] * 10 + ["iconutil"]
    assert runner.commands[-1][:3] == ["iconutil", "-c", "icns"]
    assert icns == tmp_path / "icon.icns"
    assert icns.read_bytes() == b"icns"
    assert (tmp_path / "master.png").read_bytes().startswith(b"\x89PNG")


# ================= Calls to the system =================


def test_a_successful_command_returns_quietly(build_macos_app: ModuleType) -> None:
    assert build_macos_app.run_checked([sys.executable, "-c", "pass"]) is None


def test_a_failing_command_is_reported_with_what_it_said(build_macos_app: ModuleType) -> None:
    command = [sys.executable, "-c", "import sys; sys.stderr.write('not good'); sys.exit(3)"]
    with pytest.raises(build_macos_app.MacAppError, match="not good") as raised:
        build_macos_app.run_checked(command)
    assert "exit code 3" in str(raised.value)


def test_a_program_that_is_not_there_is_reported_by_name(build_macos_app: ModuleType) -> None:
    with pytest.raises(build_macos_app.MacAppError, match="could not run no-such-tool"):
        build_macos_app.run_checked(["/nowhere/no-such-tool"])


# ================= The build =================


def test_the_bundle_has_the_plist_the_launcher_and_the_icon(
    build_macos_app: ModuleType, tmp_path: Path
) -> None:
    runner = FakeRunner(build_macos_app.MacAppError)

    result = build_macos_app.build_app(tmp_path, python=PYTHON, run=runner, icon_size=SMALL_ICON)

    app = tmp_path / APP_DIRECTORY
    contents = app / "Contents"
    assert result.app == app
    assert result.warnings == ()
    info = plistlib.loads((contents / "Info.plist").read_bytes())
    assert info["CFBundleIdentifier"] == "com.habittracker.app"
    launcher = contents / "MacOS" / "launcher"
    assert (
        launcher.read_text(encoding="utf-8").splitlines()[-1] == f"exec {PYTHON} -m habit_tracker"
    )
    assert stat.S_IMODE(launcher.stat().st_mode) == 0o755  # a double click needs it executable
    assert (contents / "Resources" / "icon.icns").read_bytes() == b"icns"


def test_the_finder_is_left_alone_unless_asked(
    build_macos_app: ModuleType, tmp_path: Path
) -> None:
    runner = FakeRunner(build_macos_app.MacAppError)
    build_macos_app.build_app(tmp_path, python=PYTHON, run=runner, icon_size=SMALL_ICON)
    assert "killall" not in runner.programs()
    assert runner.programs()[-1] == "lsregister"


def test_the_finder_is_restarted_when_asked(build_macos_app: ModuleType, tmp_path: Path) -> None:
    runner = FakeRunner(build_macos_app.MacAppError)
    build_macos_app.build_app(
        tmp_path, python=PYTHON, run=runner, icon_size=SMALL_ICON, restart_finder=True
    )
    assert runner.commands[-1] == ["killall", "Finder"]


@pytest.mark.parametrize("program", ["sips", "iconutil"])
def test_a_failing_icon_tool_stops_the_build_and_leaves_the_destination_alone(
    build_macos_app: ModuleType, tmp_path: Path, program: str
) -> None:
    runner = FakeRunner(build_macos_app.MacAppError, fail_on=program)
    with pytest.raises(build_macos_app.MacAppError, match=f"{program} failed"):
        build_macos_app.build_app(tmp_path, python=PYTHON, run=runner, icon_size=SMALL_ICON)
    assert not (tmp_path / APP_DIRECTORY).exists()


def test_a_failing_lsregister_is_a_warning_and_not_an_error(
    build_macos_app: ModuleType, tmp_path: Path
) -> None:
    runner = FakeRunner(build_macos_app.MacAppError, fail_on="lsregister")

    result = build_macos_app.build_app(tmp_path, python=PYTHON, run=runner, icon_size=SMALL_ICON)

    assert result.app.exists()
    assert len(result.warnings) == 1
    assert "lsregister failed" in result.warnings[0]


def test_the_output_folder_must_exist(build_macos_app: ModuleType, tmp_path: Path) -> None:
    runner = FakeRunner(build_macos_app.MacAppError)
    with pytest.raises(build_macos_app.MacAppError, match="does not exist"):
        build_macos_app.build_app(tmp_path / "nowhere", python=PYTHON, run=runner)
    assert runner.commands == []


def test_an_unknown_interpreter_is_refused(build_macos_app: ModuleType, tmp_path: Path) -> None:
    runner = FakeRunner(build_macos_app.MacAppError)
    with pytest.raises(build_macos_app.MacAppError, match="interpreter"):
        build_macos_app.build_app(tmp_path, python="", run=runner)
    assert runner.commands == []


# ================= Command line =================


def test_the_options_default_to_the_desktop_and_no_finder_restart(
    build_macos_app: ModuleType,
) -> None:
    args = build_macos_app.build_parser().parse_args([])
    assert args.output == Path.home() / "Desktop"
    assert args.refresh_finder is False


def test_the_help_explains_what_refreshing_the_finder_does(
    build_macos_app: ModuleType, capsys: pytest.CaptureFixture[str]
) -> None:
    with pytest.raises(SystemExit) as raised:
        build_macos_app.build_parser().parse_args(["--help"])
    assert raised.value.code == 0
    text = " ".join(capsys.readouterr().out.split())
    assert "--output" in text
    assert "--refresh-finder" in text
    assert "restart the Finder" in text


def test_the_tool_refuses_to_run_outside_macos(
    build_macos_app: ModuleType,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setattr(sys, "platform", "linux")
    assert build_macos_app.main(["--output", str(tmp_path)]) == 1
    assert "macOS" in capsys.readouterr().err
    assert list(tmp_path.iterdir()) == []


def test_a_missing_output_folder_is_reported(
    build_macos_app: ModuleType,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setattr(sys, "platform", "darwin")
    assert build_macos_app.main(["--output", str(tmp_path / "nowhere")]) == 1
    assert "does not exist" in capsys.readouterr().err


def test_main_builds_with_the_running_interpreter_and_reports_the_warnings(
    build_macos_app: ModuleType,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    calls: list[tuple[Path, dict[str, object]]] = []

    def fake_build(output_dir: Path, **options: object) -> object:
        calls.append((output_dir, options))
        return build_macos_app.BuildResult(output_dir / "app", ("careful",))

    monkeypatch.setattr(sys, "platform", "darwin")
    monkeypatch.setattr(build_macos_app, "build_app", fake_build)

    assert build_macos_app.main(["--output", str(tmp_path), "--refresh-finder"]) == 0

    output_dir, options = calls[0]
    assert output_dir == tmp_path
    assert options["python"] == sys.executable
    assert options["restart_finder"] is True
    captured = capsys.readouterr()
    assert "warning: careful" in captured.err
    assert "Created:" in captured.out
