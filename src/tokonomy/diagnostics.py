"""Read-only accounting audits; warnings never rewrite observations."""
import sqlite3
from textual.screen import ModalScreen
from textual.widgets import Static, Footer
from textual.containers import VerticalScroll


def audit(connection):
    results=[]
    integrity=[r[0] for r in connection.execute('PRAGMA quick_check')]
    results.append(('Database integrity','ok' if integrity==['ok'] else 'error', '; '.join(integrity)))
    for source, in connection.execute('SELECT DISTINCT source FROM sessions ORDER BY source'):
        duplicates=connection.execute('SELECT COUNT(*) FROM (SELECT event_id FROM usage_events WHERE source=? GROUP BY event_id HAVING COUNT(*)>1)',(source,)).fetchone()[0]
        results.append((source+' duplicate event IDs','warning' if duplicates else 'ok',str(duplicates)))
        mismatches=0
        for field in ['input_tokens','output_tokens','cached_input_tokens','cache_write_tokens']:
            count=connection.execute(f'SELECT COUNT(*) FROM sessions s JOIN (SELECT source,session_id,SUM({field}) AS total FROM usage_events GROUP BY source,session_id) e USING(source,session_id) WHERE s.source=? AND s.{field} IS NOT e.total',(source,)).fetchone()[0]
            mismatches+=count
        events=connection.execute('SELECT COUNT(*) FROM usage_events WHERE source=?',(source,)).fetchone()[0]
        results.append((source+' event/session accounting','info' if not events else 'warning' if mismatches else 'ok',f'{mismatches} field mismatches' if events else 'Not verifiable: no timestamped events'))
        coverage=connection.execute('SELECT COUNT(*),COUNT(input_tokens),COUNT(output_tokens) FROM sessions WHERE source=?',(source,)).fetchone()
        results.append((source+' coverage','info',f'{coverage[0]} sessions; input known {coverage[1]}; output known {coverage[2]}'))
    orphan=connection.execute('SELECT COUNT(*) FROM session_context x LEFT JOIN sessions s ON s.source=x.source AND s.session_id=x.parent_id WHERE x.parent_id IS NOT NULL AND s.session_id IS NULL').fetchone()[0]
    results.append(('Parent relationships','warning' if orphan else 'ok',f'{orphan} parents absent from local records'))
    return results


class Diagnostics(ModalScreen):
    BINDINGS=[('escape','dismiss','Back')]
    def __init__(self,directory): super().__init__(); self.directory=directory
    def compose(self):
        with VerticalScroll(): yield Static('Checking...',id='audit',markup=False)
        yield Footer()
    def on_mount(self):
        path=self.directory/'tokonomy.sqlite3'
        connection=sqlite3.connect(path.as_uri()+'?mode=ro',uri=True)
        try: rows=audit(connection)
        except sqlite3.DatabaseError as exc: rows=[('Database','error',str(exc))]
        finally: connection.close()
        self.query_one('#audit',Static).update('DATA QUALITY\n\n'+'\n'.join(f'{state.upper():7} {name}: {detail}' for name,state,detail in rows))
