"""Explicit, durable user grouping; grouping does not rewrite source records."""
def groups(store, action, name=None, source=None, session=None):
    c=store.connection
    c.execute('CREATE TABLE IF NOT EXISTS work_assignments(source TEXT, session_id TEXT, name TEXT NOT NULL, PRIMARY KEY(source,session_id))')
    if action=='assign':
        if not c.execute('SELECT 1 FROM sessions WHERE source=? AND session_id=?',(source,session)).fetchone():
            raise ValueError('Unknown session')
        c.execute('INSERT OR REPLACE INTO work_assignments VALUES (?,?,?)',(source,session,name))
    elif action=='remove':
        c.execute('DELETE FROM work_assignments WHERE source=? AND session_id=?',(source,session))
    for row in c.execute('SELECT a.name,COUNT(*),SUM(s.input_tokens),SUM(s.output_tokens) FROM work_assignments a JOIN sessions s USING(source,session_id) GROUP BY a.name ORDER BY a.name'):
        print(' | '.join(str(v) for v in row))


def period_report(store, provider, hours):
    from datetime import datetime, timedelta, timezone
    end=datetime.now(timezone.utc); start=end-timedelta(hours=hours)
    c=store.connection
    rows=c.execute('SELECT session_id,SUM(input_tokens),SUM(output_tokens),SUM(cached_input_tokens),SUM(cache_write_tokens),COUNT(*) FROM usage_events WHERE source=? AND occurred_at>=? AND occurred_at<? GROUP BY session_id ORDER BY SUM(input_tokens) DESC',(provider,start.isoformat(),end.isoformat())).fetchall()
    print(f'{provider} | {start.isoformat()} -> {end.isoformat()} | local recorded activity')
    opened=c.execute('SELECT COUNT(*) FROM sessions WHERE source=? AND started_at>=? AND started_at<?',(provider,start.isoformat(),end.isoformat())).fetchone()[0]
    print(f'Sessions opened: {opened} | Sessions with token events: {len(rows)}')
    for i,label in enumerate(['Input','Output','Cache read','Cache write'],1):
        known=[r[i] for r in rows if r[i] is not None]
        print(f'{label}: {sum(known) if known else "unknown"}')
    print('Largest input contributors (recorded events):')
    total=sum(r[1] or 0 for r in rows)
    for r in rows[:5]:
        print(f'{r[0]} | input={r[1]} output={r[2]} | input share={(r[1] or 0)/total:.1%}' if total else str(tuple(r)))
