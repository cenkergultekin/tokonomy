"""Dated, user-overridable model price table.

tokonomy never presents a derived number as real spend. Every cost from this
module is an estimate: the source does not report invoice values. Missing or
unknown model prices stay ``None`` instead of silently falling back to zero.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

# USD per 1M tokens. Defaults are public list prices for the model families the
# tool commonly sees; override them with <data-dir>/pricing.json.
DEFAULT_RATES = (
    # pattern, input, cached input, cache write, output
    ("claude-opus", 15.0, 1.5, 18.75, 75.0),
    ("claude-sonnet", 3.0, 0.3, 3.75, 15.0),
    ("claude-haiku", 0.8, 0.08, 1.0, 4.0),
    ("gpt-6", 1.25, 0.125, 1.25, 10.0),
    ("gpt-5", 1.25, 0.125, 1.25, 10.0),
    ("gpt-4o", 2.5, 1.25, 2.5, 10.0),
    ("o4", 2.0, 0.5, 2.0, 8.0),
    ("o3", 2.0, 0.5, 2.0, 8.0),
    ("gemini-2.5-pro", 1.25, 0.31, 1.25, 10.0),
    ("gemini-2.5-flash", 0.3, 0.075, 0.3, 2.5),
)

PRICING_SOURCE = "public list prices, edited locally; estimates only"


def _normalise(pattern: str) -> str:
    return pattern.lower().strip()


def _default_data_dir() -> Path:
    base = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local")) / "tokonomy"
    pointer = base / "active-directory.txt"
    return Path(pointer.read_text(encoding="utf-8").strip()) if pointer.exists() else base


def load_pricing(data_dir: Path | None = None) -> list[tuple[str, float, float, float, float]]:
    """Default table merged with an optional local override file."""
    rates = {pattern: (pattern, i, c, w, o) for pattern, i, c, w, o in DEFAULT_RATES}
    if data_dir is None:
        data_dir = _default_data_dir()
    if data_dir:
        override = Path(data_dir) / "pricing.json"
        try:
            payload = json.loads(override.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            payload = None
        if isinstance(payload, dict):
            for key, value in payload.items():
                if not isinstance(value, dict):
                    continue
                pattern = _normalise(key)
                if pattern in {"source", "note", "currency"}:
                    continue
                try:
                    rates[pattern] = (
                        pattern,
                        float(value["input"]),
                        float(value.get("cached_input", value["input"])),
                        float(value.get("cache_write", value["input"])),
                        float(value["output"]),
                    )
                except (KeyError, TypeError, ValueError):
                    continue
    return sorted(rates.values(), key=lambda row: len(row[0]), reverse=True)


def rate_for(model: str | None, table) -> tuple[float, float, float, float] | None:
    if not model:
        return None
    name = _normalise(model)
    for pattern, input_rate, cached_rate, cache_write_rate, output_rate in table:
        if name.startswith(pattern) or pattern in name:
            return input_rate, cached_rate, cache_write_rate, output_rate
    return None


def estimate(
    source: str,
    model: str | None,
    input_tokens: int | None,
    cached_tokens: int | None,
    cache_write_tokens: int | None,
    output_tokens: int | None,
    table,
) -> float | None:
    """Estimated USD for one model bucket, or None when unpriceable.

    OpenAI-style sources report ``input_tokens`` inclusive of cached tokens;
    Anthropic-style sources report cached tokens separately.
    """
    rates = rate_for(model, table)
    if rates is None:
        return None
    input_rate, cached_rate, cache_write_rate, output_rate = rates
    if input_tokens is None and cached_tokens is None and output_tokens is None:
        return None
    cached = cached_tokens or 0
    if source == "codex":
        uncached = max((input_tokens or 0) - cached, 0)
    else:
        uncached = input_tokens or 0
    total = (
        uncached * input_rate
        + cached * cached_rate
        + (cache_write_tokens or 0) * cache_write_rate
        + (output_tokens or 0) * output_rate
    ) / 1_000_000
    return round(total, 6)
