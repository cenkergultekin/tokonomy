"""Build a deterministic demo database for screenshots and docs.

The README images must not expose a real person's projects or spending, so the
marketing assets are generated from this synthetic dataset instead.
"""

from __future__ import annotations

import random
from datetime import datetime, timedelta, timezone
from pathlib import Path

from tokonomy.models import LimitSnapshot, ModelUsage, Session, UsageEvent
from tokonomy.store import Store

PROJECTS = [
    ("atlas-platform", 0.30),
    ("ledger-api", 0.24),
    ("orbit-mobile", 0.18),
    ("docs-site", 0.12),
    ("research-lab", 0.09),
    ("infra-tools", 0.07),
]
CODEX_MODELS = ["gpt-5.1-codex", "gpt-5.1", "gpt-5.1-codex"]
CLAUDE_MODELS = ["claude-sonnet-4-5", "claude-opus-4-1", "claude-sonnet-4-5"]


def _pick(rng, weighted):
    point = rng.random()
    cumulative = 0.0
    for value, weight in weighted:
        cumulative += weight
        if point <= cumulative:
            return value
    return weighted[-1][0]


def _split(rng, total: int, parts: int) -> list[int]:
    if parts <= 1:
        return [total]
    cuts = sorted(rng.randint(1, total - 1) for _ in range(parts - 1))
    values = []
    previous = 0
    for cut in cuts:
        values.append(cut - previous)
        previous = cut
    values.append(total - previous)
    return values


def build(path: Path) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        path.unlink()
    store = Store(path)
    connection = store.connection
    rng = random.Random(21)
    now = datetime.now(timezone.utc).replace(minute=0, second=0, microsecond=0)
    projects = [(name, weight) for name, weight in PROJECTS]

    for day in range(40):
        date = now - timedelta(days=day)
        session_count = rng.randint(4, 8) if day < 30 else rng.randint(2, 4)
        for index in range(session_count):
            source = "codex" if rng.random() < 0.62 else "claude-code"
            project = _pick(rng, projects)
            started = date.replace(hour=rng.randint(7, 21), minute=rng.randint(0, 59))
            duration = rng.randint(18, 150)
            ended = started + timedelta(minutes=duration)
            if day == 0:
                ended = min(ended, now - timedelta(minutes=rng.randint(2, 50)))
            session_id = f"{project}-{day:02d}-{index:02d}-{rng.randrange(16**6):06x}"
            model = rng.choice(CODEX_MODELS if source == "codex" else CLAUDE_MODELS)
            if source == "codex":
                uncached = rng.randint(18_000, 380_000)
                cached = rng.randint(180_000, 3_400_000)
                output = rng.randint(4_000, 92_000)
                cache_write = 0
                input_tokens = uncached + cached
            else:
                uncached = rng.randint(1_500, 48_000)
                cached = rng.randint(350_000, 4_800_000)
                cache_write = rng.randint(1_000, 32_000)
                output = rng.randint(6_000, 120_000)
                input_tokens = uncached
            parts = rng.randint(3, 7)
            inputs = _split(rng, input_tokens, parts)
            outputs = _split(rng, output, parts)
            caches = _split(rng, cached, parts)
            writes = _split(rng, cache_write, parts) if cache_write else [0] * parts
            events = []
            for part in range(parts):
                moment = started + (ended - started) * (part + 1) / parts
                events.append(UsageEvent(
                    event_id=f"evt-{session_id}-{part}",
                    occurred_at=moment.isoformat(),
                    model=model,
                    input_tokens=inputs[part],
                    output_tokens=outputs[part],
                    cached_input_tokens=caches[part],
                    cache_write_tokens=writes[part],
                ))
            store.upsert_session(Session(
                source=source,
                session_id=session_id,
                started_at=started.isoformat(),
                last_seen_at=ended.isoformat(),
                model=model,
                input_tokens=input_tokens,
                output_tokens=output,
                cached_input_tokens=cached,
                cache_write_tokens=cache_write,
                source_file=f"demo/{source}/{project}/{session_id}.jsonl",
                model_usage=(ModelUsage(
                    model=model,
                    input_tokens=input_tokens,
                    output_tokens=output,
                    cached_input_tokens=cached,
                    cache_write_tokens=cache_write,
                ),),
                usage_events=tuple(events),
            ))
            connection.execute(
                "INSERT OR REPLACE INTO session_context VALUES (?,?,?,?,?,?,?)",
                (source, session_id, f"C:/work/{project}", f"C:/work/{project}", None, "main", f"demo/{session_id}.jsonl"),
            )

    # Totals-only sources keep the coverage story honest.
    for index in range(18):
        moment = now - timedelta(days=rng.randint(1, 38), hours=rng.randint(0, 12))
        project = _pick(rng, projects)
        store.upsert_session(Session(
            "hermes", f"hermes-{index:03d}", started_at=moment.isoformat(),
            last_seen_at=(moment + timedelta(minutes=rng.randint(10, 90))).isoformat(),
            model="gpt-5.1", input_tokens=rng.randint(20_000, 300_000),
            cached_input_tokens=rng.randint(100_000, 1_200_000),
            output_tokens=rng.randint(5_000, 60_000),
            source_file=f"demo/hermes/{index}.jsonl",
        ))
        connection.execute(
            "INSERT OR REPLACE INTO session_context VALUES (?,?,?,?,?,?,?)",
            ("hermes", f"hermes-{index:03d}", f"C:/work/{project}", f"C:/work/{project}", None, None, f"demo/hermes/{index}.jsonl"),
        )
    for index in range(9):
        moment = now - timedelta(days=rng.randint(2, 35))
        store.upsert_session(Session(
            "opencode", f"opencode-{index:03d}", started_at=moment.isoformat(),
            last_seen_at=(moment + timedelta(minutes=40)).isoformat(),
            model="gemini-2.5-pro", input_tokens=rng.randint(10_000, 120_000),
            output_tokens=rng.randint(2_000, 30_000),
            source_file=f"demo/opencode/{index}.db",
        ))
    for index in range(6):
        moment = now - timedelta(days=rng.randint(2, 35))
        store.upsert_session(Session(
            "cursor", f"cursor-{index:03d}", started_at=moment.isoformat(),
            last_seen_at=(moment + timedelta(minutes=50)).isoformat(),
            source_file=f"demo/cursor/{index}.vscdb",
        ))

    # Quota observations: a hot 5-hour window and a calm weekly window.
    for step in range(37):
        captured = now - timedelta(minutes=5 * step)
        used = min(91.0, 62.0 + (36 - step) * 0.75 + rng.uniform(-0.8, 0.8))
        resets = now + timedelta(hours=2, minutes=42)
        store.save_limit_snapshot(LimitSnapshot(
            provider="codex", limit_id="codex", plan_type="pro",
            window_seconds=18000, used_percent=round(used, 1),
            captured_at=captured.isoformat(), resets_at=resets.isoformat(),
            source_event_id=f"demo-5h-{step}",
        ))
    for step in range(25):
        captured = now - timedelta(hours=step)
        used = 41.5 - step * 0.35 + rng.uniform(-0.3, 0.3)
        resets = now + timedelta(days=3, hours=5)
        store.save_limit_snapshot(LimitSnapshot(
            provider="codex", limit_id="codex", plan_type="pro",
            window_seconds=604800, used_percent=round(max(used, 19.0), 1),
            captured_at=captured.isoformat(), resets_at=resets.isoformat(),
            source_event_id=f"demo-7d-{step}",
        ))

    for source, detail in (
        ("codex", "42 files; 8 changed"),
        ("claude-code", "28 files; 5 changed"),
        ("hermes", "18 sessions; session totals only"),
        ("opencode", "9 sessions; session totals only"),
        ("cursor", "6 sessions; metadata only"),
    ):
        connection.execute(
            "INSERT OR REPLACE INTO source_health VALUES (?,?,?,?)",
            (source, now.isoformat(), "Imported", detail),
        )
    connection.commit()
    store.close()
    return path


if __name__ == "__main__":
    import sys

    target = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("demo.sqlite3")
    print(build(target))
