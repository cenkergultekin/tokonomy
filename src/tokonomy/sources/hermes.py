"""Read only allowlisted Hermes session metadata, never message bodies."""
import sqlite3
from datetime import datetime, timezone
from tokonomy.models import Session


def timestamp(value):
    if isinstance(value,(float,int)):
        return datetime.fromtimestamp(value/1000 if value>1e11 else value,timezone.utc).isoformat()
    if isinstance(value,str):
        try:
            d=datetime.fromisoformat(value.replace('Z','+00:00'))
            return (d if d.tzinfo else d.replace(tzinfo=timezone.utc)).astimezone(timezone.utc).isoformat()
        except ValueError: return None
    return None


def collect(store,path):
    if not path.is_file(): return 0
    connection=sqlite3.connect(path.as_uri()+'?mode=ro',uri=True,timeout=10)
    connection.row_factory=sqlite3.Row
    try:
        columns={r[1] for r in connection.execute('PRAGMA table_info(sessions)')}
        required=['id','started_at','ended_at','model','input_tokens','output_tokens','cache_read_tokens','cache_write_tokens','parent_session_id','cwd','git_repo_root','git_branch']
        if not set(required)<=columns: raise ValueError('Unsupported Hermes session schema')
        rows=connection.execute('SELECT '+','.join(required)+' FROM sessions').fetchall()
        for r in rows:
            store.upsert_session(Session(source='hermes',session_id=r['id'],started_at=timestamp(r['started_at']),last_seen_at=timestamp(r['ended_at']),model=r['model'],input_tokens=r['input_tokens'],output_tokens=r['output_tokens'],cached_input_tokens=r['cache_read_tokens'],cache_write_tokens=r['cache_write_tokens'],source_file=str(path)))
            store.connection.execute('INSERT OR REPLACE INTO session_context VALUES (?,?,?,?,?,?,?)',('hermes',r['id'],r['git_repo_root'] or r['cwd'],r['cwd'],r['parent_session_id'],r['git_branch'],str(path)))
        return len(rows)
    finally: connection.close()
