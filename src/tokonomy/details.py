from textual.screen import ModalScreen
from textual.widgets import Static, DataTable, Footer
from textual.containers import VerticalScroll
from tokonomy.store import Store

class SessionDetail(ModalScreen):
    BINDINGS=[('escape','dismiss','Back')]
    def __init__(self,data_dir,source,sid):
        super().__init__(); self.data_dir=data_dir; self.source=source; self.sid=sid
    def compose(self):
        with VerticalScroll():
            yield Static('',id='detail',markup=False)
            yield DataTable(id='events')
        yield Footer()
    def on_mount(self):
        store=Store(self.data_dir/'tokonomy.sqlite3'); c=store.connection
        try:
            context=c.execute('SELECT * FROM session_context WHERE source=? AND session_id=?',(self.source,self.sid)).fetchone()
            children=c.execute('SELECT session_id FROM session_context WHERE source=? AND parent_id=?',(self.source,self.sid)).fetchall()
            compact=c.execute('SELECT timestamp,line,source_file FROM session_events WHERE source=? AND session_id=?',(self.source,self.sid)).fetchall()
            self.query_one('#detail',Static).update(f'{self.source} / {self.sid}\nProject: {context["project"] if context else "Unknown"}\nRecorded child agents: {len(children)}\nRecorded compactions: {len(compact)}\nSource: {context["source_file"] if context else "Unknown"}\nChildren: '+', '.join(r[0] for r in children))
            table=self.query_one('#events',DataTable); table.add_columns('Time','Event / source ID','Input','Output','Cache read','Cache write')
            for r in c.execute('SELECT occurred_at,event_id,input_tokens,output_tokens,cached_input_tokens,cache_write_tokens FROM usage_events WHERE source=? AND session_id=? ORDER BY occurred_at',(self.source,self.sid)):
                table.add_row(*[str(v) if v is not None else 'Unknown' for v in r])
            for r in compact: table.add_row(str(r[0]),f'compaction · record {r[1]}','—','—','—','—')
        finally: store.close()
