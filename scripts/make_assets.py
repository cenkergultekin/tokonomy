"""Generate README images from the real tokonomy CLI and dashboard.

Usage:  python scripts/make_assets.py
Requires Chrome or Edge for the headless screenshots.
"""

from __future__ import annotations

import html
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DOCS = ROOT / "docs"
CLI_BIN = ROOT / ".venv" / "Scripts" / "tokonomy.exe"
PYTHON = ROOT / ".venv" / "Scripts" / "python.exe"
if not PYTHON.exists():
    PYTHON = Path(sys.executable)

ANSI = re.compile(r"\x1b\[([0-9;]*)m")
COLORS = {
    30: "#3b4252", 31: "#ff7b72", 32: "#7ee787", 33: "#f0b429", 34: "#6cb6ff",
    35: "#d2a8ff", 36: "#76e3ea", 37: "#e6efe9", 90: "#5f6f66", 91: "#ffa198",
    92: "#b7f7bd", 93: "#f6d58b", 94: "#a9d6ff", 95: "#e2c5ff", 96: "#b3f0f5", 97: "#ffffff",
}


def find_browser() -> str:
    for candidate in (
        r"C:\Program Files\Google\Chrome\Application\chrome.exe",
        r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
        "/usr/bin/google-chrome",
        "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
    ):
        if Path(candidate).exists():
            return candidate
    raise SystemExit("Chrome or Edge is required for screenshots")


def ansi_to_html(text: str) -> str:
    output = []
    for line in text.splitlines():
        spans = []
        position = 0
        colour = None
        bold = False
        for match in ANSI.finditer(line):
            chunk = html.escape(line[position:match.start()])
            if chunk:
                style = ""
                if colour:
                    style += f"color:{colour};"
                if bold:
                    style += "font-weight:600;"
                spans.append(f'<span style="{style}">{chunk}</span>' if style else chunk)
            codes = [part for part in match.group(1).split(";") if part]
            index = 0
            while index < len(codes):
                code = codes[index]
                if code == "0":
                    colour, bold = None, False
                elif code == "1":
                    bold = True
                elif code in {"38", "48"} and index + 1 < len(codes) and codes[index + 1] == "2":
                    rgb = codes[index + 2:index + 5]
                    if code == "38" and len(rgb) == 3:
                        colour = f"rgb({','.join(rgb)})"
                    index += 4
                elif code.isdigit() and int(code) in COLORS:
                    colour = COLORS[int(code)]
                index += 1
            position = match.end()
        tail = html.escape(line[position:])
        if tail:
            style = ""
            if colour:
                style += f"color:{colour};"
            if bold:
                style += "font-weight:600;"
            spans.append(f'<span style="{style}">{tail}</span>' if style else tail)
        output.append("".join(spans) or "&nbsp;")
    return "\n".join(output)


def cli_markup(data_dir: Path) -> str:
    environment = dict(os.environ)
    environment["TOKONOMY_COLOR"] = "always"
    environment["PYTHONIOENCODING"] = "utf-8"
    command = [str(PYTHON), "-m", "tokonomy", "dashboard", "--no-refresh", "--data-dir", str(data_dir)]
    result = subprocess.run(
        command, cwd=ROOT, env=environment, capture_output=True, text=True,
        encoding="utf-8", errors="replace", timeout=180,
    )
    if result.returncode != 0:
        raise SystemExit(f"CLI failed: {result.stderr[-500:]}")
    output = ansi_to_html(
        result.stdout
        .replace(str(data_dir / "tokonomy.sqlite3"), "~/tokonomy/tokonomy.sqlite3")
        .replace(str(data_dir), "~/tokonomy")
        .rstrip()
    )
    return f"""<!doctype html><html><head><meta charset="utf-8"><style>
    * {{ box-sizing: border-box; }}
    body {{ margin:0; width:1500px; height:960px; background:
      radial-gradient(900px 500px at 18% 0%, rgba(126,231,135,0.16), transparent 60%),
      radial-gradient(700px 400px at 90% 10%, rgba(108,182,255,0.10), transparent 55%),
      #050807; display:flex; align-items:center; justify-content:center; }}
    .window {{ width:1320px; border-radius:16px; overflow:hidden; border:1px solid rgba(126,231,135,0.20);
      box-shadow: 0 40px 120px rgba(0,0,0,0.65), 0 0 0 1px rgba(0,0,0,0.5); background:#0a0e0c; }}
    .bar {{ height:44px; background:linear-gradient(180deg,#161d18,#0e1310); display:flex; align-items:center;
      padding:0 16px; gap:8px; border-bottom:1px solid rgba(255,255,255,0.06); }}
    .dot {{ width:11px; height:11px; border-radius:50%; }}
    .title {{ color:#8b9a91; font: 12px "Cascadia Code", Consolas, monospace; margin:0 auto; }}
    .body {{ padding:18px 22px 22px; }}
    .prompt {{ color:#7ee787; font:600 14px "Cascadia Code", Consolas, monospace; margin-bottom:10px; }}
    .prompt .arrow {{ color:#6cb6ff; }}
    pre {{ margin:0; color:#dbe6df; font:14px/1.55 "Cascadia Code", "Consolas", monospace; white-space:pre; }}
    .cursor {{ display:inline-block; width:8px; height:16px; background:#7ee787; vertical-align:-2px; opacity:.8; }}
    </style></head><body>
    <div class="window">
      <div class="bar"><span class="dot" style="background:#ff5f57"></span><span class="dot" style="background:#febc2e"></span>
      <span class="dot" style="background:#28c840"></span><span class="title">tokonomy — local AI usage observatory</span></div>
      <div class="body">
        <div class="prompt">~/tokonomy <span class="arrow">❯</span> tokonomy dashboard</div>
        <pre>{output}</pre>
        <pre>~/tokonomy <span class="arrow">❯</span> <span class="cursor"></span></pre>
      </div>
    </div></body></html>"""


def dashboard_markup(data_dir: Path) -> str:
    from tokonomy.store import Store
    from tokonomy.web import render_dashboard

    store = Store(Path(data_dir) / "tokonomy.sqlite3")
    try:
        return render_dashboard(store)
    finally:
        store.close()


def screenshot(browser: str, page: Path, target: Path, width: int, height: int, scale: float = 2.0):
    profile = Path(tempfile.gettempdir()) / "tokonomy-chrome-profile"
    command = [
        browser, "--headless=new", "--disable-gpu", "--hide-scrollbars",
        f"--force-device-scale-factor={scale}", f"--window-size={width},{height}",
        f"--user-data-dir={profile}", f"--screenshot={target}", page.resolve().as_uri(),
    ]
    result = subprocess.run(command, capture_output=True, text=True, timeout=120)
    if not target.exists():
        raise SystemExit(f"Screenshot failed: {result.stderr[-800:]}")


def main() -> int:
    DOCS.mkdir(exist_ok=True)
    browser = find_browser()
    from make_demo_db import build as build_demo

    with tempfile.TemporaryDirectory() as directory:
        temp = Path(directory)
        demo_dir = temp / "demo-data"
        build_demo(demo_dir / "tokonomy.sqlite3")

        cli_page = temp / "cli.html"
        cli_page.write_text(cli_markup(demo_dir), encoding="utf-8")
        screenshot(browser, cli_page, DOCS / "cli.png", 1500, 960, 2.0)
        print("wrote docs/cli.png")

        dashboard_page = temp / "dashboard.html"
        dashboard_page.write_text(dashboard_markup(demo_dir), encoding="utf-8")
        screenshot(browser, dashboard_page, DOCS / "dashboard.png", 1440, 2880, 1.3)
        (DOCS / "dashboard.html").write_text(dashboard_page.read_text(encoding="utf-8"), encoding="utf-8")
        print("wrote docs/dashboard.png and docs/dashboard.html")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
