"""Human-friendly formatting shared by the CLI, TUI, web dashboard and MCP."""

from __future__ import annotations

from pathlib import Path


def compact(value: float | int | None, digits: int = 2) -> str:
    """1234567 -> 1.23M, 18400 -> 18.4K. None stays an em dash, never zero."""
    if value is None:
        return "n/a"
    number = float(value)
    sign = "-" if number < 0 else ""
    number = abs(number)
    for limit, suffix in ((1_000_000_000, "B"), (1_000_000, "M"), (1_000, "K")):
        if number >= limit:
            scaled = number / limit
            text = f"{scaled:.{digits}f}".rstrip("0").rstrip(".")
            return f"{sign}{text}{suffix}"
    if number >= 100:
        return f"{sign}{number:,.0f}"
    if number >= 10:
        return f"{sign}{number:.1f}".rstrip("0").rstrip(".")
    return f"{sign}{number:.2f}".rstrip("0").rstrip(".") if number % 1 else f"{sign}{number:.0f}"


def money(value: float | None, currency: str = "$") -> str:
    if value is None:
        return "n/a"
    if value == 0:
        return f"{currency}0.00"
    if abs(value) < 0.01:
        return f"{currency}{value:.4f}"
    return f"{currency}{value:,.2f}"


def pct(value: float | None, digits: int = 1) -> str:
    if value is None:
        return "n/a"
    return f"{value:.{digits}f}%"


def project_name(path: str | None) -> str:
    """Readable project label for POSIX and Windows paths."""
    if not path:
        return "Unattributed"
    cleaned = path.replace("\\", "/").rstrip("/")
    if not cleaned:
        return "Unattributed"
    home = str(Path.home()).replace("\\", "/").rstrip("/").lower()
    lowered = cleaned.lower()
    if lowered == home or re_home(lowered):
        return "Home"
    name = Path(cleaned).name
    return name or cleaned


def re_home(lowered: str) -> bool:
    """Recognise another machine's home directory without leaking a username."""
    import re

    return bool(re.fullmatch(r"/users/[^/]+", lowered) or re.fullmatch(r"/home/[^/]+", lowered))


def short_time(value: str | None) -> str:
    if not value:
        return "n/a"
    return value.replace("T", " ").split("+", 1)[0].split(".")[0]


def short_date(value: str | None) -> str:
    if not value:
        return "n/a"
    return value[:10]


def relative_reset(resets_at: str | None, now=None) -> str:
    from datetime import datetime, timezone

    if not resets_at:
        return "unknown"
    try:
        reset = datetime.fromisoformat(resets_at)
    except ValueError:
        return "unknown"
    current = now or datetime.now(timezone.utc)
    seconds = (reset - current).total_seconds()
    if seconds <= 0:
        return "reset passed"
    minutes = int(seconds // 60)
    if minutes < 60:
        return f"{minutes}m"
    hours, minutes = divmod(minutes, 60)
    if hours < 24:
        return f"{hours}h {minutes:02d}m"
    days, hours = divmod(hours, 24)
    return f"{days}d {hours}h"
