import argparse
import os
import shutil
import sys
import time
from dataclasses import replace
from pathlib import Path

from tokonomy import __version__
from tokonomy.sources import claude, codex
from tokonomy.providers.codex_limits import read_rate_limits
from tokonomy.store import Store


def default_data_dir() -> Path:
    base = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local"))
    directory = base / "tokonomy"
    pointer = directory / "active-directory.txt"
    return Path(pointer.read_text(encoding="utf-8").strip()) if pointer.exists() else directory


def collect(data_dir: Path, store: Store | None = None, force: bool = False, quiet: bool = False) -> int:
    home = Path.home()
    sources = (
        ("Codex", codex.discover(Path(os.environ.get("CODEX_HOME", home / ".codex")) / "sessions"), codex.read_session),
        ("Claude Code", claude.discover(Path(os.environ.get("CLAUDE_CONFIG_DIR", home / ".claude")) / "projects"), claude.read_session),
    )
    owns_store = store is None
    store = store or Store(data_dir / "tokonomy.sqlite3")
    try:
        for label, files, parser in sources:
            if label == "Claude Code":
                changed = force or any(not store.has_scanned_file('claude-code', p) for p in files)
                if not changed: continue
                from tokonomy.reconcile import reconcile
                from tokonomy.context import enrich
                parsed = []
                failures = 0
                for path in files:
                    try:
                        session = parser(path)
                        if session: parsed.append(session)
                    except (OSError, ValueError, EOFError): failures += 1
                if failures:
                    if not quiet: print(f'Claude reconciliation deferred: {failures} unreadable files')
                    continue
                from tokonomy.sources.jsonl import iter_jsonl
                for raw in parsed:
                    store.connection.execute('INSERT OR IGNORE INTO session_sources VALUES (?,?,?)',(raw.source,raw.session_id,raw.source_file))
                    store.connection.execute('DELETE FROM usage_origins WHERE source=? AND source_file=?',(raw.source,raw.source_file))
                    for ordinal, record in enumerate(iter_jsonl(Path(raw.source_file)),1):
                        message=record.get('message')
                        if record.get('type')=='assistant' and isinstance(message,dict) and message.get('id'):
                            store.connection.execute('INSERT OR IGNORE INTO usage_origins VALUES (?,?,?,?)',(raw.source,message['id'],raw.source_file,ordinal))
                for session in reconcile(parsed):
                    store.upsert_session(session)
                    enrich(store, session, Path(session.source_file))
                for path in files: store.mark_file_scanned('claude-code', path)
                if not quiet: print(f'Claude Code: reconciled {len(parsed)} files by session and message ID')
                continue
            errors = imported = 0
            scanned = 0
            for path in files:
                if not force and store.has_scanned_file(label.lower().replace(" ", "-"), path):
                    continue
                try:
                    session = parser(path)
                    if session:
                        store.upsert_session(session)
                        from tokonomy.context import enrich
                        enrich(store, session, path)
                        imported += 1
                    store.mark_file_scanned(label.lower().replace(" ", "-"), path)
                    scanned += 1
                except (OSError, ValueError, EOFError):
                    errors += 1
            if not quiet: print(f"{label}: discovered={len(files)} scanned={scanned} changed_sessions={imported} errors={errors}")
        from tokonomy.sources import hermes
        from datetime import datetime, timezone
        hermes_path = Path(os.environ.get('HERMES_HOME', Path(os.environ.get('LOCALAPPDATA',home/'AppData/Local'))/'hermes'))/'state.db'
        try:
            count=hermes.collect(store,hermes_path)
            state='Imported' if hermes_path.exists() else 'Not found'
            detail=f'{count} sessions; session totals only'
        except (OSError, ValueError, __import__('sqlite3').Error) as error:
            state='Unavailable'; detail=type(error).__name__
        store.connection.execute('INSERT OR REPLACE INTO source_health VALUES (?,?,?,?)',('hermes',datetime.now(timezone.utc).isoformat(),state,detail))
        if not quiet: print(f'Hermes: {state} / {detail}')
        if not quiet: print(f"Indexed sessions: {store.count_sessions()}")
        if not quiet: print(f"Database: {data_dir / 'tokonomy.sqlite3'}")
    finally:
        if owns_store:
            store.close()
    return 0


def watch_limits(data_dir: Path, interval: int) -> int:
    store = Store(data_dir / "tokonomy.sqlite3")
    print(f"Watching provider limits every {interval}s. Stop with Ctrl+C.")
    try:
        while True:
            collect(data_dir, store)
            try:
                snapshots = read_rate_limits()
                for snapshot in snapshots:
                    usage = store.window_usage("codex", snapshot.window_seconds, snapshot.captured_at, snapshot.resets_at)
                    snapshot = replace(snapshot, **usage)
                    store.save_limit_snapshot(snapshot)
                    window = "5h" if snapshot.window_seconds == 5 * 3600 else "7d" if snapshot.window_seconds == 7 * 86400 else f"{snapshot.window_seconds}s"
                    print(f"codex {snapshot.plan_type or 'plan unknown'} {snapshot.limit_id} {window}: {snapshot.used_percent}% resets={snapshot.resets_at or 'unknown'}")
                store.connection.commit()
            except (OSError, RuntimeError, TimeoutError, ValueError) as error:
                print(f"Codex limit snapshot unavailable: {type(error).__name__}")
            time.sleep(interval)
    except KeyboardInterrupt:
        return 0
    finally:
        store.close()


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
            from datetime import datetime, timedelta
            reset_at = datetime.fromisoformat(row["resets_at"])
            period_start = (reset_at - timedelta(seconds=row["window_seconds"])).isoformat()
            totals = store.connection.execute(
                """SELECT SUM(input_tokens), SUM(output_tokens), COUNT(DISTINCT session_id)
                   FROM usage_events WHERE source = ? AND occurred_at >= ? AND occurred_at <= ?""",
                (row["provider"], period_start, row["observed_at"]),
            ).fetchone()
            window = "5h" if row["window_seconds"] == 18000 else "7d" if row["window_seconds"] == 604800 else f"{row['window_seconds']}s"
            reset = row["resets_at"].replace("T", " ").split("+", 1)[0]
            first = row["first_seen"].replace("T", " ")[5:16]
            last = row["last_seen"].replace("T", " ")[5:16]
            percent = f"{row['first_percent']:g}/{row['peak_percent']:g}/{row['last_percent']:g}%"
            tokens = f"{totals[0] or 0:,}/{totals[1] or 0:,}"
            sessions = totals[2]
            print(f"{row['provider']:<9} {window:<6}  {reset:<22} {first}-{last}  {percent:>12}  {row['observations']:>12,}  {tokens:>26}  {sessions if sessions is not None else 'unknown'}")
        return 0
    finally:
        store.close()


def _color(text: str, code: str) -> str:
    if not sys.stdout.isatty() or os.environ.get("NO_COLOR"):
        return text
    return f"\033[{code}m{text}\033[0m"


def _safe_print(text: str) -> None:
    if sys.stdout.encoding and sys.stdout.encoding.lower().replace("-", "") in {"utf8", "utf8sig"}:
        print(text)
        return
    fallback = text.translate(str.maketrans({"─": "-", "█": "#", "░": ".", "·": "|", "—": "-"}))
    print(fallback.encode(sys.stdout.encoding or "ascii", errors="replace").decode(sys.stdout.encoding or "ascii"))


def _bar(percent: float, width: int = 24) -> str:
    filled = max(0, min(width, round(percent * width / 100)))
    color = "32" if percent < 60 else "33" if percent < 85 else "31"
    return _color("█" * filled, color) + _color("░" * (width - filled), "90")


def _format_tokens(value: int | None) -> str:
    return f"{value:,}" if value is not None else "—"


def dashboard(data_dir: Path, refresh: bool = True) -> int:
    if refresh:
        collect(data_dir)
    store = Store(data_dir / "tokonomy.sqlite3")
    try:
        width = shutil.get_terminal_size((90, 24)).columns
        line = "─" * min(76, max(48, width - 4))
        _safe_print(_color(" TOKONOMY ", "1;38;2;116;192;252") + _color("LOCAL AI USAGE", "90"))
        _safe_print(_color(line, "90"))
        session_count = store.count_sessions()
        codex_totals = store.connection.execute(
            "SELECT SUM(input_tokens), SUM(output_tokens) FROM usage_events WHERE source='codex'"
        ).fetchone()
        claude_totals = store.connection.execute(
            "SELECT SUM(input_tokens), SUM(output_tokens) FROM sessions WHERE source='claude-code'"
        ).fetchone()
        codex_sessions = store.connection.execute("SELECT COUNT(*) FROM sessions WHERE source='codex'").fetchone()[0]
        claude_sessions = store.connection.execute("SELECT COUNT(*) FROM sessions WHERE source='claude-code'").fetchone()[0]
        _safe_print(f"  Sessions tracked    {_color(f'{session_count:,}', '1;37')}")
        _safe_print(f"  By source            Codex {codex_sessions:,}  |  Claude Code {claude_sessions:,}")
        _safe_print(f"  Codex exact tokens   {_color(_format_tokens(codex_totals[0]), '36')} in  /  {_color(_format_tokens(codex_totals[1]), '35')} out")
        _safe_print(f"  Claude session sum   {_color(_format_tokens(claude_totals[0]), '36')} in  /  {_color(_format_tokens(claude_totals[1]), '35')} out")
        _safe_print("")
        latest = store.connection.execute(
            """SELECT s.* FROM limit_snapshots s
               JOIN (SELECT provider, limit_id, window_seconds, MAX(captured_at) AS latest
                     FROM limit_snapshots GROUP BY provider, limit_id, window_seconds) l
                 ON s.provider=l.provider AND s.limit_id=l.limit_id
                AND s.window_seconds=l.window_seconds AND s.captured_at=l.latest
               ORDER BY s.provider, s.window_seconds"""
        ).fetchall()
        _safe_print(_color("  CURRENT LIMITS", "1;37"))
        if latest:
            for row in latest:
                window = "5h" if row["window_seconds"] == 18000 else "7d" if row["window_seconds"] == 604800 else f"{row['window_seconds']}s"
                reset = row["resets_at"] or "reset unknown"
                if row["resets_at"]:
                    reset = row["resets_at"].replace("T", " ").split("+", 1)[0] + " UTC"
                percent = row["used_percent"]
                _safe_print(f"  {row['provider']:<9} {window:<3} {_bar(percent)}  {percent:>5g}%  resets {reset}")
        else:
            _safe_print("  No quota snapshots yet. Run `tokonomy watch-limits` to collect them.")
        _safe_print("")
        _safe_print(_color("  COMMANDS", "1;37"))
        _safe_print("  scan                 Import new session records")
        _safe_print("  history [--all]      Browse observed quota periods")
        _safe_print("  watch-limits         Keep provider limits refreshed")
        _safe_print("")
        _safe_print(_color(f"  Database  {data_dir / 'tokonomy.sqlite3'}", "90"))
        return 0
    finally:
        store.close()


def main() -> int:
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
    reset_parser = subparsers.add_parser('resets', help='list observed quota drops or label a reset')
    reset_parser.add_argument('--mark', type=int, help='row ID of an observed transition')
    reset_parser.add_argument('--reason', choices=['user-credit','scheduled','unknown'], default='unknown')
    collector_parser = subparsers.add_parser('collector', help='background collection')
    collector_parser.add_argument('action', choices=['start','stop','status','run'])
    group_parser = subparsers.add_parser('group', help='manage explicit work groups')
    group_parser.add_argument('action', choices=['list','assign','remove'])
    group_parser.add_argument('--name')
    group_parser.add_argument('--source', choices=['codex','claude-code'])
    group_parser.add_argument('--session')
    period_parser = subparsers.add_parser('period', help='recorded usage and largest contributors')
    period_parser.add_argument('--source', choices=['codex','claude-code'], default='codex')
    period_parser.add_argument('--hours', type=int, default=24)
    args = parser.parse_args()
    if args.command == 'collector':
        from tokonomy.collector import control
        control(default_data_dir(), args.action)
        return 0
    if args.command in ('group','period'):
        from tokonomy.work import groups, period_report
        if args.command=='group' and args.action!='list' and (not args.source or not args.session or (args.action=='assign' and not args.name)):
            parser.error('assign requires --name --source --session; remove requires --source --session')
        if args.command=='period' and args.hours<=0: parser.error('--hours must be positive')
        store=Store(default_data_dir()/'tokonomy.sqlite3')
        try:
            if args.command=='group': groups(store,args.action,args.name,args.source,args.session)
            else: period_report(store,args.source,args.hours)
        finally: store.close()
        return 0
    if args.command == 'resets':
        store = Store(default_data_dir() / 'tokonomy.sqlite3')
        try:
            c = store.connection
            if not c.execute("SELECT 1 FROM sqlite_master WHERE name='quota_transitions'").fetchone():
                print('No observed transitions yet.'); return 0
            if args.mark is not None:
                c.execute('UPDATE quota_transitions SET reason=? WHERE rowid=?', ('user-labelled:'+args.reason,args.mark))
            for row in c.execute('SELECT rowid,provider,window_seconds,observed_at,previous_percent,current_percent,reason FROM quota_transitions ORDER BY observed_at DESC LIMIT 50'):
                print(' | '.join(str(v) for v in row))
        finally: store.close()
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
    return 2
