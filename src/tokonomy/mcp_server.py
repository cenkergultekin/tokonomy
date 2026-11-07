"""A dependency-free MCP stdio server for tokonomy.

Exposes local usage, quota and budget context to coding agents so they can
reason about the cost of the work they are about to do. The server speaks
JSON-RPC 2.0 over newline-delimited stdin/stdout and never leaves localhost.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from tokonomy import __version__, metrics
from tokonomy.store import Store

PROTOCOL_VERSION = "2025-06-18"

TOOLS = [
    {
        "name": "usage_summary",
        "description": (
            "Cache-aware token totals, session count, estimated spend and cache savings "
            "for the last N days. Use before planning a large task to see the current pace."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {"days": {"type": "integer", "minimum": 1, "maximum": 365, "default": 30}},
            "additionalProperties": False,
        },
    },
    {
        "name": "quota_status",
        "description": (
            "Latest source-reported quota windows (used percent, reset time) plus a recent burn-rate "
            "forecast. Call this before starting a long agent run."
        ),
        "inputSchema": {"type": "object", "properties": {}, "additionalProperties": False},
    },
    {
        "name": "project_breakdown",
        "description": "Token usage and estimated spend grouped by project for the last N days.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "days": {"type": "integer", "minimum": 1, "maximum": 365, "default": 30},
                "limit": {"type": "integer", "minimum": 1, "maximum": 50, "default": 10},
            },
            "additionalProperties": False,
        },
    },
    {
        "name": "model_compare",
        "description": "Compare models by sessions, uncached input, output, cache hit rate and estimated spend.",
        "inputSchema": {
            "type": "object",
            "properties": {"days": {"type": "integer", "minimum": 1, "maximum": 365, "default": 30}},
            "additionalProperties": False,
        },
    },
    {
        "name": "recent_sessions",
        "description": "Most recent sessions with project, model, tokens and estimated cost.",
        "inputSchema": {
            "type": "object",
            "properties": {"limit": {"type": "integer", "minimum": 1, "maximum": 100, "default": 10}},
            "additionalProperties": False,
        },
    },
    {
        "name": "budget_check",
        "description": (
            "Check whether estimated spend over the last N days is under a USD budget. "
            "Returns ok=false when the budget is exceeded, ok=null when prices are unknown."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "max_usd": {"type": "number", "minimum": 0},
                "days": {"type": "integer", "minimum": 1, "maximum": 365, "default": 7},
            },
            "required": ["max_usd"],
            "additionalProperties": False,
        },
    },
    {
        "name": "coverage",
        "description": "Which sources are imported, whether events or session totals back them, and data-quality notes.",
        "inputSchema": {"type": "object", "properties": {}, "additionalProperties": False},
    },
    {
        "name": "weekly_digest",
        "description": "A compact digest of the last week: totals, projects, models and quota alerts.",
        "inputSchema": {
            "type": "object",
            "properties": {"days": {"type": "integer", "minimum": 1, "maximum": 31, "default": 7}},
            "additionalProperties": False,
        },
    },
]


def _with_store(data_dir: Path, function):
    store = Store(Path(data_dir) / "tokonomy.sqlite3")
    try:
        return function(store.connection)
    finally:
        store.close()


def call_tool(name: str, arguments: dict, data_dir: Path) -> dict:
    days = int(arguments.get("days", 30) or 30)
    if name == "usage_summary":
        return _with_store(data_dir, lambda connection: metrics.summary(connection, days))
    if name == "quota_status":
        return _with_store(data_dir, metrics.quota)
    if name == "project_breakdown":
        limit = int(arguments.get("limit", 10) or 10)
        return _with_store(data_dir, lambda connection: metrics.projects(connection, days, limit))
    if name == "model_compare":
        return _with_store(data_dir, lambda connection: metrics.model_breakdown(connection, days))
    if name == "recent_sessions":
        limit = int(arguments.get("limit", 10) or 10)
        return _with_store(data_dir, lambda connection: metrics.recent_sessions(connection, limit))
    if name == "budget_check":
        limit_usd = arguments.get("max_usd")
        if not isinstance(limit_usd, (int, float)):
            raise ValueError("max_usd is required and must be a number")
        budget_days = int(arguments.get("days", 7) or 7)
        return _with_store(data_dir, lambda connection: metrics.budget_check(connection, float(limit_usd), budget_days))
    if name == "coverage":
        return _with_store(data_dir, metrics.coverage)
    if name == "weekly_digest":
        digest_days = int(arguments.get("days", 7) or 7)
        return _with_store(data_dir, lambda connection: metrics.digest(connection, digest_days))
    raise ValueError(f"Unknown tool: {name}")


def handle(request: dict, data_dir: Path) -> dict | None:
    method = request.get("method")
    request_id = request.get("id")
    if method is None:
        return None
    if request_id is None:
        # Notifications, including notifications/initialized, need no reply.
        return None
    if method == "initialize":
        return {
            "jsonrpc": "2.0",
            "id": request_id,
            "result": {
                "protocolVersion": PROTOCOL_VERSION,
                "capabilities": {"tools": {"listChanged": False}},
                "serverInfo": {"name": "tokonomy", "version": __version__},
                "instructions": (
                    "Local, cache-aware AI usage data. Call quota_status before long runs and "
                    "budget_check when the user mentions a spending limit."
                ),
            },
        }
    if method == "ping":
        return {"jsonrpc": "2.0", "id": request_id, "result": {}}
    if method == "tools/list":
        return {"jsonrpc": "2.0", "id": request_id, "result": {"tools": TOOLS}}
    if method == "tools/call":
        params = request.get("params") or {}
        name = params.get("name")
        arguments = params.get("arguments") or {}
        try:
            result = call_tool(str(name), arguments, data_dir)
            return {
                "jsonrpc": "2.0",
                "id": request_id,
                "result": {
                    "content": [{"type": "text", "text": json.dumps(result, indent=2, default=str)}],
                    "isError": False,
                },
            }
        except Exception as error:  # tool errors are reported in-band
            return {
                "jsonrpc": "2.0",
                "id": request_id,
                "result": {
                    "content": [{"type": "text", "text": f"{type(error).__name__}: {error}"}],
                    "isError": True,
                },
            }
    return {
        "jsonrpc": "2.0",
        "id": request_id,
        "error": {"code": -32601, "message": f"Method not found: {method}"},
    }


def run(data_dir: Path) -> int:
    """Serve until stdin closes. Protocol errors stay on stdout, logs on stderr."""
    print(f"tokonomy MCP server v{__version__} ready", file=sys.stderr, flush=True)
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            request = json.loads(line)
        except ValueError:
            response = {
                "jsonrpc": "2.0",
                "id": None,
                "error": {"code": -32700, "message": "Parse error"},
            }
        else:
            try:
                response = handle(request, data_dir)
            except Exception as error:  # defensive: never kill the server
                response = {
                    "jsonrpc": "2.0",
                    "id": request.get("id"),
                    "error": {"code": -32603, "message": f"{type(error).__name__}: {error}"},
                }
        if response is not None:
            sys.stdout.write(json.dumps(response, ensure_ascii=False) + "\n")
            sys.stdout.flush()
    return 0
