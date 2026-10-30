"""The parts of tools/capture_screens.py that need no window.

Judging screenshots, finding them in a folder, building the GIF and the command line. The
tests that need Pillow are skipped, with the reason visible, when it is not installed. Nothing
here touches the real ``docs/img`` folder or opens a window.
"""

import os
import re
import sys
import tkinter
from datetime import date
from pathlib import Path
from types import ModuleType

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
SINCE = 1_000.0  # seconds since the epoch: older files are not new captures
NEW = 2_000.0
LILAC = (200, 180, 230, 255)


class ForbiddenWindow:
    """Stands in for ``tkinter.Tk`` in tests that must not open any window."""

    def __init__(self, *args: object, **kwargs: object) -> None:
        raise AssertionError("a window was opened")


def write_capture(path: Path, size: int = 10, modified: float = NEW) -> Path:
    """A file of ``size`` bytes with the given modification time."""
    path.write_bytes(b"x" * size)
    os.utime(path, (modified, modified))
    return path


# ================= Judging screenshots =================


def test_a_full_screen_capture_is_told_apart_from_a_window_capture(
    capture_screens: ModuleType,
) -> None:
    screen = (1512, 982)  # points; the captures come out at twice that
    assert capture_screens.is_fullscreen_capture((3024, 1964), screen)
    assert not capture_screens.is_fullscreen_capture((1232, 1650), screen)  # the app window
    # The dashboard is as wide as the screen but not as tall.
    assert not capture_screens.is_fullscreen_capture((3024, 1744), screen)


def test_the_shape_of_a_capture_tells_the_main_window_from_the_form(
    capture_screens: ModuleType,
) -> None:
    main_window, form = (620, 800), (464, 780)
    assert capture_screens.matches_window_shape((1232, 1650), main_window)
    assert capture_screens.matches_window_shape((928, 1624), form)
    assert not capture_screens.matches_window_shape((928, 1624), main_window)
    assert not capture_screens.matches_window_shape((1232, 1650), form)


@pytest.mark.parametrize(
    ("size", "expected"),
    [
        ((3024, 1964), "fullscreen"),
        ((928, 1624), "wrong-shape"),
        ((1232, 1650), None),
    ],
)
def test_a_capture_that_does_not_fit_is_told_why(
    capture_screens: ModuleType, size: tuple[int, int], expected: str | None
) -> None:
    problem = capture_screens.check_capture(size, (1512, 982), (620, 800))
    assert problem == expected


@pytest.mark.parametrize(
    ("name", "expected"),
    [
        ("Captura de pantalla 2026-10-29 a la(s) 9.10.37 pm.png", True),
        ("Screenshot 2026-10-29 at 9.10.37 PM.png", True),
        ("SCREENSHOT 2026-10-29.PNG", True),
        ("foto.png", False),
        ("Captura de pantalla 2026.jpg", False),
        ("notas sobre una captura.png", False),
    ],
)
def test_macos_screenshot_names_are_recognised(
    capture_screens: ModuleType, name: str, expected: bool
) -> None:
    assert capture_screens.is_screenshot_name(name) is expected


# ================= Finding the new screenshot =================


def test_the_watcher_ignores_old_files_and_files_that_are_not_screenshots(
    capture_screens: ModuleType, tmp_path: Path
) -> None:
    write_capture(tmp_path / "Captura de pantalla vieja.png", modified=500.0)
    write_capture(tmp_path / "foto cualquiera.png")
    watcher = capture_screens.CaptureWatcher(tmp_path, SINCE)
    assert watcher.poll() is None
    assert watcher.poll() is None


def test_the_watcher_returns_a_new_screenshot_once_its_size_is_stable(
    capture_screens: ModuleType, tmp_path: Path
) -> None:
    watcher = capture_screens.CaptureWatcher(tmp_path, SINCE)
    assert watcher.poll() is None  # nothing there yet
    new = write_capture(tmp_path / "Captura de pantalla nueva.png")
    assert watcher.poll() is None  # first sight: the size is noted
    assert watcher.poll() == new  # the same size twice: the file is complete
    assert watcher.poll() is None  # each screenshot is returned once


def test_the_watcher_waits_while_the_file_is_still_growing(
    capture_screens: ModuleType, tmp_path: Path
) -> None:
    watcher = capture_screens.CaptureWatcher(tmp_path, SINCE)
    path = write_capture(tmp_path / "Screenshot 2026-10-29 at 9.10.37 PM.png", size=10)
    assert watcher.poll() is None
    path.write_bytes(b"x" * 25)  # macOS is still writing it
    assert watcher.poll() is None
    assert watcher.poll() == path


def test_the_watcher_never_returns_an_empty_file(
    capture_screens: ModuleType, tmp_path: Path
) -> None:
    write_capture(tmp_path / "Captura de pantalla vacía.png", size=0)
    watcher = capture_screens.CaptureWatcher(tmp_path, SINCE)
    for _ in range(3):
        assert watcher.poll() is None


# ================= The GIF =================


def test_the_gif_has_one_frame_per_capture_and_loops(
    capture_screens: ModuleType, tmp_path: Path
) -> None:
    pil_image = pytest.importorskip("PIL.Image")
    frames = []
    for number, size in enumerate([(1232, 1650), (928, 1624), (1232, 1650)]):
        path = tmp_path / f"frame{number}.png"
        pil_image.new("RGBA", size, LILAC).save(path)
        frames.append(path)
    destination = tmp_path / "demo.gif"

    assert capture_screens.compose_gif(frames, destination) == 3

    with pil_image.open(destination) as gif:
        assert gif.n_frames == 3
        assert gif.size == (760, 940)
        assert gif.info.get("loop") == 0
        assert gif.info.get("duration") == 1800


def test_a_gif_needs_at_least_one_frame(capture_screens: ModuleType, tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="at least one frame"):
        capture_screens.compose_gif([], tmp_path / "demo.gif")


def test_the_missing_frames_are_listed_in_the_order_of_the_gif(
    capture_screens: ModuleType, tmp_path: Path
) -> None:
    every_frame = [f"{name}.png" for name in capture_screens.GIF_FRAMES]
    assert capture_screens.missing_frames(tmp_path) == every_frame
    (tmp_path / "hoy.png").write_bytes(b"")
    (tmp_path / "eliminar.png").write_bytes(b"")
    assert capture_screens.missing_frames(tmp_path) == [
        "marcado.png",
        "formulario.png",
        "formulario-fechas.png",
        "formulario-final.png",
        "calendario.png",
        "mi-mes.png",
    ]


def test_rebuilding_the_gif_says_which_frames_are_missing(
    capture_screens: ModuleType, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert capture_screens.rebuild_gif(tmp_path) is False
    error = capsys.readouterr().err
    assert "missing" in error
    assert "hoy.png" in error
    assert not (tmp_path / "demo.gif").exists()


def test_rebuilding_the_gif_builds_it_from_the_saved_frames(
    capture_screens: ModuleType, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    pil_image = pytest.importorskip("PIL.Image")
    for name in capture_screens.GIF_FRAMES:
        pil_image.new("RGBA", (1232, 1650), LILAC).save(tmp_path / f"{name}.png")

    assert capture_screens.rebuild_gif(tmp_path) is True

    assert (tmp_path / "demo.gif").exists()
    assert "8 frames" in capsys.readouterr().out


# ================= The scenes and the README =================


def test_the_scenes_have_unique_names_and_a_text_each(capture_screens: ModuleType) -> None:
    assert len(set(capture_screens.SCENES)) == len(capture_screens.SCENES)
    assert set(capture_screens.SCENE_TEXTS) == set(capture_screens.SCENES)


def test_the_gif_frames_are_scenes_shown_in_the_same_order(capture_screens: ModuleType) -> None:
    positions = [capture_screens.SCENES.index(name) for name in capture_screens.GIF_FRAMES]
    assert positions == sorted(positions)


@pytest.mark.parametrize("readme", ["README.md", "README.es.md"])
def test_every_image_a_readme_cites_is_produced_by_the_tool(
    capture_screens: ModuleType, readme: str
) -> None:
    text = (REPO_ROOT / readme).read_text(encoding="utf-8")
    cited = set(re.findall(r'src="(docs/img/[^"]+)"', text))
    produced = {f"docs/img/{name}.png" for name in capture_screens.SCENES}
    produced.add(f"docs/img/{capture_screens.GIF_NAME}")
    assert cited, f"{readme} cites no image from docs/img"
    assert cited <= produced, (
        f"{readme} cites images the tool does not produce: {cited - produced}"
    )


def test_the_instructions_name_the_scene_the_window_and_the_file(
    capture_screens: ModuleType,
) -> None:
    scene = capture_screens.Scene(
        "hoy", "La vista Hoy", "la ventana «Registro de hábitos»", lambda: None
    )
    text = capture_screens.capture_instructions(1, 10, scene, "docs/img/hoy.png")
    assert "[1/10] La vista Hoy" in text
    assert "la ventana «Registro de hábitos»" in text
    assert "docs/img/hoy.png" in text


def test_the_capture_clock_stops_at_ten_in_the_morning_of_today(
    capture_screens: ModuleType,
) -> None:
    now = capture_screens.capture_clock().now()
    assert now.date() == date.today()
    assert (now.hour, now.minute, now.second) == (10, 0, 0)


# ================= Finding the window to capture =================

CONTENT = (40, 92, 620, 800)  # left, top, width, height of a Tk window's content, in points


def macos_window(window_id: int, x: float, y: float, w: float, h: float) -> dict[str, float]:
    return {"id": window_id, "x": x, "y": y, "w": w, "h": h}


def test_the_window_is_found_by_its_content_area_and_includes_the_title_bar(
    capture_screens: ModuleType,
) -> None:
    windows = [macos_window(7, 40, 60, 620, 832)]  # starts above the content: the title bar
    assert capture_screens.find_window_id(windows, *CONTENT) == 7


def test_a_window_of_another_width_or_place_is_not_the_one(capture_screens: ModuleType) -> None:
    windows = [
        macos_window(1, 40, 60, 700, 832),  # wider
        macos_window(2, 400, 60, 620, 832),  # elsewhere
        macos_window(3, 40, 60, 620, 200),  # ends well above the bottom of the content
    ]
    assert capture_screens.find_window_id(windows, *CONTENT) is None


def test_when_several_windows_fit_the_smallest_one_wins(capture_screens: ModuleType) -> None:
    windows = [macos_window(1, 40, 20, 620, 900), macos_window(2, 40, 60, 620, 832)]
    assert capture_screens.find_window_id(windows, *CONTENT) == 2


def test_no_windows_means_no_match(capture_screens: ModuleType) -> None:
    assert capture_screens.find_window_id([], *CONTENT) is None


def test_a_difference_of_a_few_points_is_tolerated(capture_screens: ModuleType) -> None:
    windows = [macos_window(5, 41, 61, 619, 832)]
    assert capture_screens.find_window_id(windows, *CONTENT) == 5


# ================= Command line =================


def test_the_options_default_to_the_repository_images_and_the_desktop(
    capture_screens: ModuleType,
) -> None:
    args = capture_screens.build_parser().parse_args([])
    assert args.output == REPO_ROOT / "docs" / "img"
    assert args.captures_dir == Path.home() / "Desktop"
    assert args.rebuild_gif is False
    assert args.no_validate is False
    assert args.auto is False


def test_auto_asks_the_script_to_capture_the_windows_by_itself(
    capture_screens: ModuleType,
) -> None:
    assert capture_screens.build_parser().parse_args(["--auto"]).auto is True


def test_the_help_describes_every_option(
    capture_screens: ModuleType, capsys: pytest.CaptureFixture[str]
) -> None:
    with pytest.raises(SystemExit) as raised:
        capture_screens.build_parser().parse_args(["--help"])
    assert raised.value.code == 0
    text = capsys.readouterr().out
    for option in ("--output", "--captures-dir", "--auto", "--rebuild-gif", "--no-validate"):
        assert option in text


def test_taking_screenshots_is_refused_outside_macos_without_opening_a_window(
    capture_screens: ModuleType,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setattr(sys, "platform", "linux")
    monkeypatch.setattr(tkinter, "Tk", ForbiddenWindow)
    arguments = ["--output", str(tmp_path / "img"), "--captures-dir", str(tmp_path)]
    assert capture_screens.main(arguments) == 1
    assert "macOS" in capsys.readouterr().err
    assert not (tmp_path / "img").exists()


def test_a_missing_pillow_is_reported_without_a_traceback(
    capture_screens: ModuleType,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setitem(sys.modules, "PIL", None)
    monkeypatch.setitem(sys.modules, "PIL.Image", None)
    assert capture_screens.main(["--rebuild-gif", "--output", str(tmp_path)]) == 1
    error = capsys.readouterr().err
    assert "Pillow" in error
    assert "pip install" in error


def test_rebuilding_from_the_command_line_reports_the_missing_frames(
    capture_screens: ModuleType, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    pytest.importorskip("PIL")
    assert capture_screens.main(["--rebuild-gif", "--output", str(tmp_path)]) == 1
    assert "hoy.png" in capsys.readouterr().err


def test_a_missing_screenshots_folder_is_reported_before_opening_the_app(
    capture_screens: ModuleType,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    pytest.importorskip("PIL")
    monkeypatch.setattr(sys, "platform", "darwin")
    monkeypatch.setattr(tkinter, "Tk", ForbiddenWindow)
    arguments = ["--output", str(tmp_path / "img"), "--captures-dir", str(tmp_path / "nowhere")]
    assert capture_screens.main(arguments) == 1
    assert "does not exist" in capsys.readouterr().err
