from datetime import datetime
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.widgets import Static, TabbedContent, TabPane, DataTable, Input, Select, Button
from textual.containers import Horizontal, VerticalScroll
from tokonomy import metrics
from tokonomy.charts import analytics, activity
from tokonomy.formatting import compact, money, pct
from tokonomy.store import Store
from tokonomy.orbit import TokenOrbit


def number(value):
    return '—' if value is None else f'{value:,}'


class TokonomyApp(App):
    ENABLE_COMMAND_PALETTE = False
    TITLE = 'tokonomy'
    SUB_TITLE = ''
    CSS = """
    Screen { background: #101c26; color: #f3e9da; }
    #brand { height: 5; padding: 1 3; color: #e5b38a; }
    #metrics { height: 4; margin: 0 3 1 3; }
    .card { width: 1fr; padding: 0 1; margin-right: 1; background: transparent; color: #a7bac2; }
    TabbedContent { margin: 0 2; }
    TabPane { padding: 1; }
    Tabs { background: transparent; }
    Tab { background: transparent; color: #a7bac2; }
    Tab:hover { background: #233944; color: #f1cba9; }
    Tab.-active { background: transparent; color: #e5b38a; text-style: bold; }
    Underline { background: transparent; color: #436574; }
    Underline > .underline--bar { background: transparent; color: #e5b38a; }
    ContentSwitcher { background: transparent; }
    DataTable { height: 1fr; background: transparent; scrollbar-color: #436574; scrollbar-background: #101c26; }
    DataTable > .datatable--header { background: #1b303b; color: #b7cbd1; text-style: bold; }
    DataTable > .datatable--cursor { background: #335463; color: #fff0dc; }
    DataTable > .datatable--hover { background: #263e4b; }
    Input { margin-bottom: 1; border: round #436574; background: transparent; }
    Input:focus { border: round #e5b38a; }
    Select { background: #1b303b; border: tall #436574; }
    Button { background: #1b303b; color: #e5b38a; }
    #limits { height: 7; }
    #graphs { height: auto; padding: 1 0; }
    #activity { height: auto; }
    #history-table { height: 20; }
    #status { height: 1; padding: 0 3; color: #a7bac2; }
    Footer { background: transparent; color: #a7bac2; }
    Footer > .footer--key { background: transparent; color: #e5b38a; }
    Footer > .footer--description { background: transparent; }
    Footer > .footer--highlight { background: #335463; color: #fff0dc; }
    """
    BINDINGS = [Binding('q', 'quit', 'Quit'), Binding('r', 'reload', 'Refresh'),
                Binding('left', 'previous', 'Tabs', priority=True),
                Binding('right', 'next', 'Tabs', priority=True, show=False),
                Binding('1', 'page(0)', 'Overview', show=False), Binding('2', 'page(1)', 'Sessions', show=False),
                Binding('3', 'page(2)', 'Models', show=False), Binding('4', 'page(3)', 'History', show=False)]
    pages = ['overview', 'sessions', 'models', 'history', 'projects', 'sources']

    def __init__(self, data_dir):
        super().__init__()
        self.data_dir = data_dir

    def compose(self) -> ComposeResult:
        yield TokenOrbit(id='brand')
        with Horizontal(id='metrics'):
            yield Static('', id='count', classes='card')
            yield Static('', id='uncached', classes='card')
            yield Static('', id='cache', classes='card')
            yield Static('', id='output', classes='card')
            yield Static('', id='cost', classes='card')
        with TabbedContent(initial='overview'):
            with TabPane('Overview', id='overview'):
                with VerticalScroll():
                    yield Static('', id='graphs')
                    yield DataTable(id='limits', cursor_type='row')
            with TabPane('Sessions', id='sessions'):
                yield Select([('All providers','all'),('Claude Code','claude-code'),('Codex','codex'),('Hermes','hermes'),('OpenCode','opencode'),('Cursor','cursor')], value='all', allow_blank=False, id='provider-filter')
                yield Select([('Recent activity','recent'),('Largest input','input'),('Largest output','output'),('Largest cache read','cache')],value='recent',allow_blank=False,id='sort-order')
                yield Input(placeholder='Filter by provider, model, project or session ID…', id='search')
                yield DataTable(id='session-table', cursor_type='row')
            with TabPane('Models', id='models'):
                yield DataTable(id='model-table', cursor_type='row')
            with TabPane('History', id='history'):
                with VerticalScroll():
                    yield Static('', id='activity')
                    yield DataTable(id='history-table', cursor_type='row')
            with TabPane('Projects', id='projects'):
                yield DataTable(id='projects-table', cursor_type='row')
            with TabPane('Sources', id='sources'):
                yield Button('Collector settings', id='collector-settings')
                yield DataTable(id='sources-table', cursor_type='row')
        yield Static('', id='status')


    def on_mount(self):
        for table, columns in [('limits', ['Provider', 'Window', 'Used', 'Reset (UTC)', 'Observed (UTC)', 'State']),
                               ('session-table', ['Provider', 'Session', 'Model', 'Uncached', 'Output', 'Last activity', 'Cache hit', 'Est. cost']),
                               ('model-table', ['Provider', 'Model', 'Sessions', 'Uncached', 'Output', 'Cache hit', 'Est. cost']),
                               ('history-table', ['Provider', 'Window', 'Used', 'Reset (UTC)', 'Observed (UTC)'])]:
            self.query_one('#'+table, DataTable).add_columns(*columns)
        self.query_one('#projects-table', DataTable).add_columns('Project', 'Sessions', 'Uncached', 'Output', 'Cache', 'Est. cost')
        self.query_one('#sources-table', DataTable).add_columns('Source', 'Sessions', 'Token events', 'Coverage')
        self.load_data()
        self.set_interval(120, self.action_reload)

    def action_page(self, index):
        self.query_one(TabbedContent).active = self.pages[index]

    def shift(self, delta):
        tabs = self.query_one(TabbedContent)
        tabs.active = self.pages[(self.pages.index(tabs.active)+delta) % len(self.pages)]

    def action_previous(self): self.shift(-1)
    def action_next(self): self.shift(1)

    def load_data(self):
        store = Store(self.data_dir / 'tokonomy.sqlite3')
        try:
            c = store.connection
            health=self.query_one('#sources-table', DataTable); health.clear()
            for source in ['codex','claude-code','hermes','opencode','cursor']:
                sessions=c.execute('SELECT COUNT(*) FROM sessions WHERE source=?',(source,)).fetchone()[0]
                events=c.execute('SELECT COUNT(*) FROM usage_events WHERE source=?',(source,)).fetchone()[0]
                state=c.execute('SELECT status,detail FROM source_health WHERE source=?',(source,)).fetchone()
                coverage=(' / '.join(state)) if state else 'Timestamped events' if events else 'No imported data'
                health.add_row(source,str(sessions),str(events),coverage)
            projects=self.query_one('#projects-table', DataTable); projects.clear()
            for p in metrics.projects(c, limit=15):
                projects.add_row(
                    p['project'], str(p['sessions']), compact(p['uncached']),
                    compact(p['output']), pct(p['cache_hit']), money(p['cost']),
                )
            self.query_one('#graphs', Static).update(analytics(c))
            self.query_one('#activity', Static).update(activity(c))
            summary = metrics.summary(c)
            for key, label, value in [
                ('count', 'Sessions', f"{summary['sessions']:,}"),
                ('uncached', 'Uncached input', compact(summary['uncached'])),
                ('cache', 'Cache hit', pct(summary['cache_hit'])),
                ('output', 'Output', compact(summary['output'])),
                ('cost', 'Est. spend', money(summary['cost'])),
            ]:
                self.query_one('#'+key, Static).update(f'[bold #f3e9da]{value}[/]\n{label}')
            self.session_projects={(r[0],r[1]):r[2] or 'Unknown' for r in c.execute('SELECT source,session_id,project FROM session_context')}
            self.session_groups={(r[0],r[1]):r[2] for r in c.execute('SELECT source,session_id,name FROM work_assignments')}
            self.session_rows = [tuple(r) for r in c.execute('SELECT source, session_id, model, input_tokens, output_tokens, last_seen_at, cached_input_tokens, cache_write_tokens FROM sessions ORDER BY last_seen_at DESC')]
            self.session_costs = {}
            from tokonomy import pricing
            table = pricing.load_pricing(self.data_dir)
            for r in c.execute('SELECT source, session_id, model, input_tokens, cached_input_tokens, cache_write_tokens, output_tokens FROM model_usage'):
                cost = pricing.estimate(r[0], r[2], r[3], r[4], r[5], r[6], table)
                if cost is not None:
                    key = (r[0], r[1])
                    self.session_costs[key] = self.session_costs.get(key, 0.0) + cost
            self.fill_sessions(self.query_one('#search', Input).value)
            table = self.query_one('#model-table', DataTable); table.clear()
            for m in metrics.model_breakdown(c)[:20]:
                table.add_row(
                    m['source'], m['model'], str(m['sessions']), compact(m['uncached']),
                    compact(m['output']), pct(m['cache_hit']), money(m['cost']),
                )
            rows = c.execute('SELECT provider, window_seconds, used_percent, resets_at, captured_at, limit_id, id FROM limit_snapshots ORDER BY captured_at DESC LIMIT 1000').fetchall()
            latest = self.query_one('#limits', DataTable); latest.clear()
            history = self.query_one('#history-table', DataTable); history.clear()
            seen = set()
            for r in rows:
                window = {18000:'5 hours',604800:'7 days'}.get(r[1], str(r[1])+'s')
                cells = (r[0], window, f'{r[2]:g}%', r[3] or 'Unknown', r[4])
                history.add_row(*cells, key=str(r[6]))
                key = (r[0],r[1],r[5])
                if key not in seen:
                    from datetime import timezone
                    expired = bool(r[3] and datetime.fromisoformat(r[3]) <= datetime.now(timezone.utc))
                    state = 'RESET PASSED / UNKNOWN' if expired else 'EXHAUSTED (observed)' if r[2]>=100 else 'Last observed'
                    latest.add_row(*cells, state, key=str(r[6])); seen.add(key)
            if not any(k[0]=='claude-code' for k in seen):
                latest.add_row('claude-code', 'Unknown', 'Unknown', 'Unknown', 'No quota source', 'UNKNOWN')
        finally:
            store.close()

    def fill_sessions(self, text):
        table = self.query_one('#session-table', DataTable); table.clear()
        selected = self.query_one('#provider-filter', Select).value
        order=self.query_one('#sort-order',Select).value
        index={'input':3,'output':4,'cache':6}.get(order)
        rows=sorted(self.session_rows,key=lambda r:r[index] if r[index] is not None else -1,reverse=True) if index is not None else self.session_rows
        for row in rows:
            if selected != 'all' and row[0] != selected: continue
            searchable=' '.join(str(v) for v in row)+' '+self.session_projects.get((row[0],row[1]),'')+' '+self.session_groups.get((row[0],row[1]),'')
            if text.lower() in searchable.lower():
                uncached = metrics.uncached_input(row[0], row[3], row[6])
                reported = (uncached or 0) + (row[6] or 0)
                cache_hit = pct(((row[6] or 0) / reported * 100) if reported else None)
                cost = money(self.session_costs.get((row[0], row[1])))
                table.add_row(row[0], row[1], row[2] or 'Unknown', number(uncached), number(row[4]), row[5] or 'Unknown', cache_hit, cost, key=row[0]+'|'+row[1])

    def on_select_changed(self, event: Select.Changed):
        if event.select.id in ('provider-filter','sort-order') and hasattr(self, 'session_rows'):
            self.fill_sessions(self.query_one('#search', Input).value)

    def on_input_changed(self, event: Input.Changed):
        if event.input.id == 'search':
            self.fill_sessions(event.value)

    async def action_reload(self):
        if len(self.screen_stack) > 1:
            return
        import asyncio
        from tokonomy.cli import collect
        self.query_one('#status', Static).update('Refreshing...')
        try:
            # Collector output is suppressed through its quiet option.
            await asyncio.to_thread(collect, self.data_dir, quiet=True)
            self.load_data()
            self.query_one('#status', Static).update('Updated '+datetime.now().strftime('%H:%M'))
        except Exception as exc:
            self.notify(str(exc), severity='error')

    def on_data_table_row_selected(self, event: DataTable.RowSelected):
        if event.data_table.id == 'sources-table':
            from tokonomy.diagnostics import Diagnostics
            self.push_screen(Diagnostics(self.data_dir))
            return
        if event.data_table.id in ('limits','history-table'):
            key=event.row_key.value
            if key is not None and str(key).isdigit():
                from tokonomy.periods import QuotaDetail
                self.push_screen(QuotaDetail(self.data_dir,int(key)))
            return
        if event.data_table.id == 'projects-table':
            project=event.data_table.get_row(event.row_key)[0]
            self.action_page(1)
            self.query_one('#search',Input).value=project
            return
        if event.data_table.id == 'session-table':
            from tokonomy.details import SessionDetail
            source, sid = event.row_key.value.split('|',1)
            self.push_screen(SessionDetail(self.data_dir, source, sid), lambda _: self.load_data())

    def on_button_pressed(self, event: Button.Pressed):
        if event.button.id=='collector-settings':
            from tokonomy.settings import CollectorSettings
            self.push_screen(CollectorSettings(self.data_dir))
