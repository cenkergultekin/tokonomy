"""Compact terminal rendition of the single-piece token mark."""
from rich.text import Text
from textual.widgets import Static


class TokenOrbit(Static):
    def render(self):
        result = Text(no_wrap=True, overflow="crop")
        result.append(" ▟▛▜▙\n", "#e5b38a")
        result.append(" ▌ ▐▌", "#e5b38a")
        result.append("   tokonomy\n", "bold #f3e9da")
        result.append(" ▜▙▟▛", "#e5b38a")
        return result
