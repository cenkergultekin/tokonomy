from dataclasses import dataclass


@dataclass(frozen=True)
class Session:
    source: str
    session_id: str
    started_at: str | None = None
    last_seen_at: str | None = None
    model: str | None = None
    input_tokens: int | None = None
    output_tokens: int | None = None
    cached_input_tokens: int | None = None
    cache_write_tokens: int | None = None
    cost_usd: float | None = None
    cost_is_reported: bool = False
    source_file: str | None = None
    model_usage: tuple["ModelUsage", ...] = ()
    usage_events: tuple["UsageEvent", ...] = ()
    limit_snapshots: tuple["LimitSnapshot", ...] = ()


@dataclass(frozen=True)
class ModelUsage:
    model: str
    input_tokens: int | None = None
    output_tokens: int | None = None
    cached_input_tokens: int | None = None
    cache_write_tokens: int | None = None
    cost_usd: float | None = None
    cost_is_reported: bool = False


@dataclass(frozen=True)
class UsageEvent:
    event_id: str
    occurred_at: str
    model: str | None
    input_tokens: int | None
    output_tokens: int | None
    cached_input_tokens: int | None = None
    cache_write_tokens: int | None = None


@dataclass(frozen=True)
class SourceStatus:
    source: str
    discovered_files: int
    scanned_files: int
    imported_sessions: int
    errors: int


@dataclass(frozen=True)
class LimitSnapshot:
    provider: str
    limit_id: str
    plan_type: str | None
    window_seconds: int
    used_percent: float
    captured_at: str
    resets_at: str | None = None
    exhausted: bool = False
    input_tokens: int | None = None
    output_tokens: int | None = None
    session_count: int | None = None
    sessions_with_usage: int | None = None
    average_input_tokens_per_session: float | None = None
    average_output_tokens_per_session: float | None = None
    source_event_id: str | None = None
