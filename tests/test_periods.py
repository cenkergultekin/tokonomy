import tempfile
import unittest
from pathlib import Path
from tokonomy.store import Store
from tokonomy.models import Session, UsageEvent
from tokonomy.periods import window_report

class PeriodTests(unittest.TestCase):
    def test_window_excludes_old_usage_and_distinguishes_opened(self):
        with tempfile.TemporaryDirectory() as directory:
            store=Store(Path(directory)/'test.sqlite3')
            events=(UsageEvent('old','2026-11-07T08:59:59+00:00','m',999,999),UsageEvent('inside','2026-11-07T10:00:00+00:00','m',100,20,50,None),UsageEvent('future','2026-11-07T13:00:00+00:00','m',999,999))
            store.upsert_session(Session('codex','continued',started_at='2026-11-06T10:00:00+00:00',usage_events=events))
            snapshot={'provider':'codex','resets_at':'2026-11-07T14:00:00+00:00','window_seconds':18000,'captured_at':'2026-11-07T12:00:00+00:00'}
            r=window_report(store.connection,snapshot)
            self.assertEqual(r['opened'],0)
            self.assertEqual(len(r['rows']),1)
            self.assertEqual(r['totals'],[100,20,50,None])
            self.assertEqual(r['medians'][0],100)
            store.close()

if __name__=='__main__': unittest.main()
