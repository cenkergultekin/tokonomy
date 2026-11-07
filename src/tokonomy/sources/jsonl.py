import gzip
import json
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import zstandard


def iter_jsonl(path: Path) -> Iterator[dict[str, Any]]:
    """Yield parsed records without copying or storing source transcript files."""
    opener = gzip.open if path.suffix == ".gz" else open
    if path.name.endswith(".zst"):
        with path.open("rb") as raw, zstandard.ZstdDecompressor().stream_reader(raw) as reader:
            import io

            text = io.TextIOWrapper(reader, encoding="utf-8", errors="replace")
            for line in text:
                try:
                    value = json.loads(line)
                except (json.JSONDecodeError, RecursionError):
                    continue
                if isinstance(value, dict):
                    yield value
        return
    with opener(path, "rt", encoding="utf-8", errors="replace") as stream:
        for line in stream:
            try:
                value = json.loads(line)
            except (json.JSONDecodeError, RecursionError):
                continue
            if isinstance(value, dict):
                yield value
