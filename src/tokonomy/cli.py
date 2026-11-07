import argparse
import os
from pathlib import Path

from tokonomy import __version__
from tokonomy.sources import claude, codex
from tokonomy.store import Store


def default_data_dir() -> Path:
    base = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local"))
    return base / "Tokonomy"


def collect(data_dir: Path) -> int:
    home = Path.home()
    sources = (
        ("Codex", codex.discover(Path(os.environ.get("CODEX_HOME", home / ".codex")) / "sessions"), codex.read_session),
        ("Claude Code", claude.discover(Path(os.environ.get("CLAUDE_CONFIG_DIR", home / ".claude")) / "projects"), claude.read_session),
    )
    store = Store(data_dir / "tokonomy.sqlite3")
    try:
        for label, files, parser in sources:
            errors = imported = 0
            for path in files:
                try:
                    session = parser(path)
                    if session:
                        store.upsert_session(session)
                        imported += 1
                except (OSError, ValueError, EOFError):
                    errors += 1
            print(f"{label}: files={len(files)} sessions={imported} errors={errors}")
        print(f"Total sessions: {store.count_sessions()}")
        print(f"Database: {data_dir / 'tokonomy.sqlite3'}")
    finally:
        store.close()
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(prog="tokonomy")
    parser.add_argument("--version", action="version", version=__version__)
    parser.add_argument("command", choices=("scan",), help="scan local session metadata")
    parser.add_argument("--data-dir", type=Path, default=default_data_dir())
    args = parser.parse_args()
    if args.command == "scan":
        return collect(args.data_dir)
    return 2
