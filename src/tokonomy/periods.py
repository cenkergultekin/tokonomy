"""Source-defined quota window detail; no inferred reset identities."""
from datetime import datetime, timedelta
from statistics import median
from textual.screen import ModalScreen
from textual.widgets import Static, DataTable, Footer
from tokonomy.store import Store


def window_report(connection, snapshot):
    reset=snapshot['resets_at']
    if not reset: return None
    start=datetime.fromisoformat(reset)-timedelta(seconds=snapshot['window_seconds'])
    end=min(datetime.fromisoformat(snapshot['captured_at']),datetime.fromisoformat(reset))
    if end<start: return None
    params=(snapshot['provider'],start.isoformat(),end.isoformat())
    rows=connection.execute('SELECT session_id,SUM(input_tokens),SUM(output_tokens),SUM(cached_input_tokens),SUM(cache_write_tokens),COUNT(*) FROM usage_events WHERE source=? AND julianday(occurred_at)>=julianday(?) AND julianday(occurred_at)<=julianday(?) GROUP BY session_id ORDER BY SUM(input_tokens) DESC',params).fetchall()
    opened=connection.execute('SELECT COUNT(*) FROM sessions WHERE source=? AND julianday(started_at)>=julianday(?) AND julianday(started_at)<=julianday(?)',params).fetchone()[0]
    totals=[]; means=[]; medians=[]
    for index in range(1,5):
        values=[r[index] for r in rows if r[index] is not None]
        totals.append(sum(values) if values else None)
        means.append(sum(values)/len(values) if values else None)
        medians.append(median(values) if values else None)
    return dict(start=start.isoformat(),end=end.isoformat(),opened=opened,rows=rows,totals=totals,means=means,medians=medians)


class QuotaDetail(ModalScreen):
    BINDINGS=[('escape','dismiss','Back')]
    CSS='#period-summary {height:auto; padding:1 2;} #contributors {height:1fr;}'
    def __init__(self,directory,snapshot_id):
        super().__init__(); self.directory=directory; self.snapshot_id=snapshot_id
    def compose(self):
        yield Static('',id='period-summary',markup=False)
        yield DataTable(id='contributors',cursor_type='row')
        yield Footer()
    def on_mount(self):
        store=Store(self.directory/'tokonomy.sqlite3')
        try:
            row=store.connection.execute('SELECT * FROM limit_snapshots WHERE id=?',(self.snapshot_id,)).fetchone()
            if row is None: return
            self.provider=row['provider']
            report=window_report(store.connection,row)
            if not report:
                self.query_one('#period-summary',Static).update('No usable source window boundaries.'); return
            fmt=lambda v:'Unknown' if v is None else f'{v:,.0f}'
            lines=[f'{self.provider} | {row["used_percent"]:g}% observed | {row["captured_at"]}',f'{report["start"]} -> {report["end"]}',f'Sessions opened: {report["opened"]} | Sessions with token events: {len(report["rows"])}','Local observations only; account coverage is not guaranteed.']
            for i,label in enumerate(['Input','Output','Cache read','Cache write']):
                lines.append(f'{label}: {fmt(report["totals"][i])} | per-session mean {fmt(report["means"][i])} | median {fmt(report["medians"][i])}')
            self.query_one('#period-summary',Static).update('\n'.join(lines))
            table=self.query_one('#contributors',DataTable)
            table.add_columns('Session','Input','Output','Cache read','Cache write','Requests')
            for r in report['rows']: table.add_row(r[0],*[fmt(v) for v in r[1:]],key=r[0])
        finally: store.close()
    def on_data_table_row_selected(self,event):
        event.stop()
        from tokonomy.details import SessionDetail
        self.app.push_screen(SessionDetail(self.directory,self.provider,event.row_key.value))
