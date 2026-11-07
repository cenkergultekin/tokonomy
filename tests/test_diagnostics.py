import tempfile,unittest
from pathlib import Path
from tokonomy.store import Store
from tokonomy.models import Session,UsageEvent
from tokonomy.diagnostics import audit
class AuditTests(unittest.TestCase):
 def test_detects_mismatch_and_missing_event_coverage(self):
  with tempfile.TemporaryDirectory() as d:
   s=Store(Path(d)/'db'); s.upsert_session(Session('codex','a',input_tokens=10,usage_events=(UsageEvent('x','2026-11-07T10:00:00+00:00','m',20,None),)))
   s.upsert_session(Session('cursor','b'))
   rows={name:(state,detail) for name,state,detail in audit(s.connection)}
   self.assertEqual(rows['codex event/session accounting'][0],'warning')
   self.assertIn('Not verifiable',rows['cursor event/session accounting'][1]); s.close()
if __name__=='__main__':unittest.main()
