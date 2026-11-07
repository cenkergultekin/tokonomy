# Tokonomy

Open-source, local-first usage analytics for AI coding sessions. The first foundation scans Codex CLI and Claude Code session records and stores metadata in a local SQLite database.

## Current scope

- Read-only discovery of Codex and Claude Code session JSONL files.
- Local SQLite index with one row per source session.
- Exact token usage fields only. Missing source values remain `NULL`.
- No cost values yet: client-side `cost-state` values are not treated as actual spend.
- No estimates, pricing tables, account API calls, telemetry export, dashboard, or background watcher yet.
- Transcript text, prompts, responses, tool arguments, and tool results are not stored in Tokonomy's database.

JSONL records are parsed in memory to extract allowlisted fields. Source files are never modified. The database stores source file paths for traceability; these may contain local project names.

## Install

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e .
tokonomy scan
```

The default database is `%LOCALAPPDATA%\Tokonomy\tokonomy.sqlite3`. Use `tokonomy scan --data-dir <path>` to select another directory. Set `CODEX_HOME` or `CLAUDE_CONFIG_DIR` if either client stores sessions outside its default location.

## Data model

The `sessions` table contains the source, source session ID, timestamps, and source file path. Exact token counts are stored in `model_usage` where the client exposes them. Codex token totals are summed from per-turn usage records; Claude Code values come from its cumulative `cost-state` snapshot and replace earlier snapshots. Costs, TPS, durations, and limits are not calculated or inferred in this foundation.

## License

MIT. See [LICENSE](LICENSE).
