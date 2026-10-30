# Security policy

## Supported versions

Only the latest commit on `main` receives fixes.

## Reporting a vulnerability

Please report it privately through GitHub: open the **Security and quality**
tab of this repository and choose **Report a vulnerability**. Do not open a
public issue for a security problem.

Include the steps to reproduce it, the version or commit you tested and what
you expected to happen. I aim to reply within 14 days.

## Scope

Habit Tracker is a local desktop application. It makes no network requests and
keeps its data in a SQLite file in the user's data directory. The areas most
worth reviewing are:

- how the data file is read, migrated and recovered (`habit_tracker.storage`),
- the import of the legacy JSON format,
- the macOS notification and shortcut helpers, which run system commands.
