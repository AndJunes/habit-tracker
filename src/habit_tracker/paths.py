"""Where the application keeps its files, following each platform's conventions.

The functions are pure: the platform, the environment and the home directory are
arguments, so every rule can be tested on any machine.
"""

from collections.abc import Mapping
from pathlib import Path, PurePosixPath

BUNDLE_IDENTIFIER = "com.habittracker.app"
DATABASE_FILENAME = "habits.sqlite3"
LOG_FILENAME = "habit-tracker.log"

_PRIVATE_DIRECTORY_MODE = 0o700


def data_dir(*, platform: str, environ: Mapping[str, str], home: Path) -> Path:
    """The directory that holds the database and the log.

    ``platform`` is a ``sys.platform`` value. The rules, by platform:

    * macOS (``darwin``): ``~/Library/Application Support/com.habittracker.app``.
      Apple's File System Programming Guide asks apps to keep their files in a
      subdirectory of Application Support named after the bundle identifier.
    * Windows (``win32``): ``%LOCALAPPDATA%\\HabitTracker``, then
      ``%APPDATA%\\HabitTracker``, then ``~/AppData/Local/HabitTracker``. Microsoft's
      documentation only lists the known folders; choosing Local over Roaming is
      our decision: the database is a single file that is rewritten in place, and
      roaming profiles copy whole files between machines, which does not suit it.
    * Everything else (Linux and other POSIX systems): ``$XDG_DATA_HOME/habit-tracker``,
      or ``~/.local/share/habit-tracker`` when the variable is unset, empty or not
      an absolute path (XDG Base Directory Specification 0.8: a relative path in
      these variables is invalid and must be ignored).
    """
    if platform == "darwin":
        return home / "Library" / "Application Support" / BUNDLE_IDENTIFIER
    if platform == "win32":
        return _windows_dir(environ, home)
    return _xdg_dir(environ, home)


def database_path(directory: Path) -> Path:
    """The database file inside ``directory``."""
    return directory / DATABASE_FILENAME


def log_path(directory: Path) -> Path:
    """The log file inside ``directory``."""
    return directory / LOG_FILENAME


def ensure_private_directory(path: Path) -> None:
    """Create ``path`` (and any missing parents) readable only by its owner.

    An existing directory is left as it is. The mode applies to ``path`` itself:
    missing parents get the default permissions, like ``mkdir -p``. Windows
    ignores the mode.
    """
    path.mkdir(mode=_PRIVATE_DIRECTORY_MODE, parents=True, exist_ok=True)


def _windows_dir(environ: Mapping[str, str], home: Path) -> Path:
    for variable in ("LOCALAPPDATA", "APPDATA"):
        base = environ.get(variable)
        if base:
            return Path(base) / "HabitTracker"
    return home / "AppData" / "Local" / "HabitTracker"


def _xdg_dir(environ: Mapping[str, str], home: Path) -> Path:
    base = environ.get("XDG_DATA_HOME", "")
    if base and PurePosixPath(base).is_absolute():
        return Path(base) / "habit-tracker"
    return home / ".local" / "share" / "habit-tracker"
