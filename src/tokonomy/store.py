import sqlite3
from pathlib import Path

from tokonomy.models import ModelUsage, Session


SCHEMA = """
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
"""


class Store:
    def __init__(self, path: Path):
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.connection = sqlite3.connect(path)
        self.connection.row_factory = sqlite3.Row
        self.connection.executescript(SCHEMA)

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

    def close(self) -> None:
        self.connection.commit()
        self.connection.close()
