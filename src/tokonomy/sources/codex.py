from datetime import datetime, timezone
import hashlib
from pathlib import Path

from tokonomy.models import LimitSnapshot, ModelUsage, Session, UsageEvent
from tokonomy.sources.jsonl import iter_jsonl

# Bump whenever extracted fields or semantics change: stored files are then
# re-read automatically instead of silently keeping stale rows.
PARSER_VERSION = 2


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
    models_by_turn: dict[str, str] = {}
    usage_events: list[UsageEvent] = []
    limit_snapshots: list[LimitSnapshot] = []
    seen_responses: set[str] = set()
    line_number = 0
    for record in iter_jsonl(path):
        line_number += 1
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
                turn_id = payload.get("turn_id")
                if isinstance(turn_id, str):
                    models_by_turn[turn_id] = value
        elif kind == "token_usage_record":
            response_id = payload.get("response_id")
            if isinstance(response_id, str) and response_id in seen_responses:
                continue
            if isinstance(response_id, str):
                seen_responses.add(response_id)
            event_time = _timestamp(record.get("timestamp"))
            turn_id = payload.get("turn_id")
            event_model = models_by_turn.get(turn_id, current_model) if isinstance(turn_id, str) else current_model
            # `usage` is the per-response delta. The turn/thread fields are
            # cumulative snapshots and must not be added across records.
            usage = payload.get("usage")
            if isinstance(usage, dict):
                # Turn deltas are authoritative. Never sum cumulative thread totals.
                for key in ("input_tokens", "output_tokens", "cached_input_tokens", "cache_write_input_tokens"):
                    value = usage.get(key)
                    if isinstance(value, int) and not isinstance(value, bool):
                        totals[key] = totals.get(key, 0) + value
                        if event_model:
                            group = by_model.setdefault(event_model, {})
                            group[key] = group.get(key, 0) + value
                if event_time and isinstance(response_id, str):
                    usage_events.append(UsageEvent(
                        event_id=response_id, occurred_at=event_time, model=event_model,
                        input_tokens=usage.get("input_tokens") if isinstance(usage.get("input_tokens"), int) else None,
                        output_tokens=usage.get("output_tokens") if isinstance(usage.get("output_tokens"), int) else None,
                        cached_input_tokens=usage.get("cached_input_tokens") if isinstance(usage.get("cached_input_tokens"), int) else None,
                        cache_write_tokens=usage.get("cache_write_input_tokens") if isinstance(usage.get("cache_write_input_tokens"), int) else None,
                    ))
        elif kind == "event_msg" and payload.get("type") == "token_count":
            timestamp = _timestamp(record.get("timestamp"))
            limits = payload.get("rate_limits")
            if timestamp and isinstance(limits, dict):
                path_key = hashlib.sha256(str(path).encode("utf-8")).hexdigest()
                for slot in ("primary", "secondary"):
                    window = limits.get(slot)
                    if not isinstance(window, dict):
                        continue
                    minutes = window.get("window_minutes")
                    used = window.get("used_percent")
                    reset_raw = window.get("resets_at")
                    if not isinstance(minutes, int) or not isinstance(used, (int, float)):
                        continue
                    resets_at = datetime.fromtimestamp(reset_raw, timezone.utc).isoformat() if isinstance(reset_raw, (int, float)) else None
                    duration = minutes * 60
                    limit_snapshots.append(LimitSnapshot(
                        provider="codex",
                        limit_id="codex",
                        plan_type=None,
                        window_seconds=duration,
                        used_percent=float(used),
                        captured_at=timestamp,
                        resets_at=resets_at,
                        exhausted=used >= 100,
                        source_event_id=f"rollout:{path_key}:{line_number}:{duration}",
                    ))
        stamp = record.get("timestamp")
        if isinstance(stamp, str):
            last_seen_at = _timestamp(stamp) or last_seen_at
    if not session_id:
        return None
    return Session(
        source="codex",
        session_id=str(session_id),
        started_at=_timestamp(started_at),
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
        usage_events=tuple(usage_events),
        limit_snapshots=tuple(limit_snapshots),
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
