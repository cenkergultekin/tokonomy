"""The shared token geometry rendered in terminal cells."""
from rich.text import Text
from textual.widgets import Static
from tokonomy.brand import terminal_logo


class TokenOrbit(Static):
    def render(self):
        result = Text(no_wrap=True, overflow="crop")
        rows = terminal_logo()
        for index, row in enumerate(rows):
            result.append(row, "#e5b38a")
            if index == len(rows) // 2 - 1:
                result.append("   tokonomy", "bold #f3e9da")
            if index < len(rows) - 1:
                result.append('\n')
        return result
