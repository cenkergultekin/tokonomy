import json
import os
import queue
import shutil
import subprocess
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from tokonomy.models import LimitSnapshot


def _command() -> list[str]:
    local = Path(os.environ.get("LOCALAPPDATA", "")) / "Programs" / "OpenAI" / "Codex" / "bin" / "codex.exe"
    if local.is_file():
        return [str(local), "app-server"]
    for name in ("codex.exe", "codex"):
        executable = shutil.which(name)
        if executable:
            return [executable, "app-server"]
    cmd = shutil.which("codex.cmd")
    if cmd:
        return [os.environ.get("COMSPEC", "cmd.exe"), "/d", "/s", "/c", f'"{cmd}" app-server']
    raise FileNotFoundError("Codex CLI app-server was not found")


def _request(process: subprocess.Popen[str], lines: queue.Queue[str | None], message: dict[str, Any], request_id: int) -> dict[str, Any]:
    assert process.stdin is not None and process.stdout is not None
    process.stdin.write(json.dumps(message, separators=(",", ":")) + "\n")
    process.stdin.flush()
    deadline = time.monotonic() + 25
    while time.monotonic() < deadline:
        try:
            line = lines.get(timeout=max(0.05, deadline - time.monotonic()))
        except queue.Empty:
            break
        if line is None:
            break
        try:
            response = json.loads(line)
        except json.JSONDecodeError:
            continue
        if response.get("id") == request_id:
            if "error" in response:
                error = response.get("error")
                code = error.get("code") if isinstance(error, dict) else "unknown"
                raise RuntimeError(f"Codex app-server method {message.get('method')} returned protocol error {code}")
            result = response.get("result")
            return result if isinstance(result, dict) else {}
    raise TimeoutError("Codex app-server request timed out")


def read_rate_limits() -> list[LimitSnapshot]:
    process = subprocess.Popen(
        _command(), stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
        text=True, encoding="utf-8", errors="replace", bufsize=1,
    )
    lines: queue.Queue[str | None] = queue.Queue()

    def read_stdout() -> None:
        assert process.stdout is not None
        for line in process.stdout:
            lines.put(line)
        lines.put(None)

    threading.Thread(target=read_stdout, daemon=True).start()
    try:
        _request(process, lines, {
            "id": 1,
            "method": "initialize",
            "params": {"clientInfo": {"name": "tokonomy", "version": "0.1.0"}},
        }, 1)
        assert process.stdin is not None
        process.stdin.write('{"method":"initialized"}\n')
        process.stdin.flush()
        result = _request(process, lines, {
            "id": 2,
            "method": "account/rateLimits/read",
        }, 2)
    finally:
        if process.stdin:
            process.stdin.close()
        try:
            process.wait(timeout=2)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait()

    captured_at = datetime.now(timezone.utc).isoformat()
    snapshots: list[LimitSnapshot] = []
    buckets = result.get("rateLimitsByLimitId")
    if not isinstance(buckets, dict):
        fallback = result.get("rateLimits")
        buckets = {fallback.get("limitId") or "codex": fallback} if isinstance(fallback, dict) else {}
    for limit_id, bucket in buckets.items():
        if not isinstance(bucket, dict):
            continue
        plan_type = bucket.get("planType") if isinstance(bucket.get("planType"), str) else None
        for key in ("primary", "secondary"):
            window = bucket.get(key)
            if not isinstance(window, dict):
                continue
            duration_mins = window.get("windowDurationMins")
            used = window.get("usedPercent")
            if not isinstance(duration_mins, int) or not isinstance(used, int):
                continue
            seconds = duration_mins * 60
            reset_raw = window.get("resetsAt")
            resets_at = datetime.fromtimestamp(reset_raw, timezone.utc).isoformat() if isinstance(reset_raw, (int, float)) else None
            snapshots.append(LimitSnapshot(
                provider="codex",
                limit_id=str(limit_id),
                plan_type=plan_type,
                window_seconds=seconds,
                used_percent=used,
                captured_at=captured_at,
                resets_at=resets_at,
                exhausted=(used >= 100),
            ))
    return snapshots
