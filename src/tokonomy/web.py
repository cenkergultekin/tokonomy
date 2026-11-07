"""Local-first web dashboard and static HTML export.

No framework, no CDN, no telemetry: one stdlib server renders the same HTML
that ``tokonomy export --html`` writes. The page is designed to be readable in
a screenshot as well as in a browser.
"""

from __future__ import annotations

import html
import json
import webbrowser
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from tokonomy import __version__, metrics
from tokonomy.formatting import compact, money, pct, relative_reset, short_date, short_time

REPO_URL = "https://github.com/cenkergultekin/tokonomy"

STYLE = """
:root {
  --bg: #070a09;
  --panel: rgba(18, 25, 22, 0.72);
  --panel-solid: #101613;
  --line: rgba(126, 231, 135, 0.14);
  --line-soft: rgba(255, 255, 255, 0.06);
  --text: #e6efe9;
  --muted: #8b9a91;
  --dim: #5f6f66;
  --green: #7ee787;
  --green-soft: #b7f7bd;
  --blue: #6cb6ff;
  --amber: #f0b429;
  --red: #ff7b72;
  --mono: "SFMono-Regular", "Cascadia Code", "Consolas", "Liberation Mono", monospace;
  --sans: "Inter", "Segoe UI", -apple-system, BlinkMacSystemFont, "Helvetica Neue", Arial, sans-serif;
}
* { box-sizing: border-box; }
html { scroll-behavior: smooth; }
body {
  margin: 0;
  background: var(--bg);
  color: var(--text);
  font-family: var(--sans);
  font-size: 15px;
  line-height: 1.5;
  -webkit-font-smoothing: antialiased;
}
body::before {
  content: "";
  position: fixed;
  inset: 0;
  pointer-events: none;
  background:
    radial-gradient(900px 500px at 12% -8%, rgba(126, 231, 135, 0.10), transparent 60%),
    radial-gradient(800px 420px at 92% 2%, rgba(108, 182, 255, 0.07), transparent 55%),
    radial-gradient(700px 500px at 50% 110%, rgba(240, 180, 41, 0.04), transparent 60%);
  z-index: -1;
}
a { color: var(--green-soft); text-decoration: none; }
a:hover { color: #ffffff; }
.wrap { max-width: 1240px; margin: 0 auto; padding: 0 28px; }
nav {
  position: sticky; top: 0; z-index: 20;
  backdrop-filter: blur(16px);
  background: rgba(7, 10, 9, 0.72);
  border-bottom: 1px solid var(--line-soft);
}
.nav-inner { display: flex; align-items: center; gap: 22px; height: 64px; }
.brand { display: flex; align-items: center; gap: 10px; font-weight: 650; letter-spacing: -0.02em; font-size: 17px; }
.mark {
  width: 26px; height: 26px; border-radius: 9px;
  display: grid; place-items: center;
  background: radial-gradient(circle at 30% 25%, #163a23, #0b120e);
  border: 1px solid rgba(126, 231, 135, 0.35);
  color: var(--green); font-size: 13px;
  box-shadow: 0 0 22px rgba(126, 231, 135, 0.18);
}
.nav-links { display: flex; gap: 20px; margin-left: auto; align-items: center; }
.nav-links a { color: var(--muted); font-size: 13.5px; }
.nav-links a:hover { color: var(--text); }
.pill {
  display: inline-flex; align-items: center; gap: 7px;
  border: 1px solid var(--line); border-radius: 999px;
  padding: 5px 11px; color: var(--green-soft);
  background: rgba(126, 231, 135, 0.06);
  font-size: 12px; letter-spacing: 0.02em;
}
.dot { width: 6px; height: 6px; border-radius: 50%; background: var(--green); box-shadow: 0 0 10px var(--green); }
.hero { padding: 62px 0 34px; display: grid; grid-template-columns: 1.25fr 0.75fr; gap: 48px; align-items: end; }
.eyebrow { color: var(--green); font-size: 12px; letter-spacing: 0.16em; text-transform: uppercase; margin-bottom: 16px; }
h1 { font-size: clamp(38px, 5vw, 58px); line-height: 1.02; letter-spacing: -0.045em; margin: 0 0 18px; font-weight: 640; }
h1 em { font-style: normal; color: var(--green); }
.lede { color: var(--muted); font-size: 16.5px; max-width: 610px; margin: 0; }
.hero-meta { display: flex; gap: 10px; flex-wrap: wrap; margin-top: 24px; }
.hero-side { border-left: 1px solid var(--line-soft); padding-left: 28px; }
.hero-side .label { color: var(--dim); font-size: 11.5px; letter-spacing: 0.12em; text-transform: uppercase; }
.hero-side .big { font-size: 34px; letter-spacing: -0.03em; margin: 6px 0 2px; }
.hero-side .sub { color: var(--muted); font-size: 13px; }
.grid { display: grid; gap: 16px; }
.kpis { grid-template-columns: repeat(5, 1fr); margin: 18px 0 8px; }
.card {
  background: linear-gradient(180deg, rgba(22, 30, 26, 0.82), rgba(13, 18, 15, 0.82));
  border: 1px solid var(--line-soft);
  border-radius: 16px;
  padding: 18px 18px 16px;
  position: relative;
  overflow: hidden;
}
.card::after {
  content: ""; position: absolute; inset: 0;
  border-radius: 16px; pointer-events: none;
  box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.035);
}
.kpi .k { color: var(--dim); font-size: 11.5px; letter-spacing: 0.1em; text-transform: uppercase; }
.kpi .v { font-family: var(--mono); font-size: 27px; letter-spacing: -0.04em; margin: 9px 0 3px; }
.kpi .s { color: var(--muted); font-size: 12px; }
.kpi.green .v { color: var(--green); }
.kpi.blue .v { color: var(--blue); }
.kpi.amber .v { color: var(--amber); }
main { padding-bottom: 70px; }
section { margin-top: 42px; scroll-margin-top: 82px; }
.section-head { display: flex; align-items: baseline; gap: 16px; margin-bottom: 14px; }
.section-head h2 { font-size: 18px; letter-spacing: -0.02em; margin: 0; font-weight: 600; }
.section-head .hint { color: var(--dim); font-size: 12.5px; }
.section-head .more { margin-left: auto; color: var(--muted); font-size: 12.5px; }
.split { display: grid; grid-template-columns: 1.55fr 1fr; gap: 16px; }
.chart-card { padding: 20px 20px 14px; }
.legend { display: flex; gap: 18px; align-items: center; margin-bottom: 10px; color: var(--muted); font-size: 12px; }
.legend i { width: 9px; height: 9px; border-radius: 3px; display: inline-block; margin-right: 6px; }
.chart { width: 100%; height: auto; display: block; }
.axis { fill: var(--dim); font-size: 10px; font-family: var(--mono); }
.quote { padding: 22px; display: flex; flex-direction: column; gap: 14px; }
.quote h3 { margin: 0; font-size: 13px; color: var(--muted); font-weight: 500; letter-spacing: 0.02em; }
.quote .big { font-family: var(--mono); font-size: 34px; letter-spacing: -0.04em; color: var(--green); }
.quote .note { color: var(--dim); font-size: 12px; }
.quote .rule { height: 1px; background: var(--line-soft); }
.quota-grid { display: grid; grid-template-columns: repeat(2, 1fr); gap: 16px; }
.quota { padding: 20px; }
.quota-top { display: flex; justify-content: space-between; align-items: flex-start; gap: 12px; }
.quota h3 { margin: 0; font-size: 15px; font-weight: 600; }
.quota .window { color: var(--dim); font-size: 12px; margin-top: 2px; }
.quota .pct { font-family: var(--mono); font-size: 31px; letter-spacing: -0.04em; }
.bar { height: 9px; border-radius: 99px; background: rgba(255, 255, 255, 0.06); overflow: hidden; margin: 16px 0 10px; }
.bar > span { display: block; height: 100%; border-radius: 99px; background: linear-gradient(90deg, #4fbf67, var(--green)); }
.bar.warn > span { background: linear-gradient(90deg, #c98a14, var(--amber)); }
.bar.hot > span { background: linear-gradient(90deg, #c8493f, var(--red)); }
.quota .meta { display: flex; justify-content: space-between; color: var(--muted); font-size: 12px; gap: 10px; }
.alert {
  margin-top: 12px; padding: 9px 11px; border-radius: 9px;
  background: rgba(240, 180, 41, 0.08); border: 1px solid rgba(240, 180, 41, 0.22);
  color: #f6d58b; font-size: 12.5px;
}
.alert.calm { background: rgba(126, 231, 135, 0.06); border-color: rgba(126, 231, 135, 0.18); color: var(--green-soft); }
table { width: 100%; border-collapse: collapse; }
th {
  text-align: left; color: var(--dim); font-size: 10.5px; letter-spacing: 0.1em;
  text-transform: uppercase; font-weight: 600; padding: 0 10px 10px; border-bottom: 1px solid var(--line-soft);
}
td { padding: 11px 10px; border-bottom: 1px solid rgba(255, 255, 255, 0.045); font-size: 13.5px; vertical-align: middle; }
tr:last-child td { border-bottom: 0; }
td.num, th.num { text-align: right; font-family: var(--mono); font-size: 12.5px; }
.tbl-card { padding: 18px 10px 8px; }
.proj { font-weight: 550; }
.sub { color: var(--dim); font-size: 11.5px; }
.tag {
  display: inline-flex; align-items: center; gap: 6px;
  font-size: 11px; color: var(--muted); border: 1px solid var(--line-soft);
  padding: 2px 7px; border-radius: 6px; background: rgba(255, 255, 255, 0.025);
}
.tag.codex { color: #b7f7bd; border-color: rgba(126, 231, 135, 0.2); }
.tag.claude-code { color: #ffd7a3; border-color: rgba(240, 180, 41, 0.2); }
.tag.hermes { color: #d6c3ff; border-color: rgba(180, 150, 255, 0.2); }
.tag.opencode { color: #a9d6ff; border-color: rgba(108, 182, 255, 0.2); }
.tag.cursor { color: #c4c4c4; }
.mini { display: inline-block; height: 5px; border-radius: 99px; background: var(--green); opacity: 0.75; vertical-align: middle; }
.models { display: grid; gap: 13px; padding: 8px 4px; }
.model { display: grid; grid-template-columns: 200px 1fr 88px; gap: 14px; align-items: center; }
.model .name { font-size: 13px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.model .track { height: 7px; background: rgba(255, 255, 255, 0.055); border-radius: 99px; overflow: hidden; }
.model .fill { height: 100%; border-radius: 99px; background: linear-gradient(90deg, #397a49, var(--green)); }
.model .cost { text-align: right; font-family: var(--mono); font-size: 12px; color: var(--muted); }
.source-grid { display: grid; grid-template-columns: repeat(5, 1fr); gap: 12px; }
.source { padding: 15px; }
.source .name { display: flex; justify-content: space-between; align-items: center; font-size: 13.5px; font-weight: 550; }
.source .state { font-size: 10.5px; letter-spacing: 0.04em; text-transform: uppercase; }
.ok { color: var(--green); } .warn { color: var(--amber); } .off { color: var(--dim); }
.source .stat { color: var(--muted); font-size: 12px; margin-top: 8px; }
.source .detail { color: var(--dim); font-size: 11px; margin-top: 3px; min-height: 16px; }
footer { border-top: 1px solid var(--line-soft); padding: 26px 0 40px; color: var(--dim); font-size: 12px; }
.foot-inner { display: flex; justify-content: space-between; gap: 20px; flex-wrap: wrap; }
.quality { display: flex; gap: 10px; flex-wrap: wrap; margin-top: 10px; }
.chip { border: 1px solid var(--line-soft); border-radius: 999px; padding: 4px 10px; font-size: 11.5px; color: var(--muted); }
.empty { color: var(--dim); padding: 24px 6px; font-size: 13px; }
@media (max-width: 980px) {
  .hero { grid-template-columns: 1fr; gap: 24px; }
  .hero-side { border-left: 0; padding-left: 0; }
  .kpis { grid-template-columns: repeat(2, 1fr); }
  .split, .quota-grid { grid-template-columns: 1fr; }
  .source-grid { grid-template-columns: repeat(2, 1fr); }
  .model { grid-template-columns: 130px 1fr 70px; }
  .nav-links a:not(.pill) { display: none; }
}
@media print {
  body::before { display: none; }
  nav { position: static; }
  .card { break-inside: avoid; }
}
"""


def _esc(value) -> str:
    return html.escape("" if value is None else str(value))


def _tag(source: str) -> str:
    return f'<span class="tag {_esc(source)}">{_esc(source)}</span>'


def _chart(days: list[dict]) -> str:
    width, height = 1000, 250
    left, right, top, bottom = 56, 16, 16, 30
    inner_w = width - left - right
    inner_h = height - top - bottom
    values = [(row["uncached"] or 0) + (row["output"] or 0) for row in days]
    peak = max(values) if values and max(values) > 0 else 1
    n = max(len(days), 1)

    def x(index):
        return left + (index / max(n - 1, 1)) * inner_w

    def y(value):
        return top + inner_h - (value / peak) * inner_h

    def points(key):
        return [(x(i), y(row[key] or 0)) for i, row in enumerate(days)]

    uncached = points("uncached")
    output = points("output")
    if not any(values):
        return '<div class="empty">No dated usage yet. Run <code>tokonomy scan --force</code>.</div>'
    baseline = top + inner_h
    area_uncached = (
        f"M {uncached[0][0]:.1f} {baseline:.1f} "
        + " ".join(f"L {px:.1f} {py:.1f}" for px, py in uncached)
        + f" L {uncached[-1][0]:.1f} {baseline:.1f} Z"
    )
    top_points = [(xc, yc - (row["output"] or 0) / peak * inner_h) for (xc, yc), row in zip(uncached, days)]
    area_output = (
        f"M {top_points[0][0]:.1f} {top_points[0][1]:.1f} "
        + " ".join(f"L {px:.1f} {py:.1f}" for px, py in top_points)
        + " "
        + " ".join(f"L {px:.1f} {py:.1f}" for px, py in reversed(uncached))
        + " Z"
    )
    grid = []
    for step in range(5):
        value = peak * step / 4
        gy = y(value)
        grid.append(f'<line x1="{left}" y1="{gy:.1f}" x2="{width - right}" y2="{gy:.1f}" stroke="rgba(255,255,255,0.055)" stroke-width="1"/>')
        grid.append(f'<text x="{left - 10}" y="{gy + 3.5:.1f}" text-anchor="end" class="axis">{_esc(compact(value))}</text>')
    labels = []
    step = max(1, n // 6)
    for index in range(0, n, step):
        labels.append(
            f'<text x="{x(index):.1f}" y="{height - 8}" text-anchor="middle" class="axis">{_esc(short_date(days[index]["date"])[5:])}</text>'
        )
    hotspots = []
    for index, row in enumerate(days):
        title = f'{row["date"]} · {compact(row["uncached"])} uncached · {compact(row["output"])} output · {money(row["cost"])}'
        hotspots.append(
            f'<rect x="{x(index) - inner_w / n / 2:.1f}" y="{top}" width="{inner_w / n:.1f}" height="{inner_h}" fill="transparent"><title>{_esc(title)}</title></rect>'
        )
    return f"""
<svg class="chart" viewBox="0 0 {width} {height}" role="img" aria-label="Daily token activity">
  <defs>
    <linearGradient id="g-uncached" x1="0" y1="0" x2="0" y2="1">
      <stop offset="0%" stop-color="#7ee787" stop-opacity="0.42"/>
      <stop offset="100%" stop-color="#7ee787" stop-opacity="0.02"/>
    </linearGradient>
    <linearGradient id="g-output" x1="0" y1="0" x2="0" y2="1">
      <stop offset="0%" stop-color="#6cb6ff" stop-opacity="0.55"/>
      <stop offset="100%" stop-color="#6cb6ff" stop-opacity="0.06"/>
    </linearGradient>
  </defs>
  {''.join(grid)}
  <path d="{area_uncached}" fill="url(#g-uncached)"/>
  <path d="{area_output}" fill="url(#g-output)"/>
  <polyline points="{' '.join(f'{px:.1f},{py:.1f}' for px, py in uncached)}" fill="none" stroke="#7ee787" stroke-width="2"/>
  <polyline points="{' '.join(f'{px:.1f},{py:.1f}' for px, py in top_points)}" fill="none" stroke="#6cb6ff" stroke-width="2"/>
  {''.join(labels)}
  {''.join(hotspots)}
</svg>"""


def _quota_card(item: dict) -> str:
    percent = max(0.0, min(float(item["used_percent"]), 100.0))
    forecast = item["forecast"] or {}
    window = _window_label(item["window_seconds"])
    klass = "hot" if percent >= 90 else "warn" if percent >= 70 else ""
    reset = relative_reset(item["resets_at"])
    status = forecast.get("status", "unknown")
    confidence = forecast.get("confidence")
    if not confidence:
        confidence = "baseline collecting" if status in {"collecting", "insufficient_data"} else "not enough data"
    confidence_line = f"{confidence} confidence" if forecast.get("confidence") else confidence
    if forecast.get("status") == "exhausts_before_reset":
        alert = (
            f'<div class="alert">⚠ Burn {forecast.get("rate_per_hour", 0):g}%/h · '
            f'empties in ~{forecast.get("eta_hours", 0):.1f}h, before reset ({forecast.get("hours_to_reset", 0):.1f}h).</div>'
        )
    elif forecast.get("status") == "exhausted":
        alert = '<div class="alert">Quota observed at 100%. Wait for the reset or switch models.</div>'
    elif forecast.get("status") == "on_track":
        alert = (
            f'<div class="alert calm">On track: {forecast.get("forecast_percent_at_reset", 0):g}% '
            f'projected at reset.</div>'
        )
    elif forecast.get("status") in {"collecting", "insufficient_data", "insufficient_span"}:
        alert = '<div class="alert calm">Collecting a burn baseline. Leave the collector running.</div>'
    elif forecast.get("status") == "idle":
        alert = '<div class="alert calm">No recent burn observed.</div>'
    else:
        alert = f'<div class="alert calm">{_esc(forecast.get("status", "No forecast"))}</div>'
    return f"""
<div class="card quota">
  <div class="quota-top">
    <div><h3>{_esc(item["provider"])} <span class="tag">{_esc(window)}</span></h3>
    <div class="window">resets in {_esc(reset)} · observed {_esc(short_time(item["captured_at"]))}</div></div>
    <div class="pct">{percent:g}%</div>
  </div>
  <div class="bar {klass}"><span style="width:{percent:.1f}%"></span></div>
  <div class="meta"><span>window {_esc(window)}</span><span>{_esc(confidence_line)}</span></div>
  {alert}
</div>"""


def _window_label(seconds: int) -> str:
    if seconds == 5 * 3600:
        return "5 hours"
    if seconds == 7 * 86400:
        return "7 days"
    if seconds % 3600 == 0:
        return f"{seconds // 3600} hours"
    return f"{seconds}s"


def _kpis(data: dict) -> str:
    active = data.get("active_sessions", 0)
    active_note = f"{active} active in the last hour" if active else f"tracked across {len(data.get('sources', []))} sources"
    cards = [
        ("Sessions", f"{data['sessions']:,}", active_note, ""),
        ("Uncached input", compact(data["uncached"]), "context actually sent, cache excluded", "green"),
        ("Cache hit", pct(data["cache_hit"]), f"{compact(data['cached'])} tokens served from cache", "blue"),
        ("Output", compact(data["output"]), "tokens generated", ""),
        ("Est. spend", money(data["cost"]), f"{pct(data['cost_coverage'])} of tokens priceable", "amber"),
    ]
    return "".join(
        f'<div class="card kpi {klass}"><div class="k">{_esc(label)}</div>'
        f'<div class="v">{_esc(value)}</div><div class="s">{_esc(sub)}</div></div>'
        for label, value, sub, klass in cards
    )


def _model_rows(models: list[dict]) -> str:
    if not models:
        return '<div class="empty">No model usage recorded.</div>'
    peak = max((item["uncached"] + item["output"]) for item in models[:7]) or 1
    rows = []
    for item in models[:7]:
        share = (item["uncached"] + item["output"]) / peak * 100
        cost = money(item["cost"]) if item["cost"] is not None else "—"
        rows.append(
            f'<div class="model"><div class="name" title="{_esc(item["model"])}">'
            f'{_esc(item["model"])} <span class="sub">· {_esc(item["source"])}</span></div>'
            f'<div class="track"><div class="fill" style="width:{share:.1f}%"></div></div>'
            f'<div class="cost">{_esc(cost)}</div></div>'
        )
    return '<div class="models">' + "".join(rows) + "</div>"


def _project_rows(projects: list[dict]) -> str:
    if not projects:
        return '<tr><td colspan="6" class="empty">No project attribution yet.</td></tr>'
    rows = []
    for item in projects[:10]:
        rows.append(
            "<tr>"
            f'<td><div class="proj">{_esc(item["project"])}</div>'
            f'<div class="sub">{_esc(", ".join(item["sources"])) or "unknown source"}</div></td>'
            f'<td class="num">{item["sessions"]:,}</td>'
            f'<td class="num">{compact(item["uncached"])}</td>'
            f'<td class="num">{compact(item["output"])}</td>'
            f'<td class="num">{pct(item["cache_hit"])}</td>'
            f'<td class="num">{_esc(money(item["cost"]))}</td>'
            "</tr>"
        )
    return "".join(rows)


def _session_rows(sessions: list[dict]) -> str:
    if not sessions:
        return '<tr><td colspan="5" class="empty">No sessions imported yet.</td></tr>'
    rows = []
    for item in sessions[:10]:
        rows.append(
            "<tr>"
            f'<td>{_tag(item["source"])}</td>'
            f'<td><div class="proj">{_esc(item["project"])}</div>'
            f'<div class="sub">{_esc((item["model"] or "model unknown"))} · {_esc(item["session_id"][:18])}</div></td>'
            f'<td class="num">{compact(item["uncached"])}</td>'
            f'<td class="num">{compact(item["output"])}</td>'
            f'<td class="num">{_esc(money(item["cost"]))}</td>'
            "</tr>"
        )
    return "".join(rows)


def _source_cards(sources: list[dict]) -> str:
    cards = []
    for item in sources:
        state = (item["status"] or "unknown").lower()
        klass = "ok" if state in {"imported", "ok"} else "warn" if state in {"unavailable", "error"} else "off"
        cards.append(
            f'<div class="card source"><div class="name">{_esc(item["source"])}'
            f'<span class="state {klass}">{_esc(item["status"])}</span></div>'
            f'<div class="stat">{item["sessions"]:,} sessions · {item["events"]:,} events</div>'
            f'<div class="detail">{_esc(item["detail"])}</div></div>'
        )
    return "".join(cards)


def render_dashboard(store, generated_at: datetime | None = None) -> str:
    generated_at = generated_at or datetime.now(timezone.utc)
    connection = store.connection
    data = metrics.summary(connection)
    days = metrics.daily(connection, 30)
    quotas = metrics.quota(connection)
    projects = metrics.projects(connection, limit=10)
    models = metrics.model_breakdown(connection)
    sessions_list = metrics.recent_sessions(connection, limit=10)
    coverage = metrics.coverage(connection)
    quota_cards = "".join(_quota_card(item) for item in quotas)
    if not quotas:
        quota_cards = '<div class="card quota empty">No quota snapshots yet. Run <code>tokonomy watch-limits</code>.</div>'
    hero_spend = money(data["cost"])
    savings = money(data["cache_savings"])
    headline = "Your AI usage, in focus."
    if data["cache_hit"] is not None:
        headline = "Your AI usage, <em>in focus</em>."
    stamp = generated_at.strftime("%Y-%m-%d %H:%M UTC")
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="color-scheme" content="dark">
<meta name="description" content="tokonomy — local-first, cache-aware usage analytics for AI coding sessions.">
<title>tokonomy · local AI usage observatory</title>
<style>{STYLE}</style>
</head>
<body>
<nav><div class="wrap nav-inner">
  <a class="brand" href="#top"><span class="mark">◍</span>tokonomy</a>
  <div class="nav-links">
    <a href="#activity">Activity</a><a href="#quota">Quota</a><a href="#models">Models</a>
    <a href="#projects">Projects</a><a href="#sessions">Sessions</a><a href="#sources">Sources</a>
    <a class="pill" href="{REPO_URL}" target="_blank" rel="noreferrer"><span class="dot"></span>Open source · MIT</a>
  </div>
</div></nav>

<div class="wrap" id="top">
  <header class="hero">
    <div>
      <div class="eyebrow">Local AI usage observatory</div>
      <h1>{headline}</h1>
      <p class="lede">Cache-aware token accounting, real quota burn forecasts and project-level spend for
      Codex, Claude Code, Hermes, OpenCode and Cursor. Everything stays on this machine — no prompts,
      no responses, no cloud.</p>
      <div class="hero-meta">
        <span class="pill"><span class="dot"></span>Live from your local database</span>
        <span class="chip">No transcripts stored</span>
        <span class="chip">Offline by default</span>
        <span class="chip">v{__version__}</span>
      </div>
    </div>
    <aside class="hero-side">
      <div class="label">Estimated spend</div>
      <div class="big">{_esc(hero_spend)}</div>
      <div class="sub">estimated from dated list prices · not an invoice</div>
      <div class="rule" style="height:1px;background:var(--line-soft);margin:18px 0"></div>
      <div class="label">Cache saved you</div>
      <div class="big" style="color:var(--green)">{_esc(savings)}</div>
      <div class="sub">vs. sending the same context uncached</div>
    </aside>
  </header>

  <div class="grid kpis">{_kpis(data)}</div>

  <section id="activity">
    <div class="section-head"><h2>Activity</h2><span class="hint">last 30 days · UTC · uncached input + output</span>
      <a class="more" href="?scan=1">Scan now →</a></div>
    <div class="split">
      <div class="card chart-card">
        <div class="legend"><span><i style="background:var(--green)"></i>Uncached input</span>
          <span><i style="background:var(--blue)"></i>Output</span></div>
        {_chart(days)}
      </div>
      <div class="card quote">
        <h3>What this means</h3>
        <div class="big">{pct(data["cache_hit"])}</div>
        <div class="note">of reported input tokens were served from cache. Context is being reused well;
        uncached input is the number that actually costs.</div>
        <div class="rule"></div>
        <div class="note"><strong style="color:var(--text)">{compact(data["cached"])}</strong> cached tokens ·
        <strong style="color:var(--text)">{compact(data["uncached"])}</strong> uncached ·
        <strong style="color:var(--text)">{compact(data["output"])}</strong> output</div>
      </div>
    </div>
  </section>

  <section id="quota">
    <div class="section-head"><h2>Quota &amp; burn forecast</h2>
      <span class="hint">source-reported windows · local observations</span></div>
    <div class="quota-grid">{quota_cards}</div>
  </section>

  <section id="models">
    <div class="split">
      <div class="card tbl-card" id="projects">
        <div class="section-head" style="margin:4px 10px 8px"><h2>Projects</h2><span class="hint">by uncached input</span></div>
        <table><thead><tr><th>Project</th><th class="num">Sessions</th><th class="num">Uncached</th>
          <th class="num">Output</th><th class="num">Cache</th><th class="num">Est. cost</th></tr></thead>
          <tbody>{_project_rows(projects)}</tbody></table>
      </div>
      <div class="card tbl-card">
        <div class="section-head" style="margin:4px 10px 8px"><h2>Models</h2><span class="hint">share of work</span></div>
        {_model_rows(models)}
      </div>
    </div>
  </section>

  <section id="sessions">
    <div class="section-head"><h2>Recent sessions</h2><span class="hint">most recent activity first</span></div>
    <div class="card tbl-card">
      <table><thead><tr><th>Source</th><th>Session</th><th class="num">Uncached</th>
        <th class="num">Output</th><th class="num">Est. cost</th></tr></thead>
        <tbody>{_session_rows(sessions_list)}</tbody></table>
    </div>
  </section>

  <section id="sources">
    <div class="section-head"><h2>Sources &amp; coverage</h2>
      <span class="hint">unknown values stay unknown, never zero</span></div>
    <div class="source-grid">{_source_cards(coverage["sources"])}</div>
    <div class="quality">
      <span class="chip">Cost coverage {pct(data["cost_coverage"])}</span>
      <span class="chip">Event sources: {_esc(", ".join(coverage["event_sources"])) or "none"}</span>
      <span class="chip">Prices: public list prices, editable in pricing.json</span>
      <span class="chip">Database: local SQLite</span>
    </div>
  </section>
</div>

<footer><div class="wrap foot-inner">
  <div>tokonomy {__version__} · MIT · runs on 127.0.0.1 · generated {stamp}</div>
  <div>Estimates are labelled. Unknowns stay blank. <a href="{REPO_URL}">GitHub ↗</a></div>
</div></footer>
</body>
</html>"""


def export_html(store, path: Path) -> None:
    """Write a self-contained dashboard; never overwrite an existing file."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    markup = render_dashboard(store)
    with path.open("x", encoding="utf-8") as stream:
        stream.write(markup)


def serve(data_dir: Path, port: int = 8765, open_browser: bool = True) -> int:
    from tokonomy.cli import collect
    from tokonomy.store import Store

    db_path = Path(data_dir) / "tokonomy.sqlite3"

    class Handler(BaseHTTPRequestHandler):
        server_version = f"tokonomy/{__version__}"

        def log_message(self, fmt, *args):  # keep the terminal clean
            return

        def _send(self, status: int, body: bytes, content_type: str):
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self):
            parsed = urlparse(self.path)
            query = parse_qs(parsed.query)
            if parsed.path == "/health":
                self._send(200, json.dumps({"ok": True, "version": __version__}).encode(), "application/json")
                return
            if parsed.path not in {"/", "/index.html", "/api/summary.json"}:
                self._send(404, b"not found", "text/plain; charset=utf-8")
                return
            try:
                if "scan" in query:
                    collect(Path(data_dir), quiet=True)
                store = Store(db_path)
                try:
                    if parsed.path == "/api/summary.json":
                        payload = {
                            "summary": metrics.summary(store.connection),
                            "quota": metrics.quota(store.connection),
                            "coverage": metrics.coverage(store.connection),
                        }
                        body = json.dumps(payload, default=str).encode("utf-8")
                        content_type = "application/json"
                    else:
                        body = render_dashboard(store).encode("utf-8")
                        content_type = "text/html; charset=utf-8"
                finally:
                    store.close()
            except Exception as error:  # surface a readable page instead of a stack trace
                body = (
                    "<html><body style='background:#070a09;color:#e6efe9;font-family:system-ui;padding:40px'>"
                    f"<h1>tokonomy could not render</h1><pre>{html.escape(str(error))}</pre></body></html>"
                ).encode("utf-8")
                content_type = "text/html; charset=utf-8"
                self._send(500, body, content_type)
                return
            self._send(200, body, content_type)

    try:
        server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    except OSError as error:
        print(f"Could not listen on 127.0.0.1:{port}: {error}")
        return 1
    url = f"http://127.0.0.1:{port}/"
    print(f"tokonomy web · {url}")
    print("Press Ctrl+C to stop. The dashboard only listens on localhost.")
    if open_browser:
        webbrowser.open(url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopped.")
    finally:
        server.server_close()
    return 0
