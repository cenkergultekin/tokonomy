"""Allowlisted OpenCode v2 and Cursor header importers."""
import sqlite3
from tokonomy.models import Session
from tokonomy.sources.hermes import timestamp


def opencode(store,path):
    if not path.is_file(): return 0
    c=sqlite3.connect(path.as_uri()+'?mode=ro',uri=True,timeout=10); c.row_factory=sqlite3.Row
    try:
        columns={r[1] for r in c.execute('pragma table_info(session_v2)')}
        fields=['id','parent_id','directory','time_created','time_updated','tokens_input','tokens_output','tokens_cache_read','tokens_cache_write']
        if not set(fields)<=columns: raise ValueError('Unsupported OpenCode schema')
        rows=c.execute('SELECT '+','.join(fields)+' FROM session_v2').fetchall()
        for r in rows:
            store.upsert_session(Session(source='opencode',session_id=r['id'],started_at=timestamp(r['time_created']),last_seen_at=timestamp(r['time_updated']),input_tokens=r['tokens_input'],output_tokens=r['tokens_output'],cached_input_tokens=r['tokens_cache_read'],cache_write_tokens=r['tokens_cache_write'],source_file=str(path)))
            store.connection.execute('INSERT OR REPLACE INTO session_context VALUES (?,?,?,?,?,?,?)',('opencode',r['id'],r['directory'],r['directory'],r['parent_id'],None,str(path)))
        return len(rows)
    finally: c.close()


def cursor(store,path):
    if not path.is_file(): return 0
    c=sqlite3.connect(path.as_uri()+'?mode=ro',uri=True,timeout=10)
    try:
        rows=c.execute('SELECT composerId,createdAt,lastUpdatedAt FROM composerHeaders').fetchall()
        for sid,start,end in rows:
            store.upsert_session(Session(source='cursor',session_id=sid,started_at=timestamp(start),last_seen_at=timestamp(end),source_file=str(path)))
        return len(rows)
    finally: c.close()
