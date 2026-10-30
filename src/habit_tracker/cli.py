"""Command-line entry point: reads the options, prepares the data and opens the window."""

import argparse
import logging
import os
import sys
from collections.abc import Sequence
from pathlib import Path

from .bootstrap import Options, Session, start_session
from .clock import SystemClock
from .paths import data_dir, ensure_private_directory, log_path
from .ports import StorageError
from .ui import strings

PROGRAM = "habit-tracker"
LOG_FORMAT = "%(asctime)s %(levelname)s %(name)s: %(message)s"

logger = logging.getLogger(__name__)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog=PROGRAM,
        description="Registro de hábitos: a desktop habit tracker with a soft, guilt-free design.",
    )
    parser.add_argument(
        "--demo",
        action="store_true",
        help="open the app with sample data kept in memory: nothing is read or saved",
    )
    parser.add_argument(
        "--data-dir",
        type=Path,
        metavar="DIR",
        help="folder for the data (default: the user data folder of the platform)",
    )
    parser.add_argument(
        "--import-legacy",
        type=Path,
        metavar="FILE",
        help=(
            "import a habitos.json saved by an older version into an empty database; the file "
            "is left untouched and a backup copy is made next to it"
        ),
    )
    return parser


def configure_logging(directory: Path | None) -> None:
    """Send the log to a file in the data directory, or to the console without one."""
    if directory is None:
        logging.basicConfig(level=logging.INFO, format=LOG_FORMAT)
        return
    ensure_private_directory(directory)
    logging.basicConfig(
        level=logging.INFO, format=LOG_FORMAT, filename=log_path(directory), encoding="utf-8"
    )


def startup_messages(session: Session) -> tuple[str, ...]:
    """What the person should be told once the window is on screen."""
    messages: list[str] = []
    if session.recovery is not None:
        logger.warning("damaged database set aside: %s", session.recovery.reason)
        messages.append(strings.recovery_message(session.recovery.quarantined_to))
    if session.imported is not None:
        for item in session.imported.skipped:
            logger.warning("legacy import: %s", item)
        messages.append(
            strings.import_message(
                session.imported.habits, len(session.imported.skipped), session.imported.backup
            )
        )
    return tuple(messages)


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    options = Options(demo=args.demo, data_dir=args.data_dir, import_legacy=args.import_legacy)
    home = Path.home()
    directory = (
        None
        if options.demo
        else options.data_dir or data_dir(platform=sys.platform, environ=os.environ, home=home)
    )
    try:
        configure_logging(directory)
        session = start_session(
            options, clock=SystemClock(), platform=sys.platform, environ=os.environ, home=home
        )
    except (StorageError, OSError) as error:
        logger.exception("the data could not be opened")
        print(f"{PROGRAM}: {error}", file=sys.stderr)
        _show_fatal_error(strings.fatal_message(str(error)))
        return 1
    # Imported here so that --help, and everything above, work without tkinter.
    from .ui.main_window import run

    run(session.service, demo=session.demo, startup_messages=startup_messages(session))
    return 0


def _show_fatal_error(message: str) -> None:
    """Show the error in a dialog, because a shortcut has no terminal to print it to."""
    from .ui.fatal_error import show_fatal_error

    show_fatal_error(strings.APP_TITLE, message)
