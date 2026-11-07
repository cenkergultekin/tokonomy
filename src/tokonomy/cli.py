import argparse
import os
import time
from dataclasses import replace
from pathlib import Path

from tokonomy import __version__
from tokonomy.sources import claude, codex
from tokonomy.providers.codex_limits import read_rate_limits
from tokonomy.store import Store


def default_data_dir() -> Path:
    base = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local"))
    return base / "tokonomy"


def collect(data_dir: Path, store: Store | None = None, force: bool = False) -> int:
    home = Path.home()
    sources = (
        ("Codex", codex.discover(Path(os.environ.get("CODEX_HOME", home / ".codex")) / "sessions"), codex.read_session),
        ("Claude Code", claude.discover(Path(os.environ.get("CLAUDE_CONFIG_DIR", home / ".claude")) / "projects"), claude.read_session),
    )
    owns_store = store is None
    store = store or Store(data_dir / "tokonomy.sqlite3")
    try:
        for label, files, parser in sources:
            errors = imported = 0
            scanned = 0
            for path in files:
                if not force and store.has_scanned_file(label.lower().replace(" ", "-"), path):
                    continue
                try:
                    session = parser(path)
                    if session:
                        store.upsert_session(session)
                        imported += 1
                    store.mark_file_scanned(label.lower().replace(" ", "-"), path)
                    scanned += 1
                except (OSError, ValueError, EOFError):
                    errors += 1
            print(f"{label}: discovered={len(files)} scanned={scanned} changed_sessions={imported} errors={errors}")
        print(f"Indexed sessions: {store.count_sessions()}")
        print(f"Database: {data_dir / 'tokonomy.sqlite3'}")
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


def main() -> int:
    parser = argparse.ArgumentParser(prog="tokonomy")
    parser.add_argument("--version", action="version", version=__version__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    scan_parser = subparsers.add_parser("scan", help="scan local session metadata")
    scan_parser.add_argument("--data-dir", type=Path, default=default_data_dir())
    scan_parser.add_argument("--force", action="store_true", help="re-read every source file")
    watch_parser = subparsers.add_parser("watch-limits", help="poll and save Codex plan limit snapshots")
    watch_parser.add_argument("--data-dir", type=Path, default=default_data_dir())
    watch_parser.add_argument("--interval", type=int, default=120, help="poll interval in seconds (minimum 30)")
    args = parser.parse_args()
    if args.command == "scan":
        return collect(args.data_dir, force=args.force)
    if args.command == "watch-limits":
        if args.interval < 30:
            parser.error("--interval must be at least 30 seconds")
        return watch_limits(args.data_dir, args.interval)
    return 2
