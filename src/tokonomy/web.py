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

from tokonomy import __version__, metrics
from tokonomy.brand import LOGO
from tokonomy.formatting import compact, money, pct, relative_reset, short_date, short_time

FONT_FACE = '@font-face { font-family: "Outfit"; src: url(data:font/ttf;base64,' + base64.b64encode((Path(__file__).parent / "assets" / "outfit.ttf").read_bytes()).decode("ascii") + ') format("truetype"); font-weight: 100 900; font-display: swap; }'

STYLE = FONT_FACE + '\n:root{--paper:#eee8dd;--muted:#b1bfc5;--dim:#9bafb6;--green:#e5b38a;--amber:#e4b45f;--red:#e2907d;--line:#c5d5d51c;--line-soft:#c5d5d511;--mono:Consolas,monospace}*{box-sizing:border-box}body{margin:0;color:var(--paper);font:15px/1.5 Outfit,sans-serif;background:radial-gradient(ellipse at 12% 0,#274a5255,transparent 60%),radial-gradient(ellipse at 100% 95%,#68503c35,transparent 55%),#12212a;background-attachment:fixed}body:after{content:"";position:fixed;inset:0;pointer-events:none;opacity:.025;z-index:30;background-image:url("data:image/svg+xml,%3Csvg xmlns=\'http://www.w3.org/2000/svg\' width=\'160\' height=\'160\'%3E%3Cfilter id=\'n\'%3E%3CfeTurbulence type=\'fractalNoise\' baseFrequency=\'.8\' numOctaves=\'3\'/%3E%3C/filter%3E%3Crect width=\'100%25\' height=\'100%25\' filter=\'url(%23n)\'/%3E%3C/svg%3E")}\nbutton,input,select{font:inherit}button,a{color:inherit}button{cursor:pointer}button:focus-visible,a:focus-visible,input:focus-visible,select:focus-visible{outline:2px solid var(--green);outline-offset:4px}button{background:none;border:0}a{text-decoration:none}[hidden]{display:none!important}.rail{position:fixed;inset:0 auto 0 0;width:210px;padding:36px 24px;border-right:1px solid var(--line);background:#0b1a242b}.word{display:flex;align-items:center;gap:9px;font-size:23px;font-weight:550;letter-spacing:-.04em}.word svg{width:34px;height:34px;color:var(--green)}nav{display:flex;flex-direction:column;gap:12px;margin-top:58px}nav button{text-align:left;padding:10px 14px;color:var(--dim);border-left:2px solid transparent}nav button[aria-current=page]{color:var(--green);border-color:var(--green);background:linear-gradient(90deg,#e5b38a0b,transparent)}main{margin-left:210px;padding:34px 48px 60px;max-width:1750px}.toolbar{display:flex;align-items:center;justify-content:space-between;gap:20px;margin-bottom:40px}h1{font-size:30px;font-weight:450;letter-spacing:-.04em;margin:0}.tools{display:flex;align-items:center;gap:18px}.tools button{padding:8px;color:var(--dim)}.tools svg{width:20px;height:20px}.mode,#status{font-size:12px;color:var(--dim)}.kpis{display:grid;grid-template-columns:repeat(5,1fr);gap:25px;padding-bottom:35px;border-bottom:1px solid var(--line)}.kpi span{display:block;color:var(--dim);font-size:13px}.kpi b{display:block;font-size:clamp(28px,3vw,44px);font-weight:450;letter-spacing:-.055em;margin:6px 0;font-variant-numeric:tabular-nums;line-height:1.15}.kpi small{font-size:12px;color:var(--dim)}.green,.ok{color:var(--green)}.warn{color:var(--amber)}.off{color:var(--dim)}section{padding-top:32px}.sechead{display:flex;justify-content:space-between;align-items:center;gap:20px;flex-wrap:wrap;margin-bottom:24px}h2{font-size:20px;font-weight:450;letter-spacing:-.025em;margin:0}.sechead span,.note{font-size:12px;color:var(--dim)}.chart{display:block;width:100%;height:auto;max-height:260px}.axis{fill:var(--dim);font-size:11px;font-family:var(--mono)}.quotas{display:grid;grid-template-columns:1fr 1fr;gap:44px}.quota{padding:18px 0}.quota-top{display:flex;justify-content:space-between;align-items:center;gap:15px}.quota h3{margin:0;font-size:15px;font-weight:450}.quota h3 span{color:var(--dim);margin-left:12px}.quota b{font-size:36px;font-weight:450;letter-spacing:-.04em}.bar{height:3px;background:var(--line);margin:18px 0 12px}.bar i{display:block;height:3px;background:var(--green)}.bar i.warn{background:var(--amber)}.bar i.hot{background:var(--red)}.quota-meta{display:flex;justify-content:space-between;color:var(--dim);font-size:12px}.quota p{font-size:12px}.table-scroll{overflow-x:auto}table{width:100%;border-collapse:collapse}th{text-align:left;color:var(--dim);font-size:12px;font-weight:400;padding:12px 16px 12px 0;border-bottom:1px solid var(--line)}td{font-size:14px;padding:16px 16px 16px 0;border-bottom:1px solid var(--line-soft)}.num{text-align:right;font-variant-numeric:tabular-nums}.sub{color:var(--dim);font-size:12px}.src{color:var(--muted);font-size:12px}.session-link{text-align:left;padding:0;color:var(--paper)}.session-link:hover{color:var(--green)}.filters{display:flex;gap:16px;margin-bottom:25px;flex-wrap:wrap}input,select{border:0;border-bottom:1px solid var(--line);background:#152730;color:var(--paper);padding:10px 12px;border-radius:0}input{flex:1;min-width:150px}.models{display:grid;grid-template-columns:repeat(2,1fr);gap:0 50px}.model{display:flex;justify-content:space-between;gap:20px;padding:18px 0;border-bottom:1px solid var(--line)}.model .c{color:var(--green)}.sources{display:grid;gap:20px}.source{padding:20px 0;border-bottom:1px solid var(--line)}.source .s{display:flex;justify-content:space-between}.source .n,.source .d{font-size:13px;color:var(--dim);margin-top:8px}.empty{padding:20px 0;color:var(--dim)}dialog{background:#182c35;color:var(--paper);border:1px solid #39505a;padding:30px;width:min(580px,calc(100% - 32px));max-height:85vh}dialog::backdrop{background:#061119aa}dialog button{float:right;font-size:22px}dl{display:grid;grid-template-columns:130px 1fr;gap:12px}dt{color:var(--dim)}dd{margin:0;overflow-wrap:anywhere}#session-count{font-size:12px;color:var(--dim);margin-top:18px}\n@media(max-width:1000px){.rail{width:165px;padding-inline:14px}main{margin-left:165px;padding:28px}.word{font-size:20px}.kpis{grid-template-columns:repeat(3,1fr)}.quotas,.models{grid-template-columns:1fr;gap:20px}}\n@media(max-width:650px){.rail{position:static;width:auto;padding:20px;border-right:0}.word{font-size:23px}nav{flex-direction:row;gap:15px;overflow:auto;margin-top:22px}nav button{white-space:nowrap;padding:8px 0;border-left:0;border-bottom:2px solid transparent}main{margin:0;padding:20px}.toolbar{margin-bottom:28px}.kpis{grid-template-columns:repeat(2,1fr);gap:25px}.kpi b{font-size:35px}.filters{gap:10px}.filters select{max-width:100%}.tools{gap:8px}.sechead{flex-direction:column;align-items:flex-start;gap:6px}.sechead span{white-space:normal}.chart{min-height:150px}td,th{white-space:nowrap}dl{grid-template-columns:1fr;gap:6px}dd{margin-bottom:10px}.mode{display:none}}\n'


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
        return '<div class="empty">No dated usage yet.</div>'
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
    for item in projects:
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
    for item in models:
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


SCRIPT = '\nconst sessions=JSON.parse(document.querySelector(\'#session-data\').textContent);let visible=sessions;\nconst $=s=>document.querySelector(s);const num=n=>n==null?\'Unknown\':new Intl.NumberFormat(\'en\',{notation:\'compact\',maximumFractionDigits:2}).format(n);const cost=n=>n==null?\'Unknown\':\'$\'+n.toFixed(2);\nfunction show(page){if(!document.querySelector(\'[data-panel="\'+page+\'"]\'))page=\'overview\';document.querySelectorAll(\'[data-panel]\').forEach(p=>p.hidden=p.dataset.panel!==page);document.querySelectorAll(\'[data-page]\').forEach(b=>b.setAttribute(\'aria-current\',b.dataset.page===page?\'page\':\'false\'));$(\'#page-title\').textContent=page.charAt(0).toUpperCase()+page.slice(1)}\ndocument.querySelectorAll(\'[data-page]\').forEach(b=>b.onclick=()=>{location.hash=b.dataset.page});window.addEventListener(\'hashchange\',()=>show(location.hash.slice(1)));show(location.hash.slice(1));\nfunction detail(row){$(\'#detail-fields\').replaceChildren();for(const [key,label] of [[\'project\',\'Project\'],[\'session_id\',\'Session\'],[\'source\',\'Provider\'],[\'model\',\'Model\'],[\'started_at\',\'Started\'],[\'last_seen_at\',\'Last activity\'],[\'uncached\',\'Uncached input\'],[\'cached\',\'Cache reads\'],[\'output\',\'Output\'],[\'cost\',\'Est. cost\']]){const dt=document.createElement(\'dt\'),dd=document.createElement(\'dd\');dt.textContent=label;dd.textContent=row[key]==null?\'Unknown\':key===\'cost\'?cost(row[key]):String(row[key]);$(\'#detail-fields\').append(dt,dd)}$(\'#detail\').showModal()}\nfunction render(){const q=$(\'#search\').value.toLowerCase(),provider=$(\'#provider\').value,sort=$(\'#sort\').value;visible=sessions.filter(r=>(!provider||r.source===provider)&&[r.project,r.session_id,r.model,r.source].join(\' \').toLowerCase().includes(q));if(sort!==\'recent\')visible.sort((a,b)=>(b[sort]??-1)-(a[sort]??-1));const target=$(\'#session-rows\');target.replaceChildren();for(const row of visible){const tr=document.createElement(\'tr\'),first=document.createElement(\'td\'),button=document.createElement(\'button\');button.className=\'session-link\';button.textContent=row.project||row.session_id;button.onclick=()=>detail(row);const sub=document.createElement(\'div\');sub.className=\'sub\';sub.textContent=row.session_id.slice(0,22);first.append(button,sub);tr.append(first);for(const [index,value] of [row.source,row.model||\'Unknown\',num(row.uncached),num(row.output),cost(row.cost)].entries()){const td=document.createElement(\'td\');td.textContent=value;if(index>1)td.className=\'num\';tr.append(td)}target.append(tr)}$(\'#session-count\').textContent=visible.length+\' sessions\';if(!visible.length){const tr=document.createElement(\'tr\'),td=document.createElement(\'td\');td.colSpan=6;td.className=\'empty\';td.textContent=\'No matching sessions\';tr.append(td);target.append(tr)}}\n$(\'#search\').oninput=render;$(\'#provider\').onchange=render;$(\'#sort\').onchange=render;$(\'#close-detail\').onclick=()=>$(\'#detail\').close();render();\n$(\'#export\').onclick=()=>{const url=URL.createObjectURL(new Blob([JSON.stringify(visible,null,2)],{type:\'application/json\'}));const a=document.createElement(\'a\');a.href=url;a.download=\'tokonomy-sessions.json\';a.click();setTimeout(()=>URL.revokeObjectURL(url),1000)};\nconst refresh=$(\'#refresh\');if(refresh)refresh.onclick=async()=>{refresh.disabled=true;$(\'#status\').textContent=\'Refreshing\';try{const response=await fetch(\'/?scan=1\');if(!response.ok)throw Error();location.reload()}catch{$(\'#status\').textContent=\'Refresh failed\';refresh.disabled=false}};\n'

def render_dashboard(store, generated_at: datetime | None = None, live: bool = False, demo: bool = False) -> str:
    generated_at = generated_at or datetime.now(timezone.utc)
    connection = store.connection
    data = metrics.summary(connection)
    sessions_list = metrics.recent_sessions(connection, limit=-1)
    projects = metrics.projects(connection, limit=max(1, data["sessions"]))
    coverage = metrics.coverage(connection)
    quotas = "".join(_quota(item) for item in metrics.quota(connection)) or '<div class="empty">No quota snapshots.</div>'
    payload = json.dumps(sessions_list, ensure_ascii=False).replace("<", "\\u003c")
    mode = "Demo data" if demo else "" if live else "Snapshot"
    refresh = '<button id="refresh" aria-label="Refresh local data" title="Refresh"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><path d="M20 7v5h-5M4 17v-5h5M19 11a7 7 0 0 0-12-5M5 13a7 7 0 0 0 12 5"/></svg></button>' if live else ''
    return f"""<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>tokonomy</title><style>{STYLE}</style></head><body>
<aside class="rail"><a class="word" href="#overview">{LOGO}tokonomy</a><nav aria-label="Views">{''.join(f'<button data-page="{key}" aria-current="{ "page" if key == "overview" else "false" }">{label}</button>' for key,label in [('overview','Overview'),('sessions','Sessions'),('projects','Projects'),('models','Models'),('sources','Sources')])}</nav></aside>
<main><div class="toolbar"><h1 id="page-title">Overview</h1><div class="tools"><span class="mode">{mode}</span><span id="status" role="status"></span>{refresh}<button id="export" aria-label="Export displayed session data" title="Export sessions"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><path d="M12 3v12m-5-5 5 5 5-5M4 16v5h16v-5"/></svg></button></div></div>
<div data-panel="overview"><div class="kpis">
<div class="kpi"><span>Sessions</span><b>{data['sessions']:,}</b><small>{len(data['sources'])} sources</small></div>
<div class="kpi"><span>Uncached input</span><b class="green">{compact(data['uncached'])}</b></div>
<div class="kpi"><span>Cache hit</span><b>{pct(data['cache_hit'])}</b><small>{compact(data['cached'])} cached</small></div>
<div class="kpi"><span>Output</span><b>{compact(data['output'])}</b></div>
<div class="kpi"><span>Est. spend</span><b>{money(data['cost'])}</b><small>{pct(data['cost_coverage'])} priceable</small></div></div>
<section><div class="sechead"><h2>Activity</h2><span>Uncached input / 30 days / UTC</span></div>{_chart(metrics.daily(connection,30))}</section>
<section><div class="sechead"><h2>Quota</h2></div><div class="quotas">{quotas}</div></section></div>
<div data-panel="sessions" hidden><div class="filters"><input id="search" type="search" aria-label="Search sessions" placeholder="Search sessions"><select id="provider" aria-label="Provider"><option value="">All providers</option>{''.join(f'<option>{_esc(x)}</option>' for x in sorted({r['source'] for r in sessions_list}))}</select><select id="sort" aria-label="Sort sessions"><option value="recent">Recent activity</option><option value="uncached">Uncached input</option><option value="output">Output</option><option value="cost">Estimated cost</option></select></div><div class="table-scroll"><table><thead><tr><th>Project / session</th><th>Provider</th><th>Model</th><th class="num">Uncached</th><th class="num">Output</th><th class="num">Est. cost</th></tr></thead><tbody id="session-rows"></tbody></table></div><div id="session-count" role="status"></div></div>
<div data-panel="projects" hidden><div class="table-scroll"><table><thead><tr><th>Project</th><th class="num">Sessions</th><th class="num">Uncached</th><th class="num">Output</th><th class="num">Cache</th><th class="num">Est. cost</th></tr></thead><tbody>{_projects(projects)}</tbody></table></div></div>
<div data-panel="models" hidden>{_models(metrics.model_breakdown(connection))}</div>
<div data-panel="sources" hidden><div class="sources">{_sources(coverage['sources'])}</div><p class="note">Costs are estimates from local list prices. Missing values remain unknown.</p></div>
</main><dialog id="detail" aria-labelledby="detail-title"><button aria-label="Close session details" id="close-detail">×</button><h2 id="detail-title">Session</h2><dl id="detail-fields"></dl></dialog>
<script id="session-data" type="application/json">{payload}</script><script>{SCRIPT}</script></body></html>"""


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
                        body = render_dashboard(store, live=True).encode("utf-8")
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
