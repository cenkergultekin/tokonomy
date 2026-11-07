"""Reconcile Claude transcript copies before writing any session totals."""
from dataclasses import replace
from collections import defaultdict
from tokonomy.models import ModelUsage


def reconcile(sessions):
    buckets=defaultdict(list)
    for s in sessions: buckets[s.session_id].append(s)
    # Prefer a child's own transcript over a copied message in a parent log.
    owners={}
    for s in sorted(sessions,key=lambda s: (':' not in s.session_id,s.session_id)):
        for e in s.usage_events: owners.setdefault(e.event_id,s.session_id)
    for sid, copies in buckets.items():
        base=max(copies,key=lambda s:s.last_seen_at or '')
        events={}
        for s in copies:
            for e in s.usage_events:
                if owners[e.event_id]!=sid: continue
                old=events.get(e.event_id)
                if old is None or (e.output_tokens or 0)>(old.output_tokens or 0): events[e.event_id]=e
        if not any(s.usage_events for s in copies):
            yield base; continue
        fields=['input_tokens','output_tokens','cached_input_tokens','cache_write_tokens']
        def summed(items,field):
            values=[getattr(e,field) for e in items if getattr(e,field) is not None]
            return sum(values) if values else None
        models=defaultdict(list)
        for e in events.values(): models[e.model or 'unknown'].append(e)
        usages=tuple(ModelUsage(model=name,**{f:summed(items,f) for f in fields}) for name,items in models.items())
        yield replace(base,started_at=min((s.started_at for s in copies if s.started_at),default=None),usage_events=tuple(events.values()),model_usage=usages,**{f:summed(events.values(),f) for f in fields})
