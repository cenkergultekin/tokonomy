"""tokonomy command line: trust, decision and access layers in one binary."""

from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
import time
from dataclasses import dataclass, replace
from datetime import datetime, timezone
from pathlib import Path

from tokonomy import __version__, metrics
from tokonomy.formatting import compact, money, pct
from tokonomy.providers.codex_limits import read_rate_limits
from tokonomy.store import SCHEMA_VERSION, Store


def default_data_dir() -> Path:
    base = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local"))
    directory = base / "tokonomy"
    pointer = directory / "active-directory.txt"
    return Path(pointer.read_text(encoding="utf-8").strip()) if pointer.exists() else directory


def _home() -> Path:
    return Path.home()


@dataclass(frozen=True)
class SourceSpec:
    key: str
    label: str
    root: Path
    discover: object
    parser: object
    parser_version: int


def source_specs() -> list[SourceSpec]:
    from tokonomy.sources import claude, codex

    return [
        SourceSpec(
            "codex",
            "Codex",
            Path(os.environ.get("CODEX_HOME", _home() / ".codex")) / "sessions",
            codex.discover,
            codex.read_session,
            codex.PARSER_VERSION,
        ),
        SourceSpec(
            "claude-code",
            "Claude Code",
            Path(os.environ.get("CLAUDE_CONFIG_DIR", _home() / ".claude")) / "projects",
            claude.discover,
            claude.read_session,
            claude.PARSER_VERSION,
        ),
    ]


def collect(data_dir: Path, store: Store | None = None, force: bool = False, quiet: bool = False) -> int:
    owns_store = store is None
    store = store or Store(data_dir / "tokonomy.sqlite3")
    try:
        for spec in source_specs():
            if not store.source_enabled(spec.key):
                if not quiet:
                    print(f"{spec.label}: paused by source setting")
                continue
            files = spec.discover(spec.root)
            changed = [
                path for path in files
                if force or not store.has_scanned_file(spec.key, path, spec.parser_version)
            ]
            if not changed:
                if not quiet:
                    print(f"{spec.label}: {len(files)} files, no changes")
                continue
            if spec.key == "claude-code":
                _import_claude(store, spec, files, changed, force, quiet)
                _mark_health(store, spec, len(files), len(changed), quiet)
                continue
            imported = errors = 0
            for path in changed:
                try:
                    session = spec.parser(path)
                    if session:
                        store.upsert_session(session)
                        from tokonomy.context import enrich

                        enrich(store, session, path)
                        imported += 1
                    store.mark_file_scanned(spec.key, path, spec.parser_version)
                except (OSError, ValueError, EOFError):
                    errors += 1
            _mark_health(store, spec, len(files), len(changed), quiet, errors=errors)
            if not quiet:
                print(
                    f"{spec.label}: discovered={len(files)} changed={len(changed)} "
                    f"imported={imported} errors={errors}"
                )
        _import_secondary(store, quiet)
        store.connection.commit()
        if not quiet:
            print(f"Indexed sessions: {store.count_sessions():,}")
            print(f"Database: {data_dir / 'tokonomy.sqlite3'}")
    except Exception:
        store.connection.rollback()
        raise
    finally:
        if owns_store:
            store.close()
    return 0


def _mark_health(store, spec, files: int, changed: int, quiet: bool, errors: int = 0):
    from datetime import datetime, timezone

    status = "Imported" if not errors else "Partial"
    detail = f"{files} files; {changed} changed" + (f"; {errors} errors" if errors else "")
    store.connection.execute(
        "INSERT OR REPLACE INTO source_health VALUES (?,?,?,?)",
        (spec.key, datetime.now(timezone.utc).isoformat(), status, detail),
    )


def _import_claude(store, spec, files, changed, force, quiet):
    from tokonomy.context import enrich
    from tokonomy.reconcile import reconcile
    from tokonomy.sources.jsonl import iter_jsonl

    parsed = []
    failures = 0
    for path in files:
        try:
            session = spec.parser(path)
            if session:
                parsed.append(session)
        except (OSError, ValueError, EOFError):
            failures += 1
    if failures:
        if not quiet:
            print(f"Claude Code reconciliation deferred: {failures} unreadable files")
        return
    for raw in parsed:
        store.connection.execute(
            "INSERT OR IGNORE INTO session_sources VALUES (?,?,?)",
            (raw.source, raw.session_id, raw.source_file),
        )
        store.connection.execute(
            "DELETE FROM usage_origins WHERE source=? AND source_file=?",
            (raw.source, raw.source_file),
        )
        for ordinal, record in enumerate(iter_jsonl(Path(raw.source_file)), 1):
            message = record.get("message")
            if record.get("type") == "assistant" and isinstance(message, dict) and message.get("id"):
                store.connection.execute(
                    "INSERT OR IGNORE INTO usage_origins VALUES (?,?,?,?)",
                    (raw.source, message["id"], raw.source_file, ordinal),
                )
    for session in reconcile(parsed):
        store.upsert_session(session)
        enrich(store, session, Path(session.source_file))
    for path in changed:
        store.mark_file_scanned(spec.key, path, spec.parser_version)
    if not quiet:
        verb = "re-read" if force else "reconciled"
        print(
            f"Claude Code: {verb} {len(parsed)} files, {len(changed)} changed, "
            f"{sum(len(s.usage_events) for s in parsed):,} timestamped messages"
        )


def _import_secondary(store, quiet):
    from datetime import datetime, timezone

    from tokonomy.sources import hermes

    home = _home()
    if store.source_enabled("hermes"):
        hermes_path = Path(
            os.environ.get("HERMES_HOME", Path(os.environ.get("LOCALAPPDATA", home / "AppData/Local")) / "hermes")
        ) / "state.db"
        try:
            store.connection.execute("SAVEPOINT hermes_import")
            count = hermes.collect(store, hermes_path)
            store.connection.execute("RELEASE hermes_import")
            state = "Imported" if hermes_path.exists() else "Not found"
            detail = f"{count} sessions; session totals only"
        except (OSError, ValueError, __import__("sqlite3").Error) as error:
            store.connection.execute("ROLLBACK TO hermes_import")
            store.connection.execute("RELEASE hermes_import")
            state, detail = "Unavailable", type(error).__name__
        store.connection.execute(
            "INSERT OR REPLACE INTO source_health VALUES (?,?,?,?)",
            ("hermes", datetime.now(timezone.utc).isoformat(), state, detail),
        )
        if not quiet:
            print(f"Hermes: {state} / {detail}")

    from tokonomy.sources import desktop

    for source, path, adapter, coverage in [
        ("opencode", home / ".local/share/opencode/opencode.db", desktop.opencode, "Session totals only"),
        (
            "cursor",
            Path(os.environ.get("APPDATA", home / "AppData/Roaming")) / "Cursor/User/globalStorage/state.vscdb",
            desktop.cursor,
            "Session metadata only; tokens unavailable",
        ),
    ]:
        if not store.source_enabled(source):
            continue
        try:
            store.connection.execute("SAVEPOINT desktop_import")
            count = adapter(store, path)
            store.connection.execute("RELEASE desktop_import")
            state = "Imported" if path.exists() else "Not found"
            detail = f"{count} sessions; {coverage}"
        except (OSError, ValueError, __import__("sqlite3").Error) as error:
            store.connection.execute("ROLLBACK TO desktop_import")
            store.connection.execute("RELEASE desktop_import")
            state, detail = "Unavailable", type(error).__name__
        store.connection.execute(
            "INSERT OR REPLACE INTO source_health VALUES (?,?,?,?)",
            (source, datetime.now(timezone.utc).isoformat(), state, detail),
        )
        if not quiet:
            print(f"{source}: {state} / {detail}")


def watch_limits(data_dir: Path, interval: int) -> int:
    store = Store(data_dir / "tokonomy.sqlite3")
    print(f"Watching provider limits every {interval}s. Stop with Ctrl+C.")
    try:
        while True:
            collect(data_dir, store)
            try:
                snapshots = read_rate_limits()
                for snapshot in snapshots:
                    usage = store.window_usage(
                        "codex", snapshot.window_seconds, snapshot.captured_at, snapshot.resets_at
                    )
                    snapshot = replace(snapshot, **usage)
                    store.save_limit_snapshot(snapshot)
                    window = _window_label(snapshot.window_seconds)
                    print(
                        f"codex {snapshot.plan_type or 'plan unknown'} {snapshot.limit_id} "
                        f"{window}: {snapshot.used_percent}% resets={snapshot.resets_at or 'unknown'}"
                    )
                store.connection.commit()
            except (OSError, RuntimeError, TimeoutError, ValueError) as error:
                print(f"Codex limit snapshot unavailable: {type(error).__name__}")
            time.sleep(interval)
    except KeyboardInterrupt:
        return 0
    finally:
        store.close()


def _window_label(seconds: int) -> str:
    if seconds == 5 * 3600:
        return "5h"
    if seconds == 7 * 86400:
        return "7d"
    if seconds % 3600 == 0:
        return f"{seconds // 3600}h"
    return f"{seconds}s"


def show_history(data_dir: Path, show_all: bool) -> int:
    store = Store(data_dir / "tokonomy.sqlite3")
    try:
        rows = store.connection.execute(
            """SELECT provider, limit_id, window_seconds, resets_at,
                      MIN(captured_at) AS first_seen, MAX(captured_at) AS last_seen,
                      MAX(used_percent) AS peak_percent,
                      (SELECT s.used_percent FROM limit_snapshots s
                       WHERE s.provider = grouped.provider AND s.limit_id = grouped.limit_id
                         AND s.window_seconds = grouped.window_seconds
                         AND s.resets_at = grouped.resets_at
                       ORDER BY s.captured_at ASC LIMIT 1) AS first_percent,
                      (SELECT s.used_percent FROM limit_snapshots s
                       WHERE s.provider = grouped.provider AND s.limit_id = grouped.limit_id
                         AND s.window_seconds = grouped.window_seconds
                         AND s.resets_at = grouped.resets_at
                       ORDER BY s.captured_at DESC LIMIT 1) AS last_percent,
                      (SELECT s.captured_at FROM limit_snapshots s
                       WHERE s.provider = grouped.provider AND s.limit_id = grouped.limit_id
                         AND s.window_seconds = grouped.window_seconds
                         AND s.resets_at = grouped.resets_at
                       ORDER BY s.captured_at DESC LIMIT 1) AS observed_at,
                      COUNT(*) AS observations
               FROM limit_snapshots AS grouped
               WHERE resets_at IS NOT NULL
               GROUP BY provider, limit_id, window_seconds, resets_at
               ORDER BY observed_at DESC, provider, window_seconds"""
        ).fetchall()
        if not show_all:
            rows = rows[:20]
        if not rows:
            print("No historical limit snapshots. Run `tokonomy scan --force` and `tokonomy watch-limits`.")
            return 0
        print("provider  window  reset (UTC)             span UTC       start-end  min/max/last  observations  local input/output tokens  sessions")
        for row in rows:
            from datetime import timedelta

            reset_at = datetime.fromisoformat(row["resets_at"])
            period_start = (reset_at - timedelta(seconds=row["window_seconds"])).isoformat()
            totals = store.connection.execute(
                """SELECT SUM(input_tokens), SUM(output_tokens), COUNT(DISTINCT session_id)
                   FROM usage_events WHERE source = ? AND occurred_at >= ? AND occurred_at <= ?""",
                (row["provider"], period_start, row["observed_at"]),
            ).fetchone()
            window = _window_label(row["window_seconds"])
            reset = row["resets_at"].replace("T", " ").split("+", 1)[0]
            first = row["first_seen"].replace("T", " ")[5:16]
            last = row["last_seen"].replace("T", " ")[5:16]
            percent = f"{row['first_percent']:g}/{row['peak_percent']:g}/{row['last_percent']:g}%"
            tokens = f"{totals[0] or 0:,}/{totals[1] or 0:,}"
            sessions = totals[2]
            print(
                f"{row['provider']:<9} {window:<6}  {reset:<22} {first}-{last}  {percent:>12}  "
                f"{row['observations']:>12,}  {tokens:>26}  {sessions if sessions is not None else 'unknown'}"
            )
        return 0
    finally:
        store.close()


def _color(text: str, code: str) -> str:
    if os.environ.get("NO_COLOR"):
        return text
    if not sys.stdout.isatty() and os.environ.get("TOKONOMY_COLOR") != "always":
        return text
    return f"\033[{code}m{text}\033[0m"


def _safe_print(text: str) -> None:
    encoding = (sys.stdout.encoding or "utf-8").lower().replace("-", "")
    if encoding in {"utf8", "utf8sig"}:
        print(text)
        return
    fallback = text.translate(str.maketrans({"─": "-", "█": "#", "░": ".", "·": "|", "—": "-", "◍": "o", "⚠": "!"}))
    print(fallback.encode(sys.stdout.encoding or "ascii", errors="replace").decode(sys.stdout.encoding or "ascii"))


def _bar(percent: float, width: int = 24) -> str:
    filled = max(0, min(width, round(percent * width / 100)))
    color = "32" if percent < 60 else "33" if percent < 85 else "31"
    return _color("█" * filled, color) + _color("░" * (width - filled), "90")


def _spark(values: list[float]) -> str:
    blocks = "▁▂▃▄▅▆▇█"
    peak = max(values) if values and max(values) > 0 else 1
    return "".join(
        blocks[min(7, int((value / peak) ** 0.45 * 7))] if value else "·"
        for value in values
    )


def dashboard(data_dir: Path, refresh: bool = True) -> int:
    if refresh:
        collect(data_dir)
    store = Store(data_dir / "tokonomy.sqlite3")
    try:
        data = metrics.summary(store.connection)
        days = metrics.daily(store.connection, 14)
        quotas = metrics.quota(store.connection)
        projects = metrics.projects(store.connection, limit=5)
        width = shutil.get_terminal_size((96, 24)).columns
        line = "─" * min(84, max(56, width - 4))
        stamp = datetime.now().strftime("%Y-%m-%d %H:%M")
        _safe_print(_color(" ◍ TOKONOMY ", "1;38;2;126;231;135") + _color("LOCAL AI USAGE OBSERVATORY", "90") + f"   {stamp}")
        _safe_print(_color(line, "90"))
        sessions_text = f"{data['sessions']:,}"
        _safe_print(
            f"  SESSIONS {_color(sessions_text, '1;37')}   "
            f"UNCACHED IN {_color(compact(data['uncached']), '36')}   "
            f"CACHE HIT {_color(pct(data['cache_hit']), '32')}   "
            f"OUTPUT {_color(compact(data['output']), '35')}   "
            f"EST. SPEND {_color(money(data['cost']), '33')}"
        )
        _safe_print(_color(f"  cache-aware · {data['sessions']} sessions · {pct(data['cost_coverage'])} of tokens priceable · estimates, not invoices", "90"))
        _safe_print("")
        _safe_print(_color("  ACTIVITY · last 14 days · uncached input", "1;37"))
        values = [row["uncached"] for row in days[:-1]]
        if any(values):
            nonzero = [value for value in values if value]
            _safe_print(f"  {_spark(values)}   {compact(min(nonzero))} → {compact(max(values))}")
        else:
            _safe_print("  No dated usage yet. Run `tokonomy scan --force`.")
        _safe_print("")
        _safe_print(_color("  QUOTA", "1;37"))
        if quotas:
            for item in quotas:
                percent = float(item["used_percent"])
                forecast = item["forecast"]
                window = _window_label(item["window_seconds"])
                label = f"  {item['provider']:<9} {window:<3}"
                suffix = f"{percent:>5g}%  reset {item['resets_at'][:16] if item['resets_at'] else 'unknown'}"
                _safe_print(f"{label} {_bar(percent)}  {suffix}")
                if forecast.get("status") == "exhausts_before_reset":
                    eta = forecast.get("eta_hours")
                    _safe_print(
                        _color(
                            f"             ⚠ burn {forecast.get('rate_per_hour', 0):g}%/h · "
                            f"empties in ~{eta:.1f}h, before reset ({forecast.get('hours_to_reset', 0):.1f}h)",
                            "33",
                        )
                    )
                elif forecast.get("status") == "on_track":
                    _safe_print(
                        _color(
                            f"             projected {forecast.get('forecast_percent_at_reset', 0):g}% at reset",
                            "32",
                        )
                    )
                elif forecast.get("status") in {"collecting", "insufficient_data", "insufficient_span"}:
                    _safe_print(_color("             collecting a burn baseline", "90"))
                elif forecast.get("status") == "idle":
                    _safe_print(_color("             no recent burn observed", "90"))
        else:
            _safe_print("  No quota snapshots yet. Run `tokonomy watch-limits`.")
        _safe_print("")
        if projects:
            _safe_print(_color("  TOP PROJECTS", "1;37"))
            for project in projects:
                _safe_print(
                    f"  {project['project'][:34]:<34} {project['sessions']:>4} sessions  "
                    f"{compact(project['uncached']):>7} in  {compact(project['output']):>7} out  "
                    f"{money(project['cost']):>9}"
                )
            _safe_print("")
        _safe_print(_color("  COMMANDS", "1;37"))
        _safe_print("  tokonomy web          open the local dashboard in a browser")
        _safe_print("  tokonomy digest       weekly summary with burn forecast")
        _safe_print("  tokonomy mcp          expose usage tools to your coding agent")
        _safe_print("  tokonomy history      browse observed quota periods")
        _safe_print("")
        _safe_print(_color(f"  Database  {data_dir / 'tokonomy.sqlite3'}", "90"))
        return 0
    finally:
        store.close()


def status_payload(data_dir: Path) -> dict:
    store = Store(data_dir / "tokonomy.sqlite3")
    try:
        return {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "version": __version__,
            "schema_version": SCHEMA_VERSION,
            "summary": metrics.summary(store.connection),
            "quota": metrics.quota(store.connection),
            "coverage": metrics.coverage(store.connection),
        }
    finally:
        store.close()


def print_digest(data_dir: Path, days: int, as_json: bool = False) -> int:
    store = Store(data_dir / "tokonomy.sqlite3")
    try:
        report = metrics.digest(store.connection, days)
    finally:
        store.close()
    if as_json:
        print(json.dumps(report, indent=2, default=str))
        return 0
    current = report["current"]
    previous = report["previous"]

    def delta(key: str) -> str:
        now = current.get(key) or 0
        before = previous.get(key) or 0
        if not before:
            return ""
        change = (now - before) / before * 100
        return f" ({change:+.0f}%)"

    print(f"TOKONOMY · last {days} days")
    print(f"  Sessions   {current['sessions']:,}{delta('sessions')}")
    print(f"  Uncached   {compact(current['uncached'])}{delta('uncached')}")
    print(f"  Cached     {compact(current['cached'])}{delta('cached')}")
    print(f"  Output     {compact(current['output'])}{delta('output')}")
    print(f"  Cache hit  {pct(current['cache_hit'])}")
    print(f"  Est. spend {money(current['cost'])}  ({pct(current['cost_coverage'])} priceable)")
    if report["projects"]:
        print("  Projects   " + ", ".join(
            f"{item['project']} ({compact(item['uncached'])} in)" for item in report["projects"]
        ))
    if report["alerts"]:
        print("  Alerts")
        for item in report["alerts"]:
            forecast = item["forecast"]
            print(
                f"    ⚠ {item['provider']} {_window_label(item['window_seconds'])} "
                f"{item['used_percent']:g}% · {forecast.get('status')} "
                f"(burn {forecast.get('rate_per_hour', 0):g}%/h)"
            )
    else:
        print("  Alerts     none")
    return 0


def print_forecast(data_dir: Path, as_json: bool = False) -> int:
    store = Store(data_dir / "tokonomy.sqlite3")
    try:
        rows = metrics.quota(store.connection)
    finally:
        store.close()
    if as_json:
        print(json.dumps(rows, indent=2, default=str))
        return 0
    if not rows:
        print("No quota snapshots. Run `tokonomy watch-limits`.")
        return 0
    print("provider  window  used   rate      ETA      reset     status")
    for item in rows:
        forecast = item["forecast"]
        eta = forecast.get("eta_hours")
        hours = forecast.get("hours_to_reset")
        eta_text = f"{eta:.1f}h" if isinstance(eta, (int, float)) else "—"
        reset_text = f"{hours:.1f}h" if isinstance(hours, (int, float)) else "—"
        print(
            f"{item['provider']:<9} {_window_label(item['window_seconds']):<6} "
            f"{item['used_percent']:>4g}%  "
            f"{forecast.get('rate_per_hour', 0):>6g}%/h  "
            f"{eta_text:>7}  {reset_text:>7}  "
            f"{forecast.get('status', 'unknown')}"
        )
    return 0


def list_sources(data_dir: Path, as_json: bool = False) -> int:
    store = Store(data_dir / "tokonomy.sqlite3")
    try:
        coverage = metrics.coverage(store.connection)
    finally:
        store.close()
    if as_json:
        print(json.dumps(coverage, indent=2, default=str))
        return 0
    print("source       enabled  sessions  events  files  basis    status")
    for row in coverage["sources"]:
        enabled = "yes" if _source_enabled(data_dir, row["source"]) else "no"
        print(
            f"{row['source']:<12} {enabled:<7} {row['sessions']:>8} {row['events']:>7} "
            f"{row['files']:>6}  {row['basis']:<8} {row['status']}"
        )
    return 0


def _source_enabled(data_dir: Path, source: str) -> bool:
    store = Store(data_dir / "tokonomy.sqlite3")
    try:
        return store.source_enabled(source)
    finally:
        store.close()


def set_source(data_dir: Path, source: str, enabled: bool) -> int:
    store = Store(data_dir / "tokonomy.sqlite3")
    try:
        store.set_source_enabled(source, enabled)
        print(f"{source}: {'enabled' if enabled else 'paused'}")
    finally:
        store.close()
    return 0


def delete_data(data_dir: Path, source: str | None, all_data: bool, assume_yes: bool) -> int:
    if not assume_yes:
        print("Refusing to delete without --yes. This cannot be undone.")
        return 2
    store = Store(data_dir / "tokonomy.sqlite3")
    try:
        if all_data:
            store.delete_all()
            print("Deleted all imported usage data. Source files were not touched.")
        elif source:
            counts = store.delete_source(source)
            print(f"Deleted {source}: {sum(counts.values()):,} rows across {len(counts)} tables.")
        else:
            print("Choose --source <name> or --all.")
            return 2
    finally:
        store.close()
    return 0


def export(command: str, path: Path, data_dir: Path) -> int:
    store = Store(data_dir / "tokonomy.sqlite3")
    try:
        if path.suffix.lower() in {".html", ".htm"}:
            from tokonomy.web import export_html

            export_html(store, path)
            print(f"Exported dashboard: {path}")
        else:
            from tokonomy.exporting import export as export_jsonl

            export_jsonl(store.connection, path)
            print(f"Exported: {path}")
    except FileExistsError:
        print("Output already exists; choose a new filename.", file=sys.stderr)
        return 2
    finally:
        store.close()
    return 0


def doctor(data_dir: Path) -> int:
    import sqlite3

    from tokonomy.diagnostics import audit

    path = data_dir / "tokonomy.sqlite3"
    connection = sqlite3.connect(path.as_uri() + "?mode=ro", uri=True)
    connection.row_factory = sqlite3.Row
    try:
        rows = audit(connection)
        for name, state, detail in rows:
            print(f"{state.upper():7} | {name} | {detail}")
        return 1 if any(state in ("warning", "error") for _, state, _ in rows) else 0
    finally:
        connection.close()


def main(argv: list[str] | None = None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        try:
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        except (OSError, ValueError):
            pass
    parser = argparse.ArgumentParser(prog="tokonomy")
    parser.add_argument("--version", action="version", version=__version__)
    subparsers = parser.add_subparsers(dest="command")

    scan_parser = subparsers.add_parser("scan", help="scan local session metadata")
    scan_parser.add_argument("--data-dir", type=Path, default=default_data_dir())
    scan_parser.add_argument("--force", action="store_true", help="re-read every source file")

    watch_parser = subparsers.add_parser("watch-limits", help="poll and save Codex plan limit snapshots")
    watch_parser.add_argument("--data-dir", type=Path, default=default_data_dir())
    watch_parser.add_argument("--interval", type=int, default=120, help="poll interval in seconds (minimum 30)")

    history_parser = subparsers.add_parser("history", help="show observed historical provider limit periods")
    history_parser.add_argument("--data-dir", type=Path, default=default_data_dir())
    history_parser.add_argument("--all", action="store_true", help="show all recorded periods")

    dashboard_parser = subparsers.add_parser("dashboard", help="show the local usage overview")
    dashboard_parser.add_argument("--data-dir", type=Path, default=default_data_dir())
    dashboard_parser.add_argument("--no-refresh", action="store_true", help="do not scan source files first")

    reset_parser = subparsers.add_parser("resets", help="list observed quota drops or label a reset")
    reset_parser.add_argument("--mark", type=int, help="row ID of an observed transition")
    reset_parser.add_argument("--reason", choices=["user-credit", "scheduled", "unknown"], default="unknown")

    collector_parser = subparsers.add_parser("collector", help="background collection")
    collector_parser.add_argument("action", choices=["start", "stop", "status", "run"])

    group_parser = subparsers.add_parser("group", help="manage explicit work groups")
    group_parser.add_argument("action", choices=["list", "assign", "remove"])
    group_parser.add_argument("--name")
    group_parser.add_argument("--source", choices=["codex", "claude-code"])
    group_parser.add_argument("--session")

    period_parser = subparsers.add_parser("period", help="recorded usage and largest contributors")
    period_parser.add_argument("--source", choices=["codex", "claude-code"], default="codex")
    period_parser.add_argument("--hours", type=int, default=24)

    export_parser = subparsers.add_parser("export", help="export metadata JSONL or a static HTML dashboard")
    export_parser.add_argument("path", type=Path)
    export_parser.add_argument("--data-dir", type=Path, default=default_data_dir())

    doctor_parser = subparsers.add_parser("doctor", help="read-only data quality checks")
    doctor_parser.add_argument("--data-dir", type=Path, default=default_data_dir())

    sources_parser = subparsers.add_parser("sources", help="list or toggle data sources")
    sources_parser.add_argument("--enable")
    sources_parser.add_argument("--disable")
    sources_parser.add_argument("--json", action="store_true")
    sources_parser.add_argument("--data-dir", type=Path, default=default_data_dir())

    delete_parser = subparsers.add_parser("delete", help="delete imported data, never source files")
    delete_parser.add_argument("--source")
    delete_parser.add_argument("--all", action="store_true")
    delete_parser.add_argument("--yes", action="store_true")
    delete_parser.add_argument("--data-dir", type=Path, default=default_data_dir())

    digest_parser = subparsers.add_parser("digest", help="weekly summary and burn forecast")
    digest_parser.add_argument("--days", type=int, default=7)
    digest_parser.add_argument("--json", action="store_true")
    digest_parser.add_argument("--data-dir", type=Path, default=default_data_dir())

    forecast_parser = subparsers.add_parser("forecast", help="quota burn rate and projected exhaustion")
    forecast_parser.add_argument("--json", action="store_true")
    forecast_parser.add_argument("--data-dir", type=Path, default=default_data_dir())

    status_parser = subparsers.add_parser("status", help="machine-readable usage and quota status")
    status_parser.add_argument("--json", action="store_true")
    status_parser.add_argument("--data-dir", type=Path, default=default_data_dir())

    web_parser = subparsers.add_parser("web", help="serve the local dashboard")
    web_parser.add_argument("--port", type=int, default=8765)
    web_parser.add_argument("--no-open", action="store_true")
    web_parser.add_argument("--data-dir", type=Path, default=default_data_dir())

    mcp_parser = subparsers.add_parser("mcp", help="run the MCP stdio server for coding agents")
    mcp_parser.add_argument("--data-dir", type=Path, default=default_data_dir())

    args = parser.parse_args(argv)
    data_dir = getattr(args, "data_dir", default_data_dir())

    if args.command in ("group", "period"):
        from tokonomy.work import groups, period_report

        if args.command == "group" and args.action != "list" and (
            not args.source or not args.session or (args.action == "assign" and not args.name)
        ):
            parser.error("assign requires --name --source --session; remove requires --source --session")
        if args.command == "period" and args.hours <= 0:
            parser.error("--hours must be positive")
        store = Store(default_data_dir() / "tokonomy.sqlite3")
        try:
            if args.command == "group":
                groups(store, args.action, args.name, args.source, args.session)
            else:
                period_report(store, args.source, args.hours)
        finally:
            store.close()
        return 0

    if args.command == "resets":
        store = Store(default_data_dir() / "tokonomy.sqlite3")
        try:
            connection = store.connection
            if not connection.execute(
                "SELECT 1 FROM sqlite_master WHERE name='quota_transitions'"
            ).fetchone():
                print("No observed transitions yet.")
                return 0
            if args.mark is not None:
                connection.execute(
                    "UPDATE quota_transitions SET reason=? WHERE rowid=?",
                    ("user-labelled:" + args.reason, args.mark),
                )
            for row in connection.execute(
                "SELECT rowid,provider,window_seconds,observed_at,previous_percent,current_percent,reason "
                "FROM quota_transitions ORDER BY observed_at DESC LIMIT 50"
            ):
                print(" | ".join(str(value) for value in row))
        finally:
            store.close()
        return 0

    if args.command == "collector":
        from tokonomy.collector import control

        control(default_data_dir(), args.action)
        return 0

    if args.command is None:
        from tokonomy.tui import TokonomyApp

        TokonomyApp(default_data_dir()).run()
        return 0
    if args.command == "scan":
        return collect(args.data_dir, force=args.force)
    if args.command == "watch-limits":
        if args.interval < 30:
            parser.error("--interval must be at least 30 seconds")
        return watch_limits(args.data_dir, args.interval)
    if args.command == "history":
        return show_history(args.data_dir, args.all)
    if args.command == "dashboard":
        return dashboard(args.data_dir, refresh=not args.no_refresh)
    if args.command == "doctor":
        return doctor(data_dir)
    if args.command == "export":
        return export(args.command, args.path, data_dir)
    if args.command == "sources":
        if args.enable:
            return set_source(data_dir, args.enable, True)
        if args.disable:
            return set_source(data_dir, args.disable, False)
        return list_sources(data_dir, args.json)
    if args.command == "delete":
        return delete_data(data_dir, args.source, args.all, args.yes)
    if args.command == "digest":
        if args.days <= 0:
            parser.error("--days must be positive")
        return print_digest(data_dir, args.days, args.json)
    if args.command == "forecast":
        return print_forecast(data_dir, args.json)
    if args.command == "status":
        payload = status_payload(data_dir)
        if args.json:
            print(json.dumps(payload, indent=2, default=str))
        else:
            current = payload["summary"]
            print(
                f"tokonomy {payload['version']} · {current['sessions']:,} sessions · "
                f"{compact(current['uncached'])} uncached · {pct(current['cache_hit'])} cache · "
                f"{money(current['cost'])} est."
            )
        return 0
    if args.command == "web":
        from tokonomy.web import serve

        return serve(args.data_dir, port=args.port, open_browser=not args.no_open)
    if args.command == "mcp":
        from tokonomy.mcp_server import run

        return run(data_dir)
    return 2
