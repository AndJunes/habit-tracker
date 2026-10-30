"""Where the data lives on each platform, and the private directory that holds it."""

import os
import stat
import sys
from pathlib import Path

import pytest

from habit_tracker.paths import (
    data_dir,
    database_path,
    ensure_private_directory,
    log_path,
)

HOME = Path("/home/ana")


def test_on_macos_the_data_goes_in_application_support_under_the_bundle_identifier() -> None:
    result = data_dir(platform="darwin", environ={}, home=Path("/Users/example"))
    assert result == Path("/Users/example/Library/Application Support/com.habittracker.app")


def test_on_macos_xdg_variables_are_not_consulted() -> None:
    result = data_dir(platform="darwin", environ={"XDG_DATA_HOME": "/elsewhere"}, home=HOME)
    assert result == HOME / "Library" / "Application Support" / "com.habittracker.app"


def test_on_linux_xdg_data_home_is_used_when_it_is_absolute() -> None:
    result = data_dir(platform="linux", environ={"XDG_DATA_HOME": "/data/ana"}, home=HOME)
    assert result == Path("/data/ana/habit-tracker")


def test_on_linux_the_default_is_under_local_share() -> None:
    result = data_dir(platform="linux", environ={}, home=HOME)
    assert result == Path("/home/ana/.local/share/habit-tracker")


def test_an_empty_xdg_data_home_counts_as_unset() -> None:
    result = data_dir(platform="linux", environ={"XDG_DATA_HOME": ""}, home=HOME)
    assert result == Path("/home/ana/.local/share/habit-tracker")


@pytest.mark.parametrize("relative", ["data", "./data", "../data", "~/data", "relative/path"])
def test_a_relative_xdg_data_home_is_invalid_and_ignored(relative: str) -> None:
    result = data_dir(platform="linux", environ={"XDG_DATA_HOME": relative}, home=HOME)
    assert result == Path("/home/ana/.local/share/habit-tracker")


@pytest.mark.parametrize("platform", ["linux", "linux2", "freebsd14", "openbsd7", "cygwin", "aix"])
def test_other_posix_platforms_follow_the_xdg_rules(platform: str) -> None:
    result = data_dir(platform=platform, environ={"XDG_DATA_HOME": "/data"}, home=HOME)
    assert result == Path("/data/habit-tracker")


def test_on_windows_local_app_data_comes_first() -> None:
    environ = {
        "LOCALAPPDATA": "C:\\Users\\Ana\\AppData\\Local",
        "APPDATA": "C:\\Users\\Ana\\AppData\\Roaming",
    }
    result = data_dir(platform="win32", environ=environ, home=Path("C:\\Users\\Ana"))
    assert result == Path("C:\\Users\\Ana\\AppData\\Local") / "HabitTracker"


@pytest.mark.parametrize("local", [None, ""])
def test_on_windows_app_data_is_the_fallback(local: str | None) -> None:
    environ = {"APPDATA": "C:\\Users\\Ana\\AppData\\Roaming"}
    if local is not None:
        environ["LOCALAPPDATA"] = local
    result = data_dir(platform="win32", environ=environ, home=Path("C:\\Users\\Ana"))
    assert result == Path("C:\\Users\\Ana\\AppData\\Roaming") / "HabitTracker"


def test_on_windows_without_either_variable_the_home_folder_is_used() -> None:
    home = Path("C:\\Users\\Ana")
    result = data_dir(platform="win32", environ={}, home=home)
    assert result == home / "AppData" / "Local" / "HabitTracker"


def test_on_windows_xdg_variables_are_not_consulted() -> None:
    home = Path("C:\\Users\\Ana")
    result = data_dir(platform="win32", environ={"XDG_DATA_HOME": "/data"}, home=home)
    assert result == home / "AppData" / "Local" / "HabitTracker"


def test_the_database_and_the_log_live_inside_the_directory() -> None:
    directory = Path("/data/habit-tracker")
    assert database_path(directory) == directory / "habits.sqlite3"
    assert log_path(directory) == directory / "habit-tracker.log"


# ---------- ensure_private_directory ----------

posix_only = pytest.mark.skipif(sys.platform == "win32", reason="POSIX permission bits")


@posix_only
def test_the_directory_is_created_readable_only_by_its_owner(tmp_path: Path) -> None:
    target = tmp_path / "habit-tracker"
    ensure_private_directory(target)
    assert stat.S_IMODE(target.stat().st_mode) == 0o700


@posix_only
def test_the_mode_is_exactly_owner_only_even_with_a_permissive_umask(tmp_path: Path) -> None:
    previous = os.umask(0o000)
    try:
        target = tmp_path / "habit-tracker"
        ensure_private_directory(target)
    finally:
        os.umask(previous)
    assert stat.S_IMODE(target.stat().st_mode) == 0o700


def test_missing_parents_are_created(tmp_path: Path) -> None:
    target = tmp_path / "a" / "b" / "habit-tracker"
    ensure_private_directory(target)
    assert target.is_dir()


def test_an_existing_directory_is_accepted_and_left_alone(tmp_path: Path) -> None:
    target = tmp_path / "habit-tracker"
    ensure_private_directory(target)
    (target / "keep.txt").write_text("data")
    ensure_private_directory(target)
    assert (target / "keep.txt").read_text() == "data"


@posix_only
def test_an_existing_directory_keeps_its_permissions(tmp_path: Path) -> None:
    target = tmp_path / "shared"
    target.mkdir(mode=0o755)
    target.chmod(0o755)
    ensure_private_directory(target)
    assert stat.S_IMODE(target.stat().st_mode) == 0o755


def test_a_file_in_the_way_is_an_error(tmp_path: Path) -> None:
    blocker = tmp_path / "habit-tracker"
    blocker.write_text("not a directory")
    with pytest.raises(FileExistsError):
        ensure_private_directory(blocker)
