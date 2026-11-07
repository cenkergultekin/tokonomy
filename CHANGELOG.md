# Changelog

All notable changes to tokonomy are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/) and the project uses
[semantic versioning](https://semver.org/).

## [0.2.0] — 2026-11-07

The trust, decision and access release.

### Trust

- Cache-aware accounting: OpenAI-style inclusive input is normalised to
  **uncached input**; Anthropic-style separate cache fields are preserved.
- Parser versions are stored per source file. A parser change invalidates the
  scan cache and re-imports history instead of keeping stale rows.
- Claude Code now imports timestamped per-message usage events (including
  subagent transcripts), not only cumulative session totals.
- Source health is recorded for every import; missing values stay `NULL`.
- Per-source pause/enable and `tokonomy delete` for imported data.
- Dated, editable price table with explicit estimate labels and coverage.

### Decision

- Quota burn rate, projected exhaustion and “on track” forecasts, with
  `collecting` state until enough recent history exists.
- Cache savings estimate and cost coverage on every surface.
- Project and model breakdowns with token, cache and spend columns.
- `tokonomy digest`, `tokonomy forecast` and `tokonomy status --json`.
- Budget checks in the MCP server and JSON API.

### Access

- New localhost dashboard (`tokonomy web`) with the same HTML as
  `tokonomy export report.html`; no framework, no CDN, no telemetry.
- Dependency-free MCP stdio server (`tokonomy mcp`) with eight read-only tools.
- Redesigned CLI dashboard and Textual UI.
- Marketing README, landing page and reproducible demo-data screenshots.

### Changed

- `sessions.input_tokens` is still the raw source value; derived uncached values
  live in the metrics layer, so no source semantics are lost.
- Database schema version 2 adds `source_files.parser_version` and
  `source_settings`.

### Fixed

- Claude records that were already marked as scanned are now re-read after the
  parser upgrade, restoring missing timestamped events.
- Mojibake in the Textual UI.
- Quota forecasts no longer group by the provider’s jittery reset timestamp.

## [0.1.0] — 2026-10-30

- Initial local SQLite index for Codex and Claude Code sessions.
- Codex quota snapshots, historical limit periods and delta usage events.
- Hermes, OpenCode and Cursor imports with coverage labels.
- Terminal dashboard, session details and JSONL export.
