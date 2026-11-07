# Contributing to tokonomy

Thanks for helping make AI usage accounting more honest.

## Ground rules

- **Privacy is a feature.** Never add code that stores prompts, responses, tool
  arguments, file contents or credentials. Parsers must only select allowlisted
  metadata fields.
- **Unknown is not zero.** If a source does not report a value, store `NULL` and
  label the gap. Do not infer provider limits from UI scraping.
- **Source semantics are preserved.** If you normalise a value, do it in the
  metrics layer and keep the raw value intact.
- **Bump the parser version.** Any change to extracted fields or token semantics
  must bump `PARSER_VERSION` in the relevant `sources/*.py` module so existing
  databases are re-read.

## Development setup

```bash
python -m venv .venv
. .venv/bin/activate          # Windows: .\.venv\Scripts\Activate.ps1
python -m pip install -e .
python -m unittest discover -s tests -v
```

No network, API key or account is required. Tests build temporary SQLite
databases and never touch your real data directory.

## Adding a source

1. Add `src/tokonomy/sources/<name>.py` with `discover()` and `read_session()`.
2. Return a `Session` with explicit token fields; leave unavailable values `None`.
3. Set `PARSER_VERSION = 1` and register the source in `cli.source_specs()`.
4. Write a coverage label in the Sources tab and a test for the parser.
5. If the source has no timestamped events, it is a totals-only source; make that
   explicit in the UI and docs.

## UI and screenshots

```bash
python scripts/make_assets.py
```

This rebuilds `docs/cli.png`, `docs/dashboard.png` and `docs/dashboard.html` from
synthetic demo data. Never publish screenshots of real projects or spending.

The dashboard is server-rendered HTML with inline CSS/SVG. Keep it dependency-free
and self-contained so `tokonomy export report.html` works offline.

## Pull requests

- Keep commits focused and describe the user-visible effect.
- Run the test suite and `python -m compileall -q src`.
- If you change token semantics or coverage, update README and CHANGELOG.
- By contributing you agree to license your work under MIT.
