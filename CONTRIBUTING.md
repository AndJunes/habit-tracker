# Contributing

Thanks for taking a look. This is a small project and contributions are welcome:
bug reports, fixes and focused improvements.

## Set up

Python 3.12 or newer is required. The application has no runtime dependencies;
everything below is for development.

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e . --group dev
pre-commit install      # optional: lint and format on every commit
```

## Checks

Run these before opening a pull request. The same commands run in CI.

```bash
pytest                  # tests; GUI tests are skipped, with a reason, when there is no display
ruff check              # lint
ruff format --check     # formatting
mypy                    # types
```

## Making a change

- Keep a change focused: one logical change per commit, with the tests that
  cover it. Refactors go in their own commits, apart from behaviour changes.
- Add or update tests for any behaviour you touch. The domain and service
  layers are pure and easy to test; see `tests/unit`.
- Follow the existing layering: `domain` knows nothing about storage or the
  interface, `service` talks to a `Repository` protocol, and only `ui` imports
  `tkinter`. See [docs/architecture.md](docs/architecture.md).
- User-facing text lives in `habit_tracker/ui/strings.py`; the code, comments
  and commit messages are in English.

## Commit messages

[Conventional Commits](https://www.conventionalcommits.org/en/v1.0.0/):
`type(scope): imperative summary`, with a summary of about 50 characters, no
trailing period, and a body wrapped at 72 columns that explains why when the
reason is not obvious.

```
fix(service): reject non-finite measurement goals
```

## Reporting a security issue

Please do not open a public issue; see [SECURITY.md](SECURITY.md).
