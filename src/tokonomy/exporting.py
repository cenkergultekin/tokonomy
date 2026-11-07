"""Versioned metadata export for downstream analysis."""
import json
from datetime import datetime, timezone

QUERIES = {
 'session': 'SELECT source,session_id,started_at,last_seen_at,model,input_tokens,output_tokens,cached_input_tokens,cache_write_tokens FROM sessions',
 'usage_event': 'SELECT source,session_id,event_id,occurred_at,model,input_tokens,output_tokens,cached_input_tokens,cache_write_tokens FROM usage_events',
 'relationship': 'SELECT source,session_id,parent_id FROM session_context',
 'compaction': 'SELECT source,session_id,kind,timestamp FROM session_events',
 'quota_observation': 'SELECT provider,limit_id,plan_type,window_seconds,used_percent,captured_at,resets_at FROM limit_snapshots',
 'coverage': 'SELECT source,observed_at,status,detail FROM source_health',
}


def export(connection, path):
    # Exclusive creation prevents accidental replacement of a user's export.
    connection.execute('SAVEPOINT export_snapshot')
    try:
        with path.open('x',encoding='utf-8') as stream:
            stream.write(json.dumps({'type':'manifest','schema_version':1,'exported_at':datetime.now(timezone.utc).isoformat(),'scope':'recorded local usage; unknown values are null'})+'\n')
            for kind, query in QUERIES.items():
                cursor=connection.execute(query)
                names=[d[0] for d in cursor.description]
                for row in cursor:
                    stream.write(json.dumps({'type':kind,'data':dict(zip(names,row))},ensure_ascii=False)+'\n')
    finally:
        connection.execute('RELEASE export_snapshot')
