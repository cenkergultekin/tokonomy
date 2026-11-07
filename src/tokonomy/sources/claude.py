from pathlib import Path
from datetime import datetime, timezone

from tokonomy.models import ModelUsage, Session, UsageEvent
from tokonomy.sources.jsonl import iter_jsonl


def discover(root: Path) -> list[Path]:
    return sorted(root.rglob("*.jsonl")) if root.exists() else []


def read_session(path: Path) -> Session | None:
    events = {}
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
        normalized = None
        stamp = record.get("timestamp")
        if isinstance(stamp, str):
            normalized = _timestamp(stamp)
            started_at = started_at or normalized
            last_seen_at = normalized or last_seen_at
        if kind == "assistant":
            message = record.get("message", {})
            usage = message.get("usage", {})
            identity = message.get("id")
            if identity and usage and normalized:
                fields = [usage.get(k) for k in ("input_tokens", "output_tokens", "cache_read_input_tokens", "cache_creation_input_tokens")]
                fields = [v if isinstance(v, int) and not isinstance(v, bool) else None for v in fields]
                previous = events.get(identity)
                if previous:
                    fields = [max(a or 0, b or 0) if a is not None or b is not None else None for a,b in zip(fields, [previous.input_tokens, previous.output_tokens, previous.cached_input_tokens, previous.cache_write_tokens])]
                events[identity] = UsageEvent(identity, normalized, message.get("model"), *fields)
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
    # Message IDs deduplicate streaming blocks; cumulative cost-state is fallback only.
    if events:
        model_totals = {}
        for event in events.values():
            totals = model_totals.setdefault(event.model or "unknown", {})
            for key, value in zip(("inputTokens", "outputTokens", "cacheReadInputTokens", "cacheCreationInputTokens"), (event.input_tokens, event.output_tokens, event.cached_input_tokens, event.cache_write_tokens)):
                if value is not None: totals[key] = totals.get(key, 0) + value
        if '/subagents/' in path.as_posix():
            session_id = str(session_id) + ':' + path.stem
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
        usage_events=tuple(events.values()),
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
