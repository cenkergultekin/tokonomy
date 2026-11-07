from pathlib import Path

from tokonomy.models import ModelUsage, Session
from tokonomy.sources.jsonl import iter_jsonl


def discover(root: Path) -> list[Path]:
    return sorted([*root.rglob("*.jsonl"), *root.rglob("*.jsonl.zst")]) if root.exists() else []


def read_session(path: Path) -> Session | None:
    session_id = None
    started_at = None
    last_seen_at = None
    model = None
    totals: dict[str, int] = {}
    by_model: dict[str, dict[str, int]] = {}
    current_model = None
    seen_responses: set[str] = set()
    for record in iter_jsonl(path):
        kind = record.get("type")
        payload = record.get("payload")
        if not isinstance(payload, dict):
            continue
        if kind == "session_meta":
            session_id = payload.get("id") or payload.get("session_id") or session_id
            started_at = payload.get("timestamp") or record.get("timestamp") or started_at
        elif kind == "turn_context":
            value = payload.get("model")
            if isinstance(value, str):
                model = value
                current_model = value
        elif kind == "token_usage_record":
            response_id = payload.get("response_id")
            if isinstance(response_id, str) and response_id in seen_responses:
                continue
            if isinstance(response_id, str):
                seen_responses.add(response_id)
            # `usage` is the per-response delta. The turn/thread fields are
            # cumulative snapshots and must not be added across records.
            usage = payload.get("usage")
            if isinstance(usage, dict):
                # Turn deltas are authoritative. Never sum cumulative thread totals.
                for key in ("input_tokens", "output_tokens", "cached_input_tokens", "cache_write_input_tokens"):
                    value = usage.get(key)
                    if isinstance(value, int) and not isinstance(value, bool):
                        totals[key] = totals.get(key, 0) + value
                        if current_model:
                            group = by_model.setdefault(current_model, {})
                            group[key] = group.get(key, 0) + value
        stamp = record.get("timestamp")
        if isinstance(stamp, str):
            last_seen_at = stamp
    if not session_id:
        return None
    return Session(
        source="codex",
        session_id=str(session_id),
        started_at=started_at if isinstance(started_at, str) else None,
        last_seen_at=last_seen_at,
        model=model,
        input_tokens=totals.get("input_tokens"),
        output_tokens=totals.get("output_tokens"),
        cached_input_tokens=totals.get("cached_input_tokens"),
        cache_write_tokens=totals.get("cache_write_input_tokens"),
        source_file=str(path),
        model_usage=tuple(
            ModelUsage(
                model=name,
                input_tokens=values.get("input_tokens"),
                output_tokens=values.get("output_tokens"),
                cached_input_tokens=values.get("cached_input_tokens"),
                cache_write_tokens=values.get("cache_write_input_tokens"),
            )
            for name, values in by_model.items()
        ),
    )
