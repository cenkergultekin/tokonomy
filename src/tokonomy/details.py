from textual.screen import ModalScreen
from textual.widgets import Static, DataTable, Footer, Input, Button
from textual.containers import VerticalScroll
from tokonomy.store import Store

class SessionDetail(ModalScreen):
    CSS = '#detail { height: auto; padding: 1 2; } #events { height: 1fr; min-height: 10; }'
    BINDINGS=[('escape','dismiss','Back')]
    def __init__(self,data_dir,source,sid):
        super().__init__(); self.data_dir=data_dir; self.source=source; self.sid=sid
    def compose(self):
        with VerticalScroll():
            yield Static('',id='detail',markup=False)
            yield Input(placeholder='Work group name', id='work-name')
            yield Button('Save group', id='save-group')
            yield Button('Remove from group', id='remove-group')
            yield Static('', id='group-status', markup=False)
            yield DataTable(id='events')
        yield Footer()
    def on_mount(self):
        store=Store(self.data_dir/'tokonomy.sqlite3'); c=store.connection
        try:
            group=c.execute('SELECT name FROM work_assignments WHERE source=? AND session_id=?',(self.source,self.sid)).fetchone()
            self.query_one('#work-name', Input).value=group[0] if group else ''
            context=c.execute('SELECT * FROM session_context WHERE source=? AND session_id=?',(self.source,self.sid)).fetchone()
            children=c.execute('SELECT session_id FROM session_context WHERE source=? AND parent_id=?',(self.source,self.sid)).fetchall()
            compact=c.execute('SELECT timestamp,line,source_file FROM session_events WHERE source=? AND session_id=?',(self.source,self.sid)).fetchall()
            self.query_one('#detail',Static).update(f'{self.source} / {self.sid}\nProject: {context["project"] if context else "Unknown"}\nRecorded child agents: {len(children)}\nRecorded compactions: {len(compact)}\nSource: {context["source_file"] if context else "Unknown"}\nChildren: '+', '.join(r[0] for r in children))
            sources=c.execute('SELECT source_file FROM session_sources WHERE source=? AND session_id=?',(self.source,self.sid)).fetchall()
            if sources:
                header=self.query_one('#detail',Static)
                header.update(f'{self.source} / {self.sid}\nProject: {context["project"] if context else "Unknown"}\nRecorded child agents: {len(children)} | Compactions: {len(compact)}\nSources:\n'+'\n'.join(r[0] for r in sources))
            table=self.query_one('#events',DataTable); table.add_columns('Time','Event / source ID','Input','Output','Cache read','Cache write','Source record')
            for r in c.execute('SELECT occurred_at,event_id,input_tokens,output_tokens,cached_input_tokens,cache_write_tokens FROM usage_events WHERE source=? AND session_id=? ORDER BY occurred_at',(self.source,self.sid)):
                origin=c.execute('SELECT source_file,record_number FROM usage_origins WHERE source=? AND event_id=? ORDER BY source_file,record_number LIMIT 1',(self.source,r[1])).fetchone()
                table.add_row(*[str(v) if v is not None else 'Unknown' for v in r], f'{origin[0]} / record {origin[1]}' if origin else 'Event ID in session source')
            for r in compact: table.add_row(str(r[0]),f'compaction · record {r[1]}','—','—','—','—', str(r[2]))
        finally: store.close()

    def on_button_pressed(self, event: Button.Pressed):
        name=self.query_one('#work-name',Input).value.strip()
        if event.button.id=='save-group' and not name:
            self.query_one('#group-status',Static).update('Enter a group name.'); return
        store=Store(self.data_dir/'tokonomy.sqlite3')
        try:
            if event.button.id=='save-group':
                store.connection.execute('INSERT OR REPLACE INTO work_assignments VALUES (?,?,?)',(self.source,self.sid,name))
            elif event.button.id=='remove-group':
                store.connection.execute('DELETE FROM work_assignments WHERE source=? AND session_id=?',(self.source,self.sid))
                self.query_one('#work-name',Input).value=''
        finally: store.close()
        self.query_one('#group-status',Static).update('Group saved.' if event.button.id=='save-group' else 'Group removed.')
