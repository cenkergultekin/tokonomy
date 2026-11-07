import sqlite3
from pathlib import Path

from tokonomy.models import ModelUsage, Session


SCHEMA = """
CREATE TABLE IF NOT EXISTS work_assignments(source TEXT, session_id TEXT, name TEXT NOT NULL, PRIMARY KEY(source,session_id));
CREATE TABLE IF NOT EXISTS session_context (source TEXT, session_id TEXT, project TEXT, cwd TEXT, parent_id TEXT, branch TEXT, source_file TEXT, PRIMARY KEY(source,session_id));
CREATE TABLE IF NOT EXISTS session_events (source TEXT, session_id TEXT, line INTEGER, kind TEXT, timestamp TEXT, source_file TEXT, PRIMARY KEY(source,session_id,line,kind));
CREATE TABLE IF NOT EXISTS source_health (source TEXT PRIMARY KEY, observed_at TEXT, status TEXT, detail TEXT);

CREATE TABLE IF NOT EXISTS usage_origins (
 source TEXT, event_id TEXT, source_file TEXT, record_number INTEGER,
 PRIMARY KEY(source,event_id,source_file,record_number));
CREATE INDEX IF NOT EXISTS origins_event ON usage_origins(source,event_id);
CREATE TABLE IF NOT EXISTS session_sources (
 source TEXT, session_id TEXT, source_file TEXT,
 PRIMARY KEY(source,session_id,source_file));

CREATE TABLE IF NOT EXISTS sessions (
  source TEXT NOT NULL,
  session_id TEXT NOT NULL,
  started_at TEXT,
  last_seen_at TEXT,
  model TEXT,
  input_tokens INTEGER,
  output_tokens INTEGER,
  cached_input_tokens INTEGER,
  cache_write_tokens INTEGER,
  cost_usd REAL,
  cost_is_reported INTEGER NOT NULL DEFAULT 0,
  source_file TEXT,
  updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (source, session_id)
);
CREATE INDEX IF NOT EXISTS sessions_last_seen ON sessions(last_seen_at);
CREATE TABLE IF NOT EXISTS model_usage (
  source TEXT NOT NULL,
  session_id TEXT NOT NULL,
  model TEXT NOT NULL,
  input_tokens INTEGER,
  output_tokens INTEGER,
  cached_input_tokens INTEGER,
  cache_write_tokens INTEGER,
  cost_usd REAL,
  cost_is_reported INTEGER NOT NULL DEFAULT 0,
  PRIMARY KEY (source, session_id, model),
  FOREIGN KEY (source, session_id) REFERENCES sessions(source, session_id) ON DELETE CASCADE
);
CREATE TABLE IF NOT EXISTS limit_snapshots (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  provider TEXT NOT NULL,
  limit_id TEXT NOT NULL,
  plan_type TEXT,
  window_seconds INTEGER NOT NULL,
  used_percent REAL NOT NULL,
  captured_at TEXT NOT NULL,
  resets_at TEXT,
  exhausted INTEGER NOT NULL,
  input_tokens INTEGER,
  output_tokens INTEGER,
  session_count INTEGER,
  sessions_with_usage INTEGER,
  average_input_tokens_per_session REAL,
  average_output_tokens_per_session REAL,
  source_event_id TEXT
);
CREATE INDEX IF NOT EXISTS limit_snapshots_window ON limit_snapshots(provider, limit_id, window_seconds, captured_at);
CREATE TABLE IF NOT EXISTS limit_events (
  provider TEXT NOT NULL,
  limit_id TEXT NOT NULL,
  window_seconds INTEGER NOT NULL,
  resets_at TEXT,
  period_key TEXT NOT NULL,
  reached_at TEXT NOT NULL,
  plan_type TEXT,
  input_tokens INTEGER,
  output_tokens INTEGER,
  session_count INTEGER,
  sessions_with_usage INTEGER,
  average_input_tokens_per_session REAL,
  average_output_tokens_per_session REAL,
  UNIQUE(provider, limit_id, window_seconds, period_key)
);
CREATE TABLE IF NOT EXISTS usage_events (
  source TEXT NOT NULL,
  session_id TEXT NOT NULL,
  event_id TEXT NOT NULL,
  occurred_at TEXT NOT NULL,
  model TEXT,
  input_tokens INTEGER,
  output_tokens INTEGER,
  cached_input_tokens INTEGER,
  cache_write_tokens INTEGER,
  PRIMARY KEY (source, session_id, event_id),
  FOREIGN KEY (source, session_id) REFERENCES sessions(source, session_id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS usage_events_time ON usage_events(source, occurred_at);
CREATE TABLE IF NOT EXISTS source_files (
  source TEXT NOT NULL,
  file_path TEXT NOT NULL,
  size_bytes INTEGER NOT NULL,
  modified_ns INTEGER NOT NULL,
  scanned_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (source, file_path)
);
"""


class Store:
    def __init__(self, path: Path):
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.connection = sqlite3.connect(path, timeout=30)
        self.connection.row_factory = sqlite3.Row
        self.connection.execute("PRAGMA journal_mode=WAL")
        self.connection.executescript(SCHEMA)
        snapshot_columns = {row["name"] for row in self.connection.execute("PRAGMA table_info(limit_snapshots)")}
        for name, declaration in (
            ("sessions_with_usage", "INTEGER"),
            ("average_input_tokens_per_session", "REAL"),
            ("average_output_tokens_per_session", "REAL"),
        ):
            if name not in snapshot_columns:
                self.connection.execute(f"ALTER TABLE limit_snapshots ADD COLUMN {name} {declaration}")
        if "source_event_id" not in snapshot_columns:
            self.connection.execute("ALTER TABLE limit_snapshots ADD COLUMN source_event_id TEXT")
        self.connection.execute("CREATE UNIQUE INDEX IF NOT EXISTS limit_snapshots_source_event ON limit_snapshots(provider, source_event_id) WHERE source_event_id IS NOT NULL")
        self.connection.execute("CREATE INDEX IF NOT EXISTS limit_snapshots_window ON limit_snapshots(provider, limit_id, window_seconds, captured_at)")
        event_columns = {row["name"] for row in self.connection.execute("PRAGMA table_info(limit_events)")}
        if "period_key" not in event_columns:
            self.connection.execute("ALTER TABLE limit_events RENAME TO limit_events_legacy")
            self.connection.execute("""CREATE TABLE limit_events (
              provider TEXT NOT NULL, limit_id TEXT NOT NULL, window_seconds INTEGER NOT NULL,
              resets_at TEXT, period_key TEXT NOT NULL, reached_at TEXT NOT NULL,
              plan_type TEXT, input_tokens INTEGER, output_tokens INTEGER, session_count INTEGER,
              sessions_with_usage INTEGER, average_input_tokens_per_session REAL,
              average_output_tokens_per_session REAL,
              UNIQUE(provider, limit_id, window_seconds, period_key))""")
            self.connection.execute("""INSERT OR IGNORE INTO limit_events
              SELECT provider, limit_id, window_seconds, resets_at,
                     COALESCE(resets_at, substr(reached_at, 1, 10)), reached_at,
                     plan_type, input_tokens, output_tokens, session_count, NULL, NULL, NULL
              FROM limit_events_legacy""")
            self.connection.execute("DROP TABLE limit_events_legacy")
        event_columns = {row["name"] for row in self.connection.execute("PRAGMA table_info(limit_events)")}
        for name, declaration in (
            ("sessions_with_usage", "INTEGER"),
            ("average_input_tokens_per_session", "REAL"),
            ("average_output_tokens_per_session", "REAL"),
        ):
            if name not in event_columns:
                self.connection.execute(f"ALTER TABLE limit_events ADD COLUMN {name} {declaration}")

    def upsert_session(self, session: Session) -> None:
        values = (
            session.source, session.session_id, session.started_at, session.last_seen_at,
            session.model, session.input_tokens, session.output_tokens,
            session.cached_input_tokens, session.cache_write_tokens, session.cost_usd,
            int(session.cost_is_reported), session.source_file,
        )
        self.connection.execute(
            """INSERT INTO sessions (
              source, session_id, started_at, last_seen_at, model, input_tokens,
              output_tokens, cached_input_tokens, cache_write_tokens, cost_usd,
              cost_is_reported, source_file
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(source, session_id) DO UPDATE SET
              started_at=COALESCE(excluded.started_at, sessions.started_at),
              last_seen_at=COALESCE(excluded.last_seen_at, sessions.last_seen_at),
              model=COALESCE(excluded.model, sessions.model),
              input_tokens=excluded.input_tokens,
              output_tokens=excluded.output_tokens,
              cached_input_tokens=excluded.cached_input_tokens,
              cache_write_tokens=excluded.cache_write_tokens,
              cost_usd=excluded.cost_usd,
              cost_is_reported=excluded.cost_is_reported,
              source_file=COALESCE(excluded.source_file, sessions.source_file),
              updated_at=CURRENT_TIMESTAMP""",
            values,
        )
        self.connection.execute(
            "DELETE FROM model_usage WHERE source = ? AND session_id = ?",
            (session.source, session.session_id),
        )
        for usage in session.model_usage:
            self.upsert_model_usage(session.source, session.session_id, usage)
        self.connection.execute(
            "DELETE FROM usage_events WHERE source = ? AND session_id = ?",
            (session.source, session.session_id),
        )
        for event in session.usage_events:
            self.connection.execute(
                """INSERT OR IGNORE INTO usage_events (
                  source, session_id, event_id, occurred_at, model, input_tokens,
                  output_tokens, cached_input_tokens, cache_write_tokens
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (session.source, session.session_id, event.event_id, event.occurred_at,
                 event.model, event.input_tokens, event.output_tokens,
                 event.cached_input_tokens, event.cache_write_tokens),
            )
        for snapshot in session.limit_snapshots:
            self.save_limit_snapshot(snapshot)

    def upsert_model_usage(self, source: str, session_id: str, usage: ModelUsage) -> None:
        self.connection.execute(
            """INSERT INTO model_usage (
              source, session_id, model, input_tokens, output_tokens,
              cached_input_tokens, cache_write_tokens, cost_usd, cost_is_reported
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(source, session_id, model) DO UPDATE SET
              input_tokens=excluded.input_tokens,
              output_tokens=excluded.output_tokens,
              cached_input_tokens=excluded.cached_input_tokens,
              cache_write_tokens=excluded.cache_write_tokens,
              cost_usd=excluded.cost_usd,
              cost_is_reported=excluded.cost_is_reported""",
            (source, session_id, usage.model, usage.input_tokens, usage.output_tokens,
             usage.cached_input_tokens, usage.cache_write_tokens, usage.cost_usd,
             int(usage.cost_is_reported)),
        )

    def count_sessions(self) -> int:
        return int(self.connection.execute("SELECT COUNT(*) FROM sessions").fetchone()[0])

    def count_events(self, source: str) -> int:
        return int(self.connection.execute("SELECT COUNT(*) FROM usage_events WHERE source = ?", (source,)).fetchone()[0])

    def save_limit_snapshot(self, snapshot) -> None:
        self.connection.execute("CREATE TABLE IF NOT EXISTS quota_transitions (provider TEXT, limit_id TEXT, window_seconds INTEGER, observed_at TEXT, previous_at TEXT, previous_percent REAL, current_percent REAL, old_reset TEXT, new_reset TEXT, reason TEXT, UNIQUE(provider,limit_id,window_seconds,observed_at))")
        previous = self.connection.execute("SELECT captured_at,used_percent,resets_at FROM limit_snapshots WHERE provider=? AND limit_id=? AND window_seconds=? AND captured_at<? ORDER BY captured_at DESC LIMIT 1", (snapshot.provider,snapshot.limit_id,snapshot.window_seconds,snapshot.captured_at)).fetchone()
        if previous and snapshot.used_percent < previous[1]:
            self.connection.execute("INSERT OR IGNORE INTO quota_transitions VALUES (?,?,?,?,?,?,?,?,?,?)", (snapshot.provider,snapshot.limit_id,snapshot.window_seconds,snapshot.captured_at,previous[0],previous[1],snapshot.used_percent,previous[2],snapshot.resets_at,'unknown'))
        row = (snapshot.provider, snapshot.limit_id, snapshot.plan_type,
               snapshot.window_seconds, snapshot.used_percent, snapshot.captured_at,
               snapshot.resets_at, int(snapshot.exhausted), snapshot.input_tokens,
               snapshot.output_tokens, snapshot.session_count)
        self.connection.execute(
            """INSERT OR IGNORE INTO limit_snapshots (
              provider, limit_id, plan_type, window_seconds, used_percent,
              captured_at, resets_at, exhausted, input_tokens, output_tokens, session_count,
              sessions_with_usage, average_input_tokens_per_session,
              average_output_tokens_per_session, source_event_id
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            row + (snapshot.sessions_with_usage, snapshot.average_input_tokens_per_session,
                   snapshot.average_output_tokens_per_session, snapshot.source_event_id),
        )
        if snapshot.exhausted:
            self.connection.execute(
                """INSERT OR IGNORE INTO limit_events (
                  provider, limit_id, window_seconds, resets_at, period_key, reached_at,
                  plan_type, input_tokens, output_tokens, session_count, sessions_with_usage,
                  average_input_tokens_per_session, average_output_tokens_per_session
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (snapshot.provider, snapshot.limit_id, snapshot.window_seconds,
                 snapshot.resets_at, snapshot.resets_at or snapshot.captured_at[:10],
                 snapshot.captured_at, snapshot.plan_type, snapshot.input_tokens,
                 snapshot.output_tokens, snapshot.session_count, snapshot.sessions_with_usage,
                 snapshot.average_input_tokens_per_session, snapshot.average_output_tokens_per_session),
            )

    def has_scanned_file(self, source: str, path: Path) -> bool:
        try:
            stat = path.stat()
        except OSError:
            return False
        row = self.connection.execute(
            "SELECT size_bytes, modified_ns FROM source_files WHERE source = ? AND file_path = ?",
            (source, str(path)),
        ).fetchone()
        return bool(row and row["size_bytes"] == stat.st_size and row["modified_ns"] == stat.st_mtime_ns)

    def mark_file_scanned(self, source: str, path: Path) -> None:
        stat = path.stat()
        self.connection.execute(
            """INSERT INTO source_files(source, file_path, size_bytes, modified_ns)
               VALUES (?, ?, ?, ?)
               ON CONFLICT(source, file_path) DO UPDATE SET
                 size_bytes=excluded.size_bytes, modified_ns=excluded.modified_ns,
                 scanned_at=CURRENT_TIMESTAMP""",
            (source, str(path), stat.st_size, stat.st_mtime_ns),
        )

    def window_usage(self, source: str, window_seconds: int, captured_at: str, resets_at: str | None) -> dict:
        from datetime import datetime, timedelta

        if not resets_at:
            return {
                "input_tokens": None, "output_tokens": None, "session_count": None,
                "sessions_with_usage": None, "average_input_tokens_per_session": None,
                "average_output_tokens_per_session": None,
            }
        end = datetime.fromisoformat(captured_at)
        reset = datetime.fromisoformat(resets_at)
        start = (reset - timedelta(seconds=window_seconds)).isoformat()
        totals = self.connection.execute(
            """SELECT SUM(input_tokens) AS input_tokens, SUM(output_tokens) AS output_tokens,
                      COUNT(DISTINCT session_id) AS sessions_with_usage
               FROM usage_events WHERE source = ? AND occurred_at >= ? AND occurred_at <= ?""",
            (source, start, captured_at),
        ).fetchone()
        sessions = self.connection.execute(
            """SELECT COUNT(*) FROM sessions WHERE source = ? AND started_at >= ? AND started_at <= ?""",
            (source, start, captured_at),
        ).fetchone()[0]
        used_sessions = int(totals["sessions_with_usage"] or 0)
        input_tokens = totals["input_tokens"]
        output_tokens = totals["output_tokens"]
        return {
            "input_tokens": int(input_tokens) if input_tokens is not None else None,
            "output_tokens": int(output_tokens) if output_tokens is not None else None,
            "session_count": int(sessions),
            "sessions_with_usage": used_sessions,
            "average_input_tokens_per_session": input_tokens / used_sessions if input_tokens is not None and used_sessions else None,
            "average_output_tokens_per_session": output_tokens / used_sessions if output_tokens is not None and used_sessions else None,
        }

    def close(self) -> None:
        self.connection.commit()
        self.connection.close()
