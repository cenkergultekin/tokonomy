import tempfile
import unittest
from pathlib import Path

from tokonomy.store import Store


class VersioningTests(unittest.TestCase):
    def test_parser_version_invalidates_scan_cache(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "session.jsonl"
            source.write_text("{}\n", encoding="utf-8")
            store = Store(Path(directory) / "test.sqlite3")
            store.mark_file_scanned("codex", source, 1)
            self.assertTrue(store.has_scanned_file("codex", source, 1))
            self.assertFalse(store.has_scanned_file("codex", source, 2))
            store.mark_file_scanned("codex", source, 2)
            self.assertTrue(store.has_scanned_file("codex", source, 2))
            store.close()

    def test_sources_are_enabled_by_default_and_deletable(self):
        with tempfile.TemporaryDirectory() as directory:
            store = Store(Path(directory) / "test.sqlite3")
            self.assertTrue(store.source_enabled("codex"))
            store.set_source_enabled("codex", False)
            self.assertFalse(store.source_enabled("codex"))
            self.assertTrue(store.source_enabled("claude-code"))
            store.close()


if __name__ == "__main__":
    unittest.main()
