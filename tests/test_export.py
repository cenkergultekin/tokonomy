import json,tempfile,unittest
from pathlib import Path
from tokonomy.store import Store
from tokonomy.models import Session
from tokonomy.exporting import export
class ExportTests(unittest.TestCase):
 def test_privacy_nulls_and_no_overwrite(self):
  with tempfile.TemporaryDirectory() as d:
   store=Store(Path(d)/'db'); store.upsert_session(Session('cursor','example',source_file='private/path',input_tokens=None))
   path=Path(d)/'export.jsonl'; export(store.connection,path)
   data=path.read_text(encoding='utf-8'); self.assertNotIn('private/path',data)
   rows=[json.loads(line) for line in data.splitlines()]
   self.assertEqual(rows[0]['schema_version'],1)
   self.assertIsNone(next(r for r in rows if r['type']=='session')['data']['input_tokens'])
   with self.assertRaises(FileExistsError): export(store.connection,path)
   store.close()
if __name__=='__main__': unittest.main()
