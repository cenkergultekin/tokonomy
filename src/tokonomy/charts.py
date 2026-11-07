from datetime import datetime, timedelta, timezone
from rich.text import Text


def activity(connection):
    result = Text('Token activity / 14 days / UTC\n', style='bold #e5b38a')
    days = [(datetime.now(timezone.utc)-timedelta(days=i)).strftime('%Y-%m-%d') for i in reversed(range(14))]
    rows = {r[0]: r[1:] for r in connection.execute("SELECT substr(occurred_at,1,10), SUM(input_tokens), SUM(output_tokens), SUM(cached_input_tokens), SUM(cache_write_tokens) FROM usage_events GROUP BY 1")}
    for index, label in enumerate(['Input','Output','Cache read','Cache write']):
        values = [(rows[d][index] or 0) if d in rows else 0 for d in days]
        peak=max(values) or 1
        bars=''.join('▁▂▃▄▅▆▇█'[min(7,int(v/peak*7))] if d in rows else '·' for d,v in zip(days,values))
        result.append(f'{label:12} {bars}  peak {max(values):,}\n', '#b7cbd1')
    result.append(f'{days[0]} → {days[-1]}  · = no observations\n\n', '#a7bac2')
    return result


def analytics(connection):
    groups = [(r[0], r[1]) for r in connection.execute(
        "SELECT model, SUM(COALESCE(output_tokens,0)) AS total FROM model_usage "
        "GROUP BY model HAVING total>0 ORDER BY total DESC, model")]
    total = sum(value for _, value in groups)
    result = Text('Models', style='bold #e5b38a')
    result.append('  /  output tokens\n', '#a7bac2')
    if not total:
        result.append('No recorded usage.', '#a7bac2')
        return result
    if len(groups) > 5:
        groups = groups[:5] + [('Other', sum(v for _, v in groups[5:]))]
    for name, value in groups:
        result.append(f'  {name:<34} {value / total:6.1%}\n', '#b7cbd1')
    return result
