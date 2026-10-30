"""System notifications: the only piece that talks to the operating system to alert the person.

Only macOS is supported (through the Notification Center, driven by ``osascript``). On any
other system :func:`notify` does nothing and returns ``False``, so that nobody assumes an
alert went out when it did not.
"""

import subprocess
import sys

# The text travels as arguments of the script (``item 1`` / ``item 2`` of ``argv``) and is never
# spliced into the AppleScript source, so a habit name with quotes can neither break the script
# nor inject instructions into it.
_SCRIPT = (
    "on run argv\n  display notification (item 2 of argv) with title (item 1 of argv)\nend run"
)

# ``osascript`` parses everything after the script as options until it finds a plain argument, so
# a title that starts with "-" would be read as a flag ("-T" fails with "Invalid pid argument").
# "--" ends the options and makes every following argument data.
_END_OF_OPTIONS = "--"


def notify(title: str, message: str, *, platform: str = sys.platform) -> bool:
    """Show a system notification; return ``True`` when it could be launched.

    The notification itself is shown asynchronously by the system, so ``True`` means that
    the request was sent, not that the person has seen it. ``platform`` exists for tests.
    """
    if platform != "darwin":
        return False
    try:
        subprocess.Popen(
            ["osascript", "-e", _SCRIPT, _END_OF_OPTIONS, title, message],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    except OSError:
        return False
    return True
