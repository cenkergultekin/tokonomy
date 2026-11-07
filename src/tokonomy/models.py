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
class SourceStatus:
    source: str
    discovered_files: int
    scanned_files: int
    imported_sessions: int
    errors: int
