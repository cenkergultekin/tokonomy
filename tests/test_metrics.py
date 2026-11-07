import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from tokonomy.models import LimitSnapshot, Session, UsageEvent
from tokonomy.store import Store
from tokonomy import metrics


def make_store(directory):
    return Store(Path(directory) / "test.sqlite3")


class MetricTests(unittest.TestCase):
    def test_codex_input_is_cache_inclusive_and_claude_is_exclusive(self):
        with tempfile.TemporaryDirectory() as directory:
            store = make_store(directory)
            now = datetime.now(timezone.utc).isoformat()
            store.upsert_session(Session(
                "codex", "codex-1", started_at=now, last_seen_at=now, model="gpt-5",
                input_tokens=1_000_000, cached_input_tokens=900_000,
                output_tokens=100_000, usage_events=(
                    UsageEvent("c1", now, "gpt-5", 1_000_000, 100_000, 900_000),
                ),
            ))
            store.upsert_session(Session(
                "claude-code", "claude-1", started_at=now, last_seen_at=now, model="claude-sonnet-5",
                input_tokens=1_000, cached_input_tokens=9_000, output_tokens=1_000,
                usage_events=(
                    UsageEvent("m1", now, "claude-sonnet-5", 1_000, 1_000, 9_000),
                ),
            ))
            summary = metrics.summary(store.connection)
            self.assertEqual(summary["uncached"], 101_000)
            self.assertEqual(summary["cached"], 909_000)
            self.assertAlmostEqual(summary["cache_hit"], 909_000 / 1_010_000 * 100, places=4)
            self.assertAlmostEqual(summary["cost"], 1.2375 + 0.0207, places=4)
            self.assertEqual(summary["sessions"], 2)
            models = {item["model"]: item for item in metrics.model_breakdown(store.connection)}
            self.assertEqual(models["gpt-5"]["sessions"], 1)
            self.assertAlmostEqual(models["gpt-5"]["cost"], 1.2375, places=4)
            store.close()

    def test_unknown_model_price_stays_unknown(self):
        with tempfile.TemporaryDirectory() as directory:
            store = make_store(directory)
            now = datetime.now(timezone.utc).isoformat()
            store.upsert_session(Session(
                "hermes", "h1", started_at=now, last_seen_at=now, model="mystery-model",
                input_tokens=10_000, output_tokens=10_000,
            ))
            summary = metrics.summary(store.connection)
            self.assertIsNone(summary["cost"])
            self.assertEqual(summary["uncached"], 10_000)
            self.assertEqual(summary["cost_coverage"], 0)
            store.close()

    def test_daily_uses_events_and_fills_missing_days(self):
        with tempfile.TemporaryDirectory() as directory:
            store = make_store(directory)
            now = datetime.now(timezone.utc).replace(microsecond=0)
            store.upsert_session(Session(
                "codex", "c1", started_at=(now - timedelta(days=1)).isoformat(),
                last_seen_at=now.isoformat(), model="gpt-5",
                usage_events=(UsageEvent("e1", now.isoformat(), "gpt-5", 1000, 100, 0),),
            ))
            rows = metrics.daily(store.connection, 3)
            self.assertEqual(len(rows), 3)
            self.assertEqual(rows[-1]["uncached"], 1000)
            self.assertEqual(rows[-1]["output"], 100)
            self.assertEqual(rows[0]["uncached"], 0)
            store.close()

    def test_quota_forecast_detects_early_exhaustion(self):
        with tempfile.TemporaryDirectory() as directory:
            store = make_store(directory)
            now = datetime(2026, 11, 7, 12, 0, tzinfo=timezone.utc)
            reset = now + timedelta(hours=3)
            for hours_ago, percent in ((2, 10.0), (1, 50.0), (0, 70.0)):
                captured = now - timedelta(hours=hours_ago)
                store.save_limit_snapshot(LimitSnapshot(
                    provider="codex", limit_id="codex", plan_type="plus",
                    window_seconds=18000, used_percent=percent,
                    captured_at=captured.isoformat(), resets_at=reset.isoformat(),
                ))
            rows = metrics.quota(store.connection, now=now)
            self.assertEqual(len(rows), 1)
            forecast = rows[0]["forecast"]
            self.assertGreater(forecast["rate_per_hour"], 0)
            self.assertEqual(forecast["status"], "exhausts_before_reset")
            self.assertLess(forecast["eta_hours"], forecast["hours_to_reset"])
            store.close()

    def test_budget_check_reports_unknown_when_unpriced(self):
        with tempfile.TemporaryDirectory() as directory:
            store = make_store(directory)
            now = datetime.now(timezone.utc).isoformat()
            store.upsert_session(Session("cursor", "x", started_at=now, last_seen_at=now))
            result = metrics.budget_check(store.connection, 5.0, 7)
            self.assertIsNone(result["ok"])
            self.assertIsNone(result["spend"])
            store.close()


if __name__ == "__main__":
    unittest.main()
