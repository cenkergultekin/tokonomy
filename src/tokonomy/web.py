"""Localhost dashboard and static HTML export.

A textured midnight palette keeps the data view quiet and readable.
Every number retains its source and uncertainty.
"""

from __future__ import annotations

import base64
import html
import json
import webbrowser
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from tokonomy import metrics
from tokonomy.brand import LOGO
from tokonomy.formatting import compact, money, pct, relative_reset, short_date, short_time

FONT_FACE = '@font-face { font-family: "Outfit"; src: url(data:font/ttf;base64,' + base64.b64encode((Path(__file__).parent / "assets" / "outfit.ttf").read_bytes()).decode("ascii") + ') format("truetype"); font-weight: 100 900; font-display: swap; }'

STYLE = FONT_FACE + """
:root {
  --ink: #101c26;
  --paper: #f3e9da;
  --muted: #b1bfc5;
  --dim: #9aafb8;
  --line: rgba(237, 236, 230, 0.16);
  --line-soft: rgba(237, 236, 230, 0.09);
  --green: #e5b38a;
  --amber: #d6a24a;
  --red: #d47b6a;
  --mono: "DM Mono", "Cascadia Code", Consolas, monospace;
}
* { box-sizing: border-box; }
.head, .hero, .split, .two { min-width: 0; }
.hero > *, .split > *, .two > * { min-width: 0; }
html { scroll-behavior: smooth; }
body {
  margin: 0;
  background: radial-gradient(ellipse at 0% 0%, #284c55 0%, transparent 48%), radial-gradient(ellipse at 100% 38%, #45382f 0%, transparent 48%), linear-gradient(150deg, #14252e, #101923 65%, #1c292c);
  background-attachment: fixed;
  color: var(--paper);
  font-family: "Outfit", "Bahnschrift", "Trebuchet MS", sans-serif;
  font-size: 15px;
  line-height: 1.45;
  -webkit-font-smoothing: antialiased;
}
body::after {
  content: "";
  position: fixed;
  inset: 0;
  pointer-events: none;
  z-index: 20;
  opacity: .05;
  background-image: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='160' height='160'%3E%3Cfilter id='n'%3E%3CfeTurbulence type='fractalNoise' baseFrequency='.9' numOctaves='3' stitchTiles='stitch'/%3E%3C/filter%3E%3Crect width='100%25' height='100%25' filter='url(%23n)'/%3E%3C/svg%3E");
}
a { color: inherit; text-decoration: none; }
a:hover { color: var(--green); }
.word svg { width: 34px; height: 34px; color: var(--green); flex-shrink: 0; }
a:focus-visible { outline: 2px solid var(--green); outline-offset: 6px; }
.wrap { max-width: 1240px; margin: 0 auto; padding: 0 32px; }

header { padding: 24px 0; border-bottom: 1px solid var(--line-soft); }
.head { display: flex; align-items: center; gap: 30px; }
.word { display: inline-flex; align-items: center; gap: 12px; font-size: 23px; font-weight: 700; letter-spacing: -.03em; }
.head nav { margin-left: auto; display: flex; gap: 22px; color: var(--muted); font-size: 12px; }
.head nav a:hover { color: var(--paper); }

.topline { display: flex; justify-content: space-between; gap: 20px; padding: 28px 0 10px; color: var(--dim); font-size: 11px; letter-spacing: .12em; text-transform: uppercase; }

.kpis { margin-top: 44px; display: grid; grid-template-columns: repeat(5, 1fr); border-top: 1px solid var(--line); border-bottom: 1px solid var(--line); }
.kpi { padding: 20px 22px 22px 0; }
.kpi + .kpi { border-left: 1px solid var(--line-soft); padding-left: 22px; }
.kpi span { display: block; color: var(--dim); font-size: 10.5px; letter-spacing: .13em; text-transform: uppercase; }
.kpi b { display: block; margin: 10px 0 3px; font-size: clamp(30px, 3.5vw, 48px); line-height: .95; letter-spacing: -.055em; font-weight: 700; font-variant-numeric: tabular-nums; }
.kpi small { color: var(--muted); font-size: 11px; }
.kpi .green { color: var(--green); }

main { padding-bottom: 72px !important; }
section { padding-top: 52px; scroll-margin-top: 20px; }
.sechead { flex-wrap: wrap; display: flex; align-items: baseline; justify-content: space-between; gap: 20px; border-bottom: 1px solid var(--line); padding-bottom: 10px; margin-bottom: 22px; }
.sechead h2 { margin: 0; font-size: 20px; letter-spacing: -.035em; font-weight: 700; }
.sechead span { color: var(--dim); font-size: 11.5px; }

.chart { display: block; width: 100%; height: auto; }
.axis { fill: var(--dim); font-size: 10px; font-family: var(--mono); }
.legend { display: flex; gap: 22px; margin-bottom: 10px; color: var(--muted); font-size: 11.5px; }
.legend i { display: inline-block; width: 9px; height: 2px; vertical-align: middle; margin-right: 7px; }

.quotas { display: grid; grid-template-columns: 1fr 1fr; gap: 0 56px; }
.quota { padding: 4px 0 26px; border-bottom: 1px solid var(--line-soft); }
.quota-top { display: flex; align-items: flex-end; justify-content: space-between; gap: 20px; }
.quota h3 { margin: 0; font-size: 14px; font-weight: 500; }
.quota h3 span { color: var(--dim); margin-left: 8px; }
.quota b { font-size: 40px; line-height: .9; letter-spacing: -.055em; font-weight: 700; font-variant-numeric: tabular-nums; }
.quota .bar { height: 2px; background: var(--line-soft); margin: 18px 0 10px; }
.quota .bar i { display: block; height: 2px; background: var(--green); }
.quota .bar i.warn { background: var(--amber); }
.quota .bar i.hot { background: var(--red); }
.quota-meta { display: flex; justify-content: space-between; gap: 12px; color: var(--muted); font-size: 11.5px; }
.quota p { margin: 12px 0 0; color: var(--muted); font-size: 12px; }
.quota p.warn { color: var(--amber); }
.quota p.ok { color: var(--green); }

.two { display: grid; grid-template-columns: 1.3fr .7fr; gap: 56px; }
.table-scroll { overflow-x: auto; }
table { width: 100%; border-collapse: collapse; }
th { color: var(--dim); font-size: 10px; letter-spacing: .12em; text-transform: uppercase; font-weight: 500; text-align: left; padding: 0 10px 8px 0; border-bottom: 1px solid var(--line); }
td { padding: 10px 10px 10px 0; border-bottom: 1px solid var(--line-soft); font-size: 13px; vertical-align: baseline; }
th.num, td.num { text-align: right; font-variant-numeric: tabular-nums; padding-right: 0; }
tr:last-child td { border-bottom: 0; }
.name { font-weight: 500; }
.sub { color: var(--dim); font-size: 11px; }
.src { color: var(--muted); font-size: 11px; text-transform: uppercase; letter-spacing: .06em; }

.models { display: grid; gap: 0; }
.model { display: grid; grid-template-columns: 1fr auto; gap: 16px; padding: 11px 0; border-bottom: 1px solid var(--line-soft); }
.model:last-child { border-bottom: 0; }
.model .m { font-size: 13px; }
.model .c { color: var(--muted); font-size: 12px; font-variant-numeric: tabular-nums; }

.sources { display: grid; grid-template-columns: repeat(5, 1fr); gap: 0; border-top: 1px solid var(--line); border-bottom: 1px solid var(--line); }
.source { padding: 18px 20px 20px 0; }
.source + .source { border-left: 1px solid var(--line-soft); padding-left: 20px; }
.source .s { display: flex; justify-content: space-between; gap: 10px; font-size: 13px; font-weight: 500; }
.source .state { font-size: 10px; letter-spacing: .08em; text-transform: uppercase; font-weight: 400; }
.source .n { color: var(--muted); font-size: 11.5px; margin-top: 9px; }
.source .d { color: var(--dim); font-size: 11px; margin-top: 2px; }
.ok { color: var(--green); }
.warn { color: var(--amber); }
.off { color: var(--dim); }

.note { color: var(--dim); font-size: 11.5px; margin-top: 18px; }
.empty { color: var(--dim); font-size: 13px; padding: 18px 0; }
footer { margin-top: 84px; border-top: 1px solid var(--line-soft); padding: 22px 0 44px; color: var(--dim); font-size: 11.5px; }
.foot { display: flex; justify-content: space-between; gap: 20px; flex-wrap: wrap; }

@media (max-width: 900px) {
  .kpis { grid-template-columns: repeat(2, 1fr); }
  .kpi:nth-child(odd) { border-left: 0; padding-left: 0; }
  .kpi + .kpi { padding-left: 18px; }
  .quotas, .two { grid-template-columns: 1fr; gap: 36px; }
  .sources { grid-template-columns: repeat(2, 1fr); }
  .source + .source { border-left: 0; padding-left: 0; }
  .head nav a:not(:last-child) { display: none; }
}
@media (max-width: 520px) { .wrap { padding: 0 20px; } .head nav { gap: 12px; } .kpi { padding-right: 8px; } .kpi:nth-child(odd) { padding-left: 0; } .sources { grid-template-columns: 1fr; } td, th { white-space: nowrap; } }
@media (prefers-reduced-motion: reduce) { html { scroll-behavior: auto; } }
@media print { body::after { display: none; } }
"""


def _esc(value) -> str:
    return html.escape("" if value is None else str(value))


def _chart(days: list[dict]) -> str:
    width, height = 1200, 250
    left, right, top, bottom = 52, 8, 10, 24
    inner_w = width - left - right
    inner_h = height - top - bottom
    values = [row["uncached"] or 0 for row in days]
    peak = max(values) if values and max(values) > 0 else 1
    n = max(len(days), 1)

    def x(index):
        return left + (index / max(n - 1, 1)) * inner_w

    def y(value):
        return top + inner_h - (value / peak) * inner_h

    uncached = [(x(i), y(row["uncached"] or 0)) for i, row in enumerate(days)]
    if not any(values):
        return '<div class="empty">No dated usage yet. Run tokonomy scan --force.</div>'
    baseline = top + inner_h
    area = (
        f"M {uncached[0][0]:.1f} {baseline:.1f} "
        + " ".join(f"L {px:.1f} {py:.1f}" for px, py in uncached)
        + f" L {uncached[-1][0]:.1f} {baseline:.1f} Z"
    )
    grid = []
    for step in range(5):
        value = peak * step / 4
        gy = y(value)
        grid.append(f'<line x1="{left}" y1="{gy:.1f}" x2="{width - right}" y2="{gy:.1f}" stroke="rgba(237,236,230,0.07)"/>')
        grid.append(f'<text x="{left - 9}" y="{gy + 3.5:.1f}" text-anchor="end" class="axis">{_esc(compact(value))}</text>')
    labels = []
    step = max(1, n // 6)
    for index in range(0, n, step):
        labels.append(f'<text x="{x(index):.1f}" y="{height - 6}" text-anchor="middle" class="axis">{_esc(short_date(days[index]["date"])[5:])}</text>')
    hotspots = []
    for index, row in enumerate(days):
        hotspots.append(
            f'<rect x="{x(index) - inner_w / n / 2:.1f}" y="{top}" width="{inner_w / n:.1f}" height="{inner_h}" fill="transparent">'
            f'<title>{_esc(row["date"])} · {_esc(compact(row["uncached"]))} uncached</title></rect>'
        )
    return f"""
<svg class="chart" viewBox="0 0 {width} {height}" role="img" aria-label="Daily uncached input">
  {''.join(grid)}
  <path d="{area}" fill="#e5b38a" fill-opacity="0.10"/>
  <polyline points="{' '.join(f'{px:.1f},{py:.1f}' for px, py in uncached)}" fill="none" stroke="#e5b38a" stroke-width="1.6"/>
  {''.join(labels)}
  {''.join(hotspots)}
</svg>"""


def _window(seconds: int) -> str:
    if seconds == 5 * 3600:
        return "5 hours"
    if seconds == 7 * 86400:
        return "7 days"
    if seconds % 3600 == 0:
        return f"{seconds // 3600} hours"
    return f"{seconds}s"


def _quota(item: dict) -> str:
    percent = max(0.0, min(float(item["used_percent"]), 100.0))
    forecast = item["forecast"] or {}
    status = forecast.get("status", "unknown")
    klass = "hot" if percent >= 90 else "warn" if percent >= 70 else ""
    if status == "exhausts_before_reset":
        note = f'<p class="warn">Empties in {forecast.get("eta_hours", 0):.1f}h, before reset ({forecast.get("hours_to_reset", 0):.1f}h).</p>'
    elif status == "exhausted":
        note = '<p class="warn">At 100%. Wait for reset.</p>'
    elif status == "on_track":
        note = f'<p class="ok">{forecast.get("forecast_percent_at_reset", 0):g}% projected at reset.</p>'
    elif status in {"collecting", "insufficient_data", "insufficient_span"}:
        note = '<p>Collecting a burn baseline.</p>'
    elif status == "idle":
        note = '<p>No recent burn.</p>'
    elif status == "reset_passed":
        note = '<p>Reset passed. No newer observation.</p>'
    else:
        note = f'<p>{_esc(status)}</p>'
    rate = forecast.get("rate_per_hour")
    rate_text = f"{rate:g}%/h" if isinstance(rate, (int, float)) else "rate unknown"
    return f"""
<div class="quota">
  <div class="quota-top">
    <h3>{_esc(item["provider"])}<span>{_esc(_window(item["window_seconds"]))}</span></h3>
    <b>{percent:g}%</b>
  </div>
  <div class="bar"><i class="{klass}" style="width:{percent:.1f}%"></i></div>
  <div class="quota-meta"><span>resets in {_esc(relative_reset(item["resets_at"]))}</span><span>{_esc(rate_text)}</span></div>
  {note}
</div>"""


def _projects(projects: list[dict]) -> str:
    if not projects:
        return '<tr><td colspan="6" class="empty">No project attribution.</td></tr>'
    rows = []
    for item in projects[:6]:
        rows.append(
            "<tr>"
            f'<td><div class="name">{_esc(item["project"])}</div><div class="sub">{_esc(", ".join(item["sources"]))}</div></td>'
            f'<td class="num">{item["sessions"]:,}</td>'
            f'<td class="num">{compact(item["uncached"])}</td>'
            f'<td class="num">{compact(item["output"])}</td>'
            f'<td class="num">{pct(item["cache_hit"])}</td>'
            f'<td class="num">{_esc(money(item["cost"]))}</td>'
            "</tr>"
        )
    return "".join(rows)


def _models(models: list[dict]) -> str:
    models = [item for item in models if (item["uncached"] or 0) + (item["output"] or 0) > 0]
    if not models:
        return '<div class="empty">No model usage.</div>'
    rows = []
    for item in models[:6]:
        rows.append(
            f'<div class="model"><div class="m">{_esc(item["model"])}<div class="sub">{_esc(item["source"])} · {item["sessions"]:,} sessions</div></div>'
            f'<div class="c">{_esc(money(item["cost"]))}</div></div>'
        )
    return '<div class="models">' + "".join(rows) + "</div>"


def _sessions(sessions: list[dict]) -> str:
    if not sessions:
        return '<tr><td colspan="6" class="empty">No sessions.</td></tr>'
    rows = []
    for item in sessions[:6]:
        rows.append(
            "<tr>"
            f'<td class="src">{_esc(item["source"])}</td>'
            f'<td><div class="name">{_esc(item["project"])}</div><div class="sub">{_esc(item["session_id"][:22])}</div></td>'
            f'<td>{_esc(item["model"] or "unknown")}</td>'
            f'<td class="num">{compact(item["uncached"])}</td>'
            f'<td class="num">{compact(item["output"])}</td>'
            f'<td class="num">{_esc(money(item["cost"]))}</td>'
            "</tr>"
        )
    return "".join(rows)


def _sources(sources: list[dict]) -> str:
    rows = []
    for item in sources:
        state = (item["status"] or "unknown").lower()
        klass = "ok" if state in {"imported", "ok"} else "warn" if state in {"unavailable", "error", "partial"} else "off"
        rows.append(
            f'<div class="source"><div class="s"><span>{_esc(item["source"])}</span><span class="state {klass}">{_esc(item["status"])}</span></div>'
            f'<div class="n">{item["sessions"]:,} sessions, {item["events"]:,} events</div>'
            f'<div class="d">{_esc(item["detail"])}</div></div>'
        )
    return "".join(rows)


def render_dashboard(store, generated_at: datetime | None = None) -> str:
    generated_at = generated_at or datetime.now(timezone.utc)
    connection = store.connection
    data = metrics.summary(connection)
    days = metrics.daily(connection, 30)
    quotas = metrics.quota(connection)
    projects = metrics.projects(connection, limit=6)
    models = metrics.model_breakdown(connection)
    sessions_list = metrics.recent_sessions(connection, limit=6)
    coverage = metrics.coverage(connection)
    quota_markup = "".join(_quota(item) for item in quotas) or '<div class="empty">No quota snapshots. Run tokonomy watch-limits.</div>'
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="color-scheme" content="dark">
<title>tokonomy</title>
<style>{STYLE}</style>
</head>
<body>
<header><div class="wrap head">
  <a class="word" href="/">{LOGO}tokonomy</a>
  <nav><a href="#activity">Activity</a><a href="#quota">Quota</a><a href="#projects">Projects</a><a href="#sessions">Sessions</a><a href="#sources">Sources</a></nav>
</div></header>
<main class="wrap">
  <div class="kpis">
    <div class="kpi"><span>Sessions</span><b>{data["sessions"]:,}</b><small>{len(data["sources"])} sources</small></div>
    <div class="kpi"><span>Uncached input</span><b class="green">{compact(data["uncached"])}</b></div>
    <div class="kpi"><span>Cache hit</span><b>{pct(data["cache_hit"])}</b><small>{compact(data["cached"])} cached</small></div>
    <div class="kpi"><span>Output</span><b>{compact(data["output"])}</b></div>
    <div class="kpi"><span>Est. spend</span><b>{money(data["cost"])}</b><small>{pct(data["cost_coverage"])} priceable</small></div>
  </div>

  <section id="activity">
    <div class="sechead"><h2>Activity</h2><span>30 days / UTC / uncached input</span></div>
    {_chart(days)}
  </section>

  <section id="quota">
    <div class="sechead"><h2>Quota</h2></div>
    <div class="quotas">{quota_markup}</div>
  </section>

  <section id="projects" class="two">
    <div>
      <div class="sechead"><h2>Projects</h2></div>
      <div class="table-scroll" tabindex="0" role="region" aria-label="Usage table"><table><thead><tr><th>Project</th><th class="num">Sessions</th><th class="num">Uncached</th><th class="num">Output</th><th class="num">Cache</th><th class="num">Est.</th></tr></thead>
      <tbody>{_projects(projects)}</tbody></table></div>
    </div>
    <div>
      <div class="sechead"><h2>Models</h2></div>
      {_models(models)}
    </div>
  </section>

  <section id="sessions">
    <div class="sechead"><h2>Sessions</h2></div>
    <div class="table-scroll" tabindex="0" role="region" aria-label="Usage table"><table><thead><tr><th>Source</th><th>Session</th><th>Model</th><th class="num">Uncached</th><th class="num">Output</th><th class="num">Est.</th></tr></thead>
    <tbody>{_sessions(sessions_list)}</tbody></table></div>
  </section>

  <section id="sources">
    <div class="sechead"><h2>Sources</h2></div>
    <div class="sources">{_sources(coverage["sources"])}</div>
    <p class="note">Missing values stay empty. Cost uses local list prices, not invoices. Event sources: {_esc(", ".join(coverage["event_sources"])) or "none"}.</p>
  </section>
</main>

</body>
</html>"""


def export_html(store, path: Path) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8") as stream:
        stream.write(render_dashboard(store))


def serve(data_dir: Path, port: int = 8765, open_browser: bool = True) -> int:
    from tokonomy.cli import collect
    from tokonomy.store import Store

    db_path = Path(data_dir) / "tokonomy.sqlite3"

    class Handler(BaseHTTPRequestHandler):
        server_version = f"tokonomy/{__version__}"

        def log_message(self, fmt, *args):
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
            except Exception as error:
                body = (
                    "<html><body style='background:#101c26;color:#f3e9da;font-family:sans-serif;padding:40px'>"
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
