# tokonomy

Open-source, local-first usage analytics for AI coding sessions. The first foundation scans Codex CLI and Claude Code session records and stores metadata in a local SQLite database.

## Current scope

- Read-only discovery of Codex and Claude Code session JSONL files.
- Local SQLite index with one row per source session.
- Exact token usage fields only. Missing source values remain `NULL`.
- No cost values yet: client-side `cost-state` values are not treated as actual spend.
- Codex plan type and native quota snapshots can be polled from Codex's official local app-server protocol.
- No estimates, pricing tables, telemetry export, dashboard, or Windows background-service registration yet.
- Transcript text, prompts, responses, tool arguments, and tool results are not stored in tokonomy's database.

JSONL records are parsed in memory to extract allowlisted fields. Source files are never modified. The database stores source file paths for traceability; these may contain local project names.

## Install

Windows için repo klasöründe bir kez (repo içindeki `.venv` ortamına kurar):

```powershell
Set-ExecutionPolicy -Scope CurrentUser RemoteSigned
.\install.ps1
```

Yeni bir terminal açtıktan sonra `tokonomy` yazmak yerel kullanım ekranını gösterir. Dashboard açılırken yeni/değişmiş session kayıtlarını tarar. Var olan terminalin PATH'i yenilenmediyse yeni terminal açın.

Elle Python kurulumu:

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e .
tokonomy scan
tokonomy history --all
tokonomy watch-limits --interval 120
```

Terminal komutları: `tokonomy scan [--force]`, `tokonomy history [--all]` ve `tokonomy watch-limits [--interval 120]`.

The default database is `%LOCALAPPDATA%\tokonomy\tokonomy.sqlite3`. `watch-limits` remains running until Ctrl+C and polls Codex's limit snapshot every 120 seconds by default (minimum 30 seconds). It also rescans only source files whose size or modification time changed. Use `--data-dir <path>` to select another database directory. Set `CODEX_HOME` or `CLAUDE_CONFIG_DIR` if either client stores sessions outside its default location.

## Data model

The `sessions` table contains the source, source session ID, timestamps, and source file path. Exact token counts are stored in `model_usage` where the client exposes them. Codex per-response token deltas are also stored as timestamped `usage_events`, allowing exact local token totals for a 5-hour or 7-day interval. Claude Code's cumulative `cost-state` token snapshot is retained in session summaries; its cost value is ignored. A limit snapshot records plan type, source limit bucket, window duration, used percentage, and source reset time. On exhaustion, it also captures locally observed tokens, session count, and average tokens per session within that window. This describes local-client activity and does not include other devices or Claude.ai/ChatGPT web usage.

`tokonomy scan --force` also imports Codex's historical `token_count` rate-limit observations from local rollout files. `tokonomy history` groups them by the reset timestamp the provider recorded, shows latest/peak observed percentage and observation count per period, plus exact local Codex token deltas in that interval. `--all` shows the full available history. Historical observations have no plan type in the source records. A reset period is only listed when a source observation includes its reset timestamp; missed periods cannot be reconstructed. Current checked local history begins 2026-09-08. Claude session totals can be historical, but Claude quota/reset history is not exposed by its local structured records.

Codex exposes this through its official local app-server method `account/rateLimits/read`; the watcher runs it with the existing Codex CLI login and saves a snapshot every poll. The `primary` and `secondary` labels are not assumed to mean 5h and 7d; the source window duration is used. Read more in [Codex usage limits](https://help.openai.com/en/articles/11369540-using-codex-with-your-chatgpt-plan) and the [Codex rate-limit protocol](https://github.com/openai/codex/blob/main/codex-rs/app-server-protocol/src/protocol/v2/account.rs).

Claude plans can have 5-hour and weekly allowances, with plan-specific exceptions, but the official structured local telemetry/session records do not expose quota reset snapshots or plan type. tokonomy does not scrape the signed-in account UI or infer those values. See [Claude usage limits](https://support.claude.com/en/articles/11647753-how-do-usage-and-length-limits-work).

## License

MIT. See [LICENSE](LICENSE).

## Collection and analysis

`tokonomy collector start` starts a Windows background collector independent of the terminal UI. It imports changed files and polls Codex quotas every 120 seconds. `tokonomy collector status` shows the last cycle; `tokonomy collector stop` requests shutdown. It is not registered for Windows login startup. Only one collector per database runs. SQLite uses WAL with a 30-second lock timeout.

`tokonomy period --source codex --hours 5` reports recorded usage over a rolling interval, sessions opened versus sessions with usage, and the largest input contributors. This is a rolling interval, not an inferred provider quota period. Missing activity outside local logs is not reconstructed.

`tokonomy group assign --name "feature-a" --source codex --session SESSION_ID` assigns an explicit work group. Reassignment moves the session; `group remove --source codex --session SESSION_ID` removes membership. `group list` summarizes groups. Assignments survive rescans. Intent similarity is not inferred from transcript contents.

The Projects tab groups observed working directories by local Git common directory, combining worktrees when available. Session details (Enter) show source files, token event IDs, recorded child agents and compaction observations. Counts describe recorded events, not all possible activity. `tokonomy resets` lists quota drops; `--mark ID --reason user-credit` labels a transition as user reported, without redeeming a provider reset credit.

## Source coverage

Codex and Claude provide timestamped usage events. Hermes and OpenCode v2 are imported from read-only SQLite session counters; these totals are not allocated to dates or attributed to the last model as if all requests used it. Cursor imports allowlisted composer headers only: token values remain unknown. No credentials or message contents are selected by these database adapters. Sources shows imported counts and coverage. Antigravity/Gemini integration remains under investigation.

Quota rows in Overview/History open a source-window report with Enter. Totals run from the reported reset minus window duration up to the selected observation, capped at reset. It distinguishes sessions opened from sessions with usage events, provides means/medians, and links contributors to session details. This is local observed coverage; reset timestamp jitter is not silently merged into inferred quota cycles.

`tokonomy export usage.jsonl` exports schema-versioned session totals, timestamped events, parent relationships, compaction observations, quota snapshots and source coverage. It excludes local paths, prompts, responses and group names. Missing metrics remain null. Existing output files are never overwritten.
