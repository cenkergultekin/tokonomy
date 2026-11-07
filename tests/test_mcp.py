import json
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from tokonomy.mcp_server import handle
from tokonomy.models import Session, UsageEvent
from tokonomy.store import Store


class McpTests(unittest.TestCase):
    def test_initialize_tools_and_call(self):
        with tempfile.TemporaryDirectory() as directory:
            data = Path(directory)
            store = Store(data / "tokonomy.sqlite3")
            now = datetime.now(timezone.utc).isoformat()
            store.upsert_session(Session(
                "codex", "s1", started_at=now, last_seen_at=now, model="gpt-5",
                input_tokens=1000, cached_input_tokens=500, output_tokens=100,
                usage_events=(UsageEvent("e1", now, "gpt-5", 1000, 100, 500),),
            ))
            store.close()

            init = handle({"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}}, data)
            self.assertEqual(init["result"]["protocolVersion"], "2025-06-18")
            self.assertIn("tools", init["result"]["capabilities"])

            listed = handle({"jsonrpc": "2.0", "id": 2, "method": "tools/list"}, data)
            names = [tool["name"] for tool in listed["result"]["tools"]]
            self.assertIn("quota_status", names)
            self.assertIn("budget_check", names)

            called = handle({
                "jsonrpc": "2.0", "id": 3, "method": "tools/call",
                "params": {"name": "usage_summary", "arguments": {"days": 7}},
            }, data)
            payload = json.loads(called["result"]["content"][0]["text"])
            self.assertEqual(payload["uncached"], 500)
            self.assertEqual(payload["cached"], 500)
            self.assertFalse(called["result"]["isError"])

            unknown = handle({"jsonrpc": "2.0", "id": 4, "method": "tools/call",
                              "params": {"name": "nope", "arguments": {}}}, data)
            self.assertTrue(unknown["result"]["isError"])

    def test_notifications_get_no_response(self):
        with tempfile.TemporaryDirectory() as directory:
            response = handle({"jsonrpc": "2.0", "method": "notifications/initialized"}, Path(directory))
            self.assertIsNone(response)


if __name__ == "__main__":
    unittest.main()
