import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from tokonomy.models import Session, UsageEvent
from tokonomy.store import Store
from tokonomy.web import export_html, render_dashboard


class WebTests(unittest.TestCase):
    def test_dashboard_is_self_contained_and_privacy_safe(self):
        with tempfile.TemporaryDirectory() as directory:
            store = Store(Path(directory) / "test.sqlite3")
            now = datetime.now(timezone.utc).isoformat()
            store.upsert_session(Session(
                "codex", "session-123", started_at=now, last_seen_at=now, model="gpt-5",
                input_tokens=10_000, cached_input_tokens=8_000, output_tokens=1_000,
                source_file=r"C:\private\project\transcript.jsonl",
                usage_events=(UsageEvent("e1", now, "gpt-5", 10_000, 1_000, 8_000),),
            ))
            markup = render_dashboard(store)
            self.assertIn("Uncached input", markup)
            self.assertIn("Quota", markup)
            self.assertIn("Sources", markup)
            self.assertNotIn("CDN", markup)
            self.assertNotIn(r"C:\private", markup)
            self.assertNotIn("transcript.jsonl", markup)
            target = Path(directory) / "dashboard.html"
            export_html(store, target)
            self.assertIn("<!doctype html>", target.read_text(encoding="utf-8"))
            with self.assertRaises(FileExistsError):
                export_html(store, target)
            store.close()

    def test_empty_database_still_renders(self):
        with tempfile.TemporaryDirectory() as directory:
            store = Store(Path(directory) / "empty.sqlite3")
            markup = render_dashboard(store)
            self.assertIn("No dated usage yet", markup)
            self.assertIn("No quota snapshots", markup)
            store.close()


if __name__ == "__main__":
    unittest.main()
