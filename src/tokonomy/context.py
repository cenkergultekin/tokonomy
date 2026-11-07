"""Allowlisted provenance and project relationships; no transcript persistence."""
import subprocess
from functools import lru_cache
from pathlib import Path
from tokonomy.sources.jsonl import iter_jsonl

@lru_cache(maxsize=256)
def project_root(cwd):
    if not cwd or not Path(cwd).is_dir(): return cwd
    try:
        result = subprocess.run(['git','-C',cwd,'rev-parse','--path-format=absolute','--git-common-dir'],capture_output=True,text=True,timeout=3)
        if result.returncode == 0:
            return str(Path(result.stdout.strip()).parent)
    except (OSError, subprocess.TimeoutExpired): pass
    return cwd


def enrich(store, session, path):
    c=store.connection
    c.execute('CREATE TABLE IF NOT EXISTS session_context (source TEXT, session_id TEXT, project TEXT, cwd TEXT, parent_id TEXT, branch TEXT, source_file TEXT, PRIMARY KEY(source,session_id))')
    c.execute('CREATE TABLE IF NOT EXISTS session_events (source TEXT, session_id TEXT, line INTEGER, kind TEXT, timestamp TEXT, source_file TEXT, PRIMARY KEY(source,session_id,line,kind))')
    cwd=parent=branch=None
    events=[]
    for line,r in enumerate(iter_jsonl(path),1):
        payload=r.get('payload',{})
        if not isinstance(payload,dict): payload={}
        cwd=r.get('cwd') or (payload.get('cwd') if r.get('type')=='session_meta' else None) or cwd
        branch=r.get('gitBranch') or branch
        if r.get('type')=='session_meta':
            src=payload.get('source',{})
            if isinstance(src,dict):
                sub=src.get('subagent',{})
                if isinstance(sub,dict):
                    spawn=sub.get('thread_spawn',{})
                    if isinstance(spawn,dict): parent=spawn.get('parent_thread_id') or parent
        if '/subagents/' in path.as_posix(): parent=r.get('sessionId') or parent
        kind=r.get('type')
        if kind=='compacted' or (kind=='system' and r.get('subtype')=='compact_boundary') or (kind=='event_msg' and payload.get('type')=='context_compacted'):
            events.append((session.source,session.session_id,line,'compaction',r.get('timestamp'),str(path)))
    c.execute('INSERT OR REPLACE INTO session_context VALUES (?,?,?,?,?,?,?)',(session.source,session.session_id,project_root(cwd),cwd,parent,branch,str(path)))
    c.execute('DELETE FROM session_events WHERE source=? AND session_id=?',(session.source,session.session_id))
    c.executemany('INSERT OR IGNORE INTO session_events VALUES (?,?,?,?,?,?)',events)
