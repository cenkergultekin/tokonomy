from pathlib import Path
from datetime import datetime, timezone

from tokonomy.models import ModelUsage, Session
from tokonomy.sources.jsonl import iter_jsonl


def discover(root: Path) -> list[Path]:
    return sorted(root.rglob("*.jsonl")) if root.exists() else []


def read_session(path: Path) -> Session | None:
    session_id = None
    started_at = None
    last_seen_at = None
    total_input = total_output = total_cache_read = total_cache_write = None
    model_totals: dict[str, dict[str, int | float]] = {}
    for record in iter_jsonl(path):
        sid = record.get("sessionId")
        if isinstance(sid, str):
            session_id = sid
        kind = record.get("type")
        stamp = record.get("timestamp")
        if isinstance(stamp, str):
            normalized = _timestamp(stamp)
            started_at = started_at or normalized
            last_seen_at = normalized or last_seen_at
        if kind == "cost-state":
            start_ms = record.get("startTime")
            if isinstance(start_ms, (int, float)):
                started_at = datetime.fromtimestamp(start_ms / 1000, timezone.utc).isoformat()
            usage = record.get("modelUsage")
            if isinstance(usage, dict):
                # cost-state is a cumulative snapshot; replace, do not add.
                model_totals = {
                    name: values for name, values in usage.items()
                    if isinstance(name, str) and isinstance(values, dict)
                }
    if not session_id:
        return None
    by_model = []
    if model_totals:
        for name, values in model_totals.items():
            if not isinstance(values, dict):
                continue
            by_model.append(ModelUsage(
                model=name,
                input_tokens=values.get("inputTokens") if isinstance(values.get("inputTokens"), int) else None,
                output_tokens=values.get("outputTokens") if isinstance(values.get("outputTokens"), int) else None,
                cached_input_tokens=values.get("cacheReadInputTokens") if isinstance(values.get("cacheReadInputTokens"), int) else None,
                cache_write_tokens=values.get("cacheCreationInputTokens") if isinstance(values.get("cacheCreationInputTokens"), int) else None,
            ))
        total_input = sum(v.get("inputTokens", 0) for v in model_totals.values() if isinstance(v.get("inputTokens", 0), int))
        total_output = sum(v.get("outputTokens", 0) for v in model_totals.values() if isinstance(v.get("outputTokens", 0), int))
        total_cache_read = sum(v.get("cacheReadInputTokens", 0) for v in model_totals.values() if isinstance(v.get("cacheReadInputTokens", 0), int))
        total_cache_write = sum(v.get("cacheCreationInputTokens", 0) for v in model_totals.values() if isinstance(v.get("cacheCreationInputTokens", 0), int))
    return Session(
        source="claude-code",
        session_id=session_id,
        started_at=started_at,
        last_seen_at=last_seen_at,
        model=by_model[-1].model if len(by_model) == 1 else None,
        input_tokens=total_input,
        output_tokens=total_output,
        cached_input_tokens=total_cache_read,
        cache_write_tokens=total_cache_write,
        source_file=str(path),
        model_usage=tuple(by_model),
    )


def _timestamp(value) -> str | None:
    if not isinstance(value, str):
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc).isoformat()
    except ValueError:
        return None
