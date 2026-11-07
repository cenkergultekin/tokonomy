"""Cache-aware, source-honest usage metrics.

Two source families report tokens differently:

* OpenAI-style (``codex``) ``input_tokens`` already contains cached tokens.
* Anthropic-style (``claude-code``) cached tokens are separate fields.

The dashboard therefore leads with **uncached input**, so a 97% cache hit rate
does not masquerade as a 2-billion-token context bill. Sources without
timestamped events contribute session totals and are labelled as such.
"""

from __future__ import annotations

import sqlite3
from datetime import datetime, timedelta, timezone

from tokonomy import pricing

CACHE_INCLUSIVE = {"codex"}


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(moment: datetime) -> str:
    return moment.astimezone(timezone.utc).isoformat()


def _start(days: int | None) -> str | None:
    if not days:
        return None
    return _iso((_now() - timedelta(days=days)).replace(hour=0, minute=0, second=0, microsecond=0))


def _get(row, key, default=None):
    try:
        value = row[key]
    except (IndexError, KeyError, TypeError):
        return default
    return default if value is None else value


def source_basis(connection: sqlite3.Connection) -> dict[str, str]:
    """A source is counted from its events when it has any, else its totals."""
    bases = {}
    for source in [r[0] for r in connection.execute("SELECT DISTINCT source FROM sessions")]:
        count = connection.execute(
            "SELECT COUNT(*) FROM usage_events WHERE source = ?", (source,)
        ).fetchone()[0]
        bases[source] = "events" if count else "sessions"
    return bases


def _uncached(source: str, input_tokens, cached_tokens) -> int | None:
    if input_tokens is None:
        return None if cached_tokens is None else 0
    if source in CACHE_INCLUSIVE:
        return max(int(input_tokens) - int(cached_tokens or 0), 0)
    return int(input_tokens)


def uncached_input(source: str, input_tokens, cached_tokens) -> int | None:
    """Public cache-semantics helper for table renderers."""
    return _uncached(source, input_tokens, cached_tokens)


def _model_groups(connection, start: str | None, basis: dict[str, str]):
    """Yield (source, model, sessions, input, cached, cache_write, output)."""
    groups = []
    for source, kind in basis.items():
        if kind == "events":
            clause = " AND occurred_at >= ?" if start else ""
            params = (source, start) if start else (source,)
            rows = connection.execute(
                f"""SELECT COALESCE(model, 'unknown') AS model,
                           COUNT(DISTINCT session_id) AS sessions,
                           SUM(input_tokens) AS input_tokens,
                           SUM(cached_input_tokens) AS cached_input_tokens,
                           SUM(cache_write_tokens) AS cache_write_tokens,
                           SUM(output_tokens) AS output_tokens
                    FROM usage_events WHERE source = ?{clause}
                    GROUP BY COALESCE(model, 'unknown')""",
                params,
            )
        else:
            clause = " AND COALESCE(last_seen_at, started_at) >= ?" if start else ""
            params = (source, start) if start else (source,)
            rows = connection.execute(
                f"""SELECT COALESCE(model, 'unknown') AS model,
                           COUNT(*) AS sessions,
                           SUM(input_tokens) AS input_tokens,
                           SUM(cached_input_tokens) AS cached_input_tokens,
                           SUM(cache_write_tokens) AS cache_write_tokens,
                           SUM(output_tokens) AS output_tokens
                    FROM sessions WHERE source = ?{clause}
                    GROUP BY COALESCE(model, 'unknown')""",
                params,
            )
        for row in rows:
            groups.append((source, row["model"], row))
    return groups


def model_breakdown(connection, days: int | None = None, table=None) -> list[dict]:
    table = table or pricing.load_pricing()
    basis = source_basis(connection)
    start = _start(days)
    merged: dict[tuple[str, str], dict] = {}
    for source, model, row in _model_groups(connection, start, basis):
        key = (source, model)
        bucket = merged.setdefault(
            key,
            {
                "source": source,
                "model": model,
                "sessions": 0,
                "input": 0,
                "cached": 0,
                "cache_write": 0,
                "output": 0,
                "uncached": 0,
                "cost": 0.0,
                "priced": False,
            },
        )
        bucket["sessions"] += int(row["sessions"] or 0)
        for field, column in (
            ("input", "input_tokens"),
            ("cached", "cached_input_tokens"),
            ("cache_write", "cache_write_tokens"),
            ("output", "output_tokens"),
        ):
            bucket[field] += int(row[column] or 0)
        bucket["uncached"] += _uncached(source, row["input_tokens"], row["cached_input_tokens"]) or 0
        cost = pricing.estimate(
            source,
            model,
            row["input_tokens"],
            row["cached_input_tokens"],
            row["cache_write_tokens"],
            row["output_tokens"],
            table,
        )
        if cost is not None:
            bucket["cost"] += cost
            bucket["priced"] = True
    for bucket in merged.values():
        reported_input = (bucket["uncached"] or 0) + (bucket["cached"] or 0)
        bucket["cache_hit"] = (
            (bucket["cached"] / reported_input * 100) if reported_input else None
        )
        bucket["cost"] = round(bucket["cost"], 6) if bucket["priced"] else None
    return sorted(
        merged.values(), key=lambda item: item["uncached"] + item["output"], reverse=True
    )


def daily(connection, days: int = 30, table=None) -> list[dict]:
    """One row per UTC day, with events preferred over session totals."""
    table = table or pricing.load_pricing()
    basis = source_basis(connection)
    now = _now()
    first = (now - timedelta(days=days - 1)).replace(hour=0, minute=0, second=0, microsecond=0)
    buckets: dict[str, dict] = {}
    for offset in range(days):
        day = (first + timedelta(days=offset)).strftime("%Y-%m-%d")
        buckets[day] = {
            "date": day,
            "uncached": 0,
            "cached": 0,
            "cache_write": 0,
            "output": 0,
            "cost": 0.0,
            "priced": False,
            "sessions": 0,
        }
    for source, kind in basis.items():
        if kind == "events":
            rows = connection.execute(
                """SELECT substr(occurred_at, 1, 10) AS day, COALESCE(model,'unknown') AS model,
                          COUNT(DISTINCT session_id) AS sessions,
                          SUM(input_tokens) AS input_tokens,
                          SUM(cached_input_tokens) AS cached_input_tokens,
                          SUM(cache_write_tokens) AS cache_write_tokens,
                          SUM(output_tokens) AS output_tokens
                   FROM usage_events WHERE occurred_at >= ?
                   GROUP BY day, COALESCE(model,'unknown')""",
                (_iso(first),),
            )
        else:
            rows = connection.execute(
                """SELECT substr(COALESCE(last_seen_at, started_at), 1, 10) AS day,
                          COALESCE(model,'unknown') AS model, COUNT(*) AS sessions,
                          SUM(input_tokens) AS input_tokens,
                          SUM(cached_input_tokens) AS cached_input_tokens,
                          SUM(cache_write_tokens) AS cache_write_tokens,
                          SUM(output_tokens) AS output_tokens
                   FROM sessions WHERE COALESCE(last_seen_at, started_at) >= ?
                   GROUP BY day, COALESCE(model,'unknown')""",
                (_iso(first),),
            )
        for row in rows:
            day = row["day"]
            if day not in buckets:
                continue
            bucket = buckets[day]
            bucket["sessions"] += int(row["sessions"] or 0)
            for field, column in (
                ("cached", "cached_input_tokens"),
                ("cache_write", "cache_write_tokens"),
                ("output", "output_tokens"),
            ):
                bucket[field] += int(row[column] or 0)
            bucket["uncached"] += _uncached(source, row["input_tokens"], row["cached_input_tokens"]) or 0
            cost = pricing.estimate(
                source,
                row["model"],
                row["input_tokens"],
                row["cached_input_tokens"],
                row["cache_write_tokens"],
                row["output_tokens"],
                table,
            )
            if cost is not None:
                bucket["cost"] += cost
                bucket["priced"] = True
    result = []
    for day in sorted(buckets):
        bucket = buckets[day]
        reported = bucket["uncached"] + bucket["cached"]
        bucket["cache_hit"] = (bucket["cached"] / reported * 100) if reported else None
        bucket["cost"] = round(bucket["cost"], 6) if bucket["priced"] else None
        result.append(bucket)
    return result


def summary(connection, days: int | None = None, table=None) -> dict:
    table = table or pricing.load_pricing()
    basis = source_basis(connection)
    start = _start(days)
    totals = {
        "sessions": 0,
        "uncached": 0,
        "cached": 0,
        "cache_write": 0,
        "output": 0,
        "cost": 0.0,
        "cache_savings": 0.0,
        "priced": False,
        "priced_tokens": 0,
        "unpriced_tokens": 0,
        "sources": [],
    }
    for source, model, row in _model_groups(connection, start, basis):
        sessions = int(row["sessions"] or 0)
        totals["sessions"] += sessions
        uncached = _uncached(source, row["input_tokens"], row["cached_input_tokens"]) or 0
        cached = int(row["cached_input_tokens"] or 0)
        output = int(row["output_tokens"] or 0)
        totals["uncached"] += uncached
        totals["cached"] += cached
        totals["cache_write"] += int(row["cache_write_tokens"] or 0)
        totals["output"] += output
        cost = pricing.estimate(
            source,
            model,
            row["input_tokens"],
            row["cached_input_tokens"],
            row["cache_write_tokens"],
            row["output_tokens"],
            table,
        )
        if cost is None:
            totals["unpriced_tokens"] += uncached + cached + output
        else:
            totals["cost"] += cost
            totals["priced"] = True
            totals["priced_tokens"] += uncached + cached + output
            rates = pricing.rate_for(model, table)
            if rates:
                totals["cache_savings"] += cached * max(rates[0] - rates[1], 0) / 1_000_000
    reported_input = totals["uncached"] + totals["cached"]
    totals["cache_hit"] = (totals["cached"] / reported_input * 100) if reported_input else None
    totals["total_input"] = reported_input
    totals["cost"] = round(totals["cost"], 6) if totals["priced"] else None
    totals["cache_savings"] = round(totals["cache_savings"], 6) if totals["priced"] else None
    known = totals["priced_tokens"] + totals["unpriced_tokens"]
    totals["cost_coverage"] = (
        totals["priced_tokens"] / known * 100 if known else None
    )
    totals["sessions_in_range"] = _sessions_in_range(connection, start)
    totals["sessions"] = totals["sessions_in_range"]
    totals["active_sessions"] = _active_sessions(connection)
    totals["sources"] = _source_rows(connection, start)
    return totals


def _sessions_in_range(connection, start: str | None) -> int:
    if start:
        return connection.execute(
            "SELECT COUNT(*) FROM sessions WHERE COALESCE(last_seen_at, started_at) >= ?",
            (start,),
        ).fetchone()[0]
    return connection.execute("SELECT COUNT(*) FROM sessions").fetchone()[0]


def _active_sessions(connection, minutes: int = 60) -> int:
    threshold = _iso(_now() - timedelta(minutes=minutes))
    return connection.execute(
        "SELECT COUNT(*) FROM sessions WHERE last_seen_at >= ?", (threshold,)
    ).fetchone()[0]


def _source_rows(connection, start: str | None) -> list[dict]:
    basis = source_basis(connection)
    health = {
        row["source"]: (row["status"], row["detail"])
        for row in connection.execute("SELECT source, status, detail FROM source_health")
    }
    rows = []
    for source, kind in sorted(basis.items()):
        if kind == "events":
            clause = " AND occurred_at >= ?" if start else ""
            params = (source, start) if start else (source,)
            count = connection.execute(
                f"SELECT COUNT(*), COUNT(DISTINCT session_id), "
                f"SUM(input_tokens), SUM(cached_input_tokens), SUM(output_tokens) "
                f"FROM usage_events WHERE source = ?{clause}",
                params,
            ).fetchone()
            records, events, input_tokens, cached, output = count
        else:
            clause = " AND COALESCE(last_seen_at, started_at) >= ?" if start else ""
            params = (source, start) if start else (source,)
            row = connection.execute(
                f"SELECT COUNT(*), SUM(input_tokens), SUM(cached_input_tokens), SUM(output_tokens) "
                f"FROM sessions WHERE source = ?{clause}",
                params,
            ).fetchone()
            records, input_tokens, cached, output = row
            events = 0
        sessions = connection.execute(
            "SELECT COUNT(*) FROM sessions WHERE source = ?", (source,)
        ).fetchone()[0]
        status, detail = health.get(source, (None, None))
        if status is None:
            status = "Imported" if sessions else "Never imported"
            detail = "Sessions present; no health record" if sessions else "No source health record"
        rows.append(
            {
                "source": source,
                "sessions": sessions,
                "records": int(records or 0),
                "events": int(events or 0),
                "basis": kind,
                "status": status,
                "detail": detail,
                "input": int(input_tokens or 0),
                "cached": int(cached or 0),
                "output": int(output or 0),
            }
        )
    return rows


def projects(connection, days: int | None = None, limit: int = 12, table=None) -> list[dict]:
    from tokonomy.formatting import project_name

    table = table or pricing.load_pricing()
    start = _start(days)
    clause = " AND COALESCE(s.last_seen_at, s.started_at) >= ?" if start else ""
    params = (start,) if start else ()
    rows = connection.execute(
        f"""SELECT COALESCE(x.project, '') AS project,
                   COUNT(*) AS sessions,
                   SUM(CASE WHEN s.source = 'codex'
                            THEN MAX(COALESCE(s.input_tokens, 0) - COALESCE(s.cached_input_tokens, 0), 0)
                            ELSE COALESCE(s.input_tokens, 0) END) AS uncached,
                   SUM(COALESCE(s.cached_input_tokens, 0)) AS cached,
                   SUM(COALESCE(s.output_tokens, 0)) AS output_tokens,
                   MAX(COALESCE(s.last_seen_at, s.started_at)) AS last_seen,
                   GROUP_CONCAT(DISTINCT s.source) AS sources
            FROM sessions s
            LEFT JOIN session_context x
              ON x.source = s.source AND x.session_id = s.session_id
            WHERE 1=1{clause}
            GROUP BY COALESCE(x.project, '')""",
        params,
    )
    merged: dict[str, dict] = {}
    for row in rows:
        name = project_name(row["project"])
        bucket = merged.setdefault(
            name,
            {
                "project": name,
                "sessions": 0,
                "uncached": 0,
                "cached": 0,
                "output": 0,
                "cost": 0.0,
                "priced": False,
                "last_seen": None,
                "sources": set(),
                "paths": set(),
            },
        )
        bucket["sessions"] += int(row["sessions"] or 0)
        bucket["uncached"] += int(row["uncached"] or 0)
        bucket["cached"] += int(row["cached"] or 0)
        bucket["output"] += int(row["output_tokens"] or 0)
        bucket["last_seen"] = max(filter(None, [bucket["last_seen"], row["last_seen"]]), default=None)
        if row["project"]:
            bucket["paths"].add(row["project"])
        for source in (row["sources"] or "").split(","):
            if source:
                bucket["sources"].add(source)
    # Cost per project is calculated from per-session model buckets.
    cost_rows = connection.execute(
        f"""SELECT COALESCE(x.project, '') AS project, m.model, m.source,
                   SUM(m.input_tokens) AS input_tokens,
                   SUM(m.cached_input_tokens) AS cached_input_tokens,
                   SUM(m.cache_write_tokens) AS cache_write_tokens,
                   SUM(m.output_tokens) AS output_tokens
            FROM model_usage m
            JOIN sessions s ON s.source = m.source AND s.session_id = m.session_id
            LEFT JOIN session_context x
              ON x.source = s.source AND x.session_id = s.session_id
            WHERE 1=1{clause}
            GROUP BY COALESCE(x.project, ''), m.model, m.source""",
        params,
    )
    for row in cost_rows:
        name = project_name(row["project"])
        bucket = merged.get(name)
        if not bucket:
            continue
        cost = pricing.estimate(
            row["source"],
            row["model"],
            row["input_tokens"],
            row["cached_input_tokens"],
            row["cache_write_tokens"],
            row["output_tokens"],
            table,
        )
        if cost is not None:
            bucket["cost"] += cost
            bucket["priced"] = True
    for bucket in merged.values():
        reported = bucket["uncached"] + bucket["cached"]
        bucket["cache_hit"] = (bucket["cached"] / reported * 100) if reported else None
        bucket["cost"] = round(bucket["cost"], 6) if bucket["priced"] else None
        bucket["sources"] = sorted(bucket["sources"])
        bucket["paths"] = sorted(bucket["paths"])
    return sorted(merged.values(), key=lambda item: item["uncached"] + item["output"], reverse=True)[:limit]


def recent_sessions(connection, limit: int = 40, days: int | None = None, table=None) -> list[dict]:
    from tokonomy.formatting import project_name

    table = table or pricing.load_pricing()
    start = _start(days)
    clause = " AND COALESCE(s.last_seen_at, s.started_at) >= ?" if start else ""
    params = (start,) if start else ()
    rows = connection.execute(
        f"""SELECT s.source, s.session_id, s.model, s.started_at, s.last_seen_at,
                   s.input_tokens, s.output_tokens, s.cached_input_tokens,
                   x.project
            FROM sessions s
            LEFT JOIN session_context x
              ON x.source = s.source AND x.session_id = s.session_id
            WHERE 1=1{clause}
            ORDER BY COALESCE(s.last_seen_at, s.started_at) DESC
            LIMIT ?""",
        (*params, limit),
    ).fetchall()
    costs: dict[tuple[str, str], float] = {}
    for row in connection.execute(
        "SELECT source, session_id, model, input_tokens, cached_input_tokens, "
        "cache_write_tokens, output_tokens FROM model_usage"
    ):
        key = (row["source"], row["session_id"])
        cost = pricing.estimate(
            row["source"],
            row["model"],
            row["input_tokens"],
            row["cached_input_tokens"],
            row["cache_write_tokens"],
            row["output_tokens"],
            table,
        )
        if cost is not None:
            costs[key] = costs.get(key, 0.0) + cost
    result = []
    for row in rows:
        input_tokens = row["input_tokens"]
        cached = row["cached_input_tokens"]
        uncached = _uncached(row["source"], input_tokens, cached)
        reported = (uncached or 0) + (cached or 0)
        key = (row["source"], row["session_id"])
        cost = costs.get(key)
        if cost is None:
            cost = pricing.estimate(
                row["source"], row["model"], input_tokens, cached, None,
                row["output_tokens"], table,
            )
        result.append(
            {
                "source": row["source"],
                "session_id": row["session_id"],
                "model": row["model"],
                "project": project_name(row["project"]),
                "started_at": row["started_at"],
                "last_seen_at": row["last_seen_at"],
                "input": input_tokens,
                "uncached": uncached,
                "cached": cached,
                "output": row["output_tokens"],
                "cache_hit": ((cached or 0) / reported * 100) if reported else None,
                "cost": round(cost, 6) if cost is not None else None,
            }
        )
    return result


def _forecast_period(connection, provider, limit_id, window_seconds, resets_at, now=None):
    """Recent burn rate from the latest monotonic segment.

    Provider reset timestamps jitter by seconds between polls, so periods are
    detected from decreasing percentages instead of exact reset strings.
    """
    now = now or _now()

    def points_since(hours: int):
        cutoff = _iso(now - timedelta(hours=hours))
        rows = connection.execute(
            """SELECT captured_at, used_percent FROM limit_snapshots
               WHERE provider = ? AND limit_id = ? AND window_seconds = ?
                 AND captured_at >= ? AND used_percent IS NOT NULL
               ORDER BY captured_at""",
            (provider, limit_id, window_seconds, cutoff),
        ).fetchall()
        collected = []
        for row in rows:
            try:
                collected.append((datetime.fromisoformat(row["captured_at"]), float(row["used_percent"])))
            except (TypeError, ValueError):
                continue
        return collected

    recent_hours = max(window_seconds / 3600 + 1, 2)
    points = points_since(recent_hours)
    if len(points) < 2:
        points = points_since(48)
    if len(points) < 2:
        return {"status": "insufficient_data", "samples": len(points)}
    # Walk back to the last reset (a drop of more than two points).
    segment = [points[-1]]
    for previous in reversed(points[:-1]):
        if previous[1] > segment[0][1] + 2:
            break
        segment.insert(0, previous)
    if len(segment) < 2:
        return {"status": "insufficient_data", "samples": len(segment)}
    first, last = segment[0], segment[-1]
    span_hours = (last[0] - first[0]).total_seconds() / 3600
    minimum_span = 0.25 if window_seconds <= 6 * 3600 else 6
    if span_hours < minimum_span:
        return {
            "status": "collecting",
            "samples": len(segment),
            "observed_hours": round(span_hours, 2),
        }
    delta = last[1] - first[1]
    rate = delta / span_hours
    current = last[1]
    payload = {
        "samples": len(segment),
        "observed_hours": round(span_hours, 2),
        "rate_per_hour": round(rate, 3),
        "current_percent": round(current, 2),
        "confidence": "high" if span_hours >= 3 and len(segment) >= 6 else "medium" if span_hours >= 1 else "low",
    }
    if current >= 100:
        payload.update(status="exhausted", eta_hours=0.0, forecast_percent_at_reset=100.0)
        return payload
    if rate <= 0.001:
        payload.update(status="idle", eta_hours=None, forecast_percent_at_reset=round(current, 2))
        return payload
    eta_hours = (100 - current) / rate
    payload["eta_hours"] = round(eta_hours, 2)
    if not resets_at:
        payload.update(status="forecast_only", forecast_percent_at_reset=None)
        return payload
    try:
        reset = datetime.fromisoformat(resets_at)
    except ValueError:
        payload.update(status="forecast_only", forecast_percent_at_reset=None)
        return payload
    hours_to_reset = (reset - now).total_seconds() / 3600
    payload["hours_to_reset"] = round(hours_to_reset, 2)
    if hours_to_reset <= 0:
        payload.update(status="reset_passed", forecast_percent_at_reset=None)
        return payload
    projected = current + rate * hours_to_reset
    payload["forecast_percent_at_reset"] = round(min(projected, 999), 1)
    payload["status"] = "exhausts_before_reset" if eta_hours < hours_to_reset else "on_track"
    return payload


def quota(connection, now=None) -> list[dict]:
    now = now or _now()
    latest = connection.execute(
        """SELECT s.* FROM limit_snapshots s
           JOIN (SELECT provider, limit_id, window_seconds, MAX(captured_at) AS latest
                 FROM limit_snapshots GROUP BY provider, limit_id, window_seconds) l
             ON s.provider = l.provider AND s.limit_id = l.limit_id
            AND s.window_seconds = l.window_seconds AND s.captured_at = l.latest
           ORDER BY s.provider, s.window_seconds"""
    ).fetchall()
    result = []
    for row in latest:
        forecast = _forecast_period(
            connection, row["provider"], row["limit_id"], row["window_seconds"],
            row["resets_at"], now,
        )
        result.append(
            {
                "provider": row["provider"],
                "plan": row["plan_type"],
                "limit_id": row["limit_id"],
                "window_seconds": row["window_seconds"],
                "used_percent": row["used_percent"],
                "resets_at": row["resets_at"],
                "captured_at": row["captured_at"],
                "forecast": forecast,
            }
        )
    return result


def coverage(connection) -> dict:
    basis = source_basis(connection)
    sources = _source_rows(connection, None)
    files = {
        row["source"]: {"files": row["files"], "versions": row["versions"]}
        for row in connection.execute(
            "SELECT source, COUNT(*) AS files, GROUP_CONCAT(DISTINCT parser_version) AS versions "
            "FROM source_files GROUP BY source"
        )
    }
    for source in sources:
        source["files"] = files.get(source["source"], {}).get("files", 0)
        source["parser_versions"] = files.get(source["source"], {}).get("versions")
    return {
        "sources": sources,
        "event_sources": [name for name, kind in basis.items() if kind == "events"],
        "total_sources": len(sources),
    }


def digest(connection, days: int = 7) -> dict:
    current = summary(connection, days)
    previous = summary(connection, days * 2)
    previous_only = {
        key: max((previous.get(key) or 0) - (current.get(key) or 0), 0)
        for key in ("sessions", "uncached", "cached", "output")
    }
    top_projects = projects(connection, days, limit=3)
    top_models = model_breakdown(connection, days)[:3]
    quotas = quota(connection)
    alerts = [
        item for item in quotas
        if item["forecast"].get("status") in {"exhausts_before_reset", "exhausted"}
    ]
    return {
        "days": days,
        "current": current,
        "previous": previous_only,
        "projects": top_projects,
        "models": top_models,
        "alerts": alerts,
    }


def budget_check(connection, max_usd: float, days: int = 7) -> dict:
    current = summary(connection, days)
    spend = current["cost"]
    if spend is None:
        return {
            "ok": None,
            "reason": "No priceable usage in range; cannot verify a budget.",
            "spend": None,
            "limit": max_usd,
            "days": days,
        }
    return {
        "ok": spend <= max_usd,
        "spend": round(spend, 4),
        "limit": max_usd,
        "remaining": round(max_usd - spend, 4),
        "coverage": current["cost_coverage"],
        "days": days,
    }
