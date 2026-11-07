<div align="center">

<img src="docs/cli.png" alt="tokonomy CLI dashboard" width="100%">

<h1>tokonomy</h1>

<p><strong>Local-first, cache-aware usage analytics for AI coding sessions.</strong><br>
Know where your tokens, quota and money actually go — without uploading a single prompt.</p>

[![CI](https://github.com/cenkergultekin/tokonomy/actions/workflows/ci.yml/badge.svg)](https://github.com/cenkergultekin/tokonomy/actions/workflows/ci.yml)
[![MIT](https://img.shields.io/badge/license-MIT-7ee787.svg)](LICENSE)
[![Python](https://img.shields.io/badge/python-3.11%2B-6cb6ff.svg)](pyproject.toml)
[![MCP](https://img.shields.io/badge/MCP-stdio-d2a8ff.svg)](#mcp-your-agent-can-see-its-budget)

</div>

---

AI coding agents are good at spending tokens. They are bad at telling you what they spent.
Invoices arrive late, quota screens are per-vendor, and the biggest number on most
dashboards — “input tokens” — is usually 95% cache reads.

tokonomy reads the session records your tools already write, keeps only allowlisted
metadata in a local SQLite database, and turns it into three things:

| Layer | Question it answers | What ships |
| --- | --- | --- |
| **Trust** | Are these numbers honest? | Cache-inclusive vs cache-exclusive token semantics, parser versioning, per-source coverage, `NULL` instead of fake zeros, labelled estimates |
| **Decision** | What should I do differently? | Quota burn forecast, project and model spend, weekly digest, budget checks, cache savings |
| **Access** | How do I use it? | Terminal UI, polished localhost dashboard, static HTML export, MCP server for agents, JSON API |

It is not a proxy, not a SaaS, and not another place your prompts get stored.

## The dashboard

<p align="center">
  <img src="docs/dashboard.png" alt="tokonomy web dashboard" width="920">
</p>

The same page is available three ways:

```powershell
tokonomy web                 # http://127.0.0.1:8765
tokonomy dashboard           # terminal overview
tokonomy export report.html  # self-contained static HTML
```

Screenshots in this README use synthetic demo data, not a real person's projects.

## Why cache-aware matters

Codex reports `input_tokens` **including** cached tokens. Claude Code reports cached
tokens **separately**. Add them together naively and you get a meaningless number.

A real local database looked like this:

| Raw “input” | Cached | Uncached input | Cache hit |
| ---: | ---: | ---: | ---: |
| 1.96 B | 1.92 B | 46.6 M | 97.6% |

That is a 97.6% cache hit rate — good news — displayed as a two-billion-token bill by
most tools. tokonomy makes **uncached input** the headline, keeps cache read/write
visible, and estimates cache savings separately.

## Install

**Windows (recommended, one command):**

```powershell
git clone https://github.com/cenkergultekin/tokonomy.git
cd tokonomy
Set-ExecutionPolicy -Scope CurrentUser RemoteSigned
.\install.ps1
```

Open a new terminal and run `tokonomy`. The installer creates a repo-local `.venv`
and adds a launcher to your user PATH.

**Manual (any OS):**

```bash
python -m venv .venv
. .venv/bin/activate        # Windows: .\.venv\Scripts\Activate.ps1
python -m pip install -e .
tokonomy scan --force
tokonomy dashboard
```

The first scan imports historical sessions and can take a minute. The database lives at
`%LOCALAPPDATA%\tokonomy\tokonomy.sqlite3` on Windows. Override it with `--data-dir`
or `CODEX_HOME` / `CLAUDE_CONFIG_DIR`.

## What it reads

| Source | What is imported | Token detail |
| --- | --- | --- |
| **Codex CLI** | rollout JSONL / JSONL.ZST | timestamped per-response usage, exact quota snapshots |
| **Claude Code** | project JSONL + subagent transcripts | timestamped per-message usage, reconciled by message ID |
| **Hermes** | read-only SQLite counters | session totals only |
| **OpenCode** | read-only SQLite counters | session totals only |
| **Cursor** | composer headers | metadata only, tokens unknown |

Source files are opened read-only. Prompts, responses, tool arguments and tool results
are never written to the tokonomy database. The database stores source paths for
traceability, which may contain local project names.

## Commands

```text
tokonomy                      interactive terminal app
tokonomy dashboard            one-screen overview (cache-aware)
tokonomy digest --days 7      weekly summary + burn forecast
tokonomy forecast             quota burn rate and projected exhaustion
tokonomy history              observed quota periods
tokonomy web                  localhost dashboard
tokonomy export usage.jsonl   versioned metadata export
tokonomy export report.html   self-contained HTML dashboard
tokonomy mcp                  MCP stdio server for coding agents
tokonomy status --json        machine-readable status for scripts/CI
tokonomy sources              list sources and pause/enable them
tokonomy delete --source X --yes   delete imported data (source files untouched)
tokonomy doctor               read-only data quality audit
tokonomy collector start      Windows background collector
```

### Quota burn forecast

tokonomy compares recent percentage movement with the provider-reported reset time:

```text
codex 5h   89.5%   burn 9.4%/h   empties in ~1.1h, before reset (2.0h)
codex 7d   41.3%   on track      68% projected at reset
```

Forecasts are local observations. They are marked `collecting` until enough recent
history exists, and never pretend a reset timestamp is a new quota cycle when the
provider jitters it.

### Budget checks

`tokonomy status --json` and the MCP `budget_check` tool return a machine-readable
verdict. Prices are public list prices stored in `pricing.json` (editable in your data
directory); every derived cost is labelled an estimate.

## MCP: your agent can see its budget

`tokonomy mcp` exposes eight read-only tools over stdio:
`usage_summary`, `quota_status`, `project_breakdown`, `model_compare`,
`recent_sessions`, `budget_check`, `coverage`, `weekly_digest`.

Claude Code:

```bash
claude mcp add tokonomy -- tokonomy mcp
```

Codex (`~/.codex/config.toml`):

```toml
[mcp_servers.tokonomy]
command = "tokonomy"
args = ["mcp"]
```

Any MCP client:

```json
{
  "mcpServers": {
    "tokonomy": {
      "command": "tokonomy",
      "args": ["mcp"]
    }
  }
}
```

An agent can now ask “am I about to burn the weekly quota?” before it starts a long
refactor, instead of after.

## Data semantics

tokonomy is deliberately boring about provenance:

- **Missing stays missing.** Source values that are not reported remain `NULL`, not zero.
- **Two cache models.** OpenAI-style input includes cache reads; Anthropic-style input
  does not. The dashboard normalises both into `uncached input` and keeps the raw fields.
- **Events over totals.** When a source has timestamped events, totals are computed from
  events; otherwise session counters are used and labelled `session totals only`.
- **Parser versions.** Changing a parser invalidates the scan cache, so old rows are
  re-read instead of silently surviving a schema change.
- **Estimates are estimates.** Cost uses a local, dated price table; it is not an invoice.
  Unknown models remain unpriced and are reported in coverage.
- **No content.** No prompts, responses, tool arguments or file contents.

## Development

```bash
python -m pip install -e .
python -m unittest discover -s tests -v
python scripts/make_assets.py   # regenerate README screenshots (Chrome/Edge required)
```

CI runs the suite on Windows and Linux, Python 3.11 and 3.13.

The project is Windows-first because the background collector and login startup use
Windows APIs. The CLI, dashboard and MCP server are pure Python and run on macOS/Linux;
a native collector for those platforms is on the roadmap.

## Roadmap

- [x] Cache-aware accounting and parser versioning
- [x] Quota burn forecast and budget checks
- [x] Localhost dashboard and static HTML export
- [x] MCP server
- [ ] macOS/Linux background collector
- [ ] OpenTelemetry ingestion (opt-in)
- [ ] More sources: Gemini/Antigravity, Copilot
- [ ] Optional encrypted multi-machine sync (local-first, never required)

## License

MIT. See [LICENSE](LICENSE).

---

<p align="center"><sub>tokonomy v0.2.0 · made for people who pay for tokens · estimates, never invoices</sub></p>
