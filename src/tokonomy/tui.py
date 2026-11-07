from datetime import datetime
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.widgets import Header, Footer, Static, TabbedContent, TabPane, DataTable, Input, Select
from textual.containers import Horizontal, VerticalScroll
from tokonomy.charts import analytics, activity
from tokonomy.store import Store
from tokonomy.orbit import TokenOrbit


def number(value):
    return 'â€”' if value is None else f'{value:,}'


class TokonomyApp(App):
    ENABLE_COMMAND_PALETTE = False
    TITLE = 'tokonomy'
    SUB_TITLE = 'your local AI usage observatory'
    CSS = """
    Screen { background: ansi_default; color: #d0d0d0; }
    #brand { height: 15; padding: 1 3; color: #82c783; }
    #metrics { height: 4; margin: 0 3 1 3; }
    .card { width: 1fr; border-left: solid #426b43; padding: 0 1; margin-right: 1; background: transparent; color: #919191; }
    TabbedContent { margin: 0 2; }
    TabPane { padding: 1; }
    Tabs { background: transparent; }
    Tab { background: transparent; color: #888888; }
    Tab:hover { background: #202620; color: #a9d9aa; }
    Tab.-active { background: transparent; color: #82c783; text-style: bold; }
    Underline { background: transparent; color: #426b43; }
    Underline > .underline--bar { background: transparent; color: #82c783; }
    ContentSwitcher { background: transparent; }
    DataTable { height: 1fr; background: transparent; scrollbar-color: #426b43; scrollbar-background: #171717; }
    DataTable > .datatable--header { background: #191d19; color: #a9b9a9; text-style: bold; }
    DataTable > .datatable--cursor { background: #263a27; color: #d4f0d5; }
    DataTable > .datatable--hover { background: #1d271e; }
    Input { margin-bottom: 1; border: round #3b443b; background: transparent; }
    Input:focus { border: round #82c783; }
    #limits { height: 7; }
    #graphs { height: auto; padding: 1 0; }
    #activity { height: auto; }
    #history-table { height: 20; }
    #status { height: 1; padding: 0 3; color: #888888; }
    Footer { background: transparent; color: #999999; }
    Footer > .footer--key { background: transparent; color: #82c783; }
    Footer > .footer--description { background: transparent; }
    Footer > .footer--highlight { background: #263a27; color: #d4f0d5; }
    """
    BINDINGS = [Binding('space', 'orbit', 'Pause', show=False), Binding('q', 'quit', 'Quit'), Binding('r', 'reload', 'Refresh'),
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
            yield Static('', id='input', classes='card')
            yield Static('', id='cache-read', classes='card')
            yield Static('', id='cache-write', classes='card')
            yield Static('', id='output', classes='card')
        with TabbedContent(initial='overview'):
            with TabPane('1 Overview', id='overview'):
                with VerticalScroll():
                    yield Static('', id='graphs')
                    yield DataTable(id='limits', cursor_type='row')
            with TabPane('2 Sessions', id='sessions'):
                yield Select([('All providers','all'),('Claude Code','claude-code'),('Codex','codex'),('Hermes','hermes'),('OpenCode','opencode'),('Cursor','cursor')], value='all', allow_blank=False, id='provider-filter')
                yield Select([('Recent activity','recent'),('Largest input','input'),('Largest output','output'),('Largest cache read','cache')],value='recent',allow_blank=False,id='sort-order')
                yield Input(placeholder='Filter by provider, model or session IDâ€¦', id='search')
                yield DataTable(id='session-table', cursor_type='row')
            with TabPane('3 Models', id='models'):
                yield DataTable(id='model-table', cursor_type='row')
            with TabPane('4 History', id='history'):
                with VerticalScroll():
                    yield Static('', id='activity')
                    yield DataTable(id='history-table', cursor_type='row')
            with TabPane('5 Projects', id='projects'):
                yield DataTable(id='projects-table', cursor_type='row')
            with TabPane('6 Sources', id='sources'):
                yield DataTable(id='sources-table', cursor_type='row')
        yield Static('', id='status')
        yield Footer()

    def on_mount(self):
        for table, columns in [('limits', ['Provider', 'Window', 'Used', 'Reset (UTC)', 'Observed (UTC)', 'State']),
                               ('session-table', ['Provider', 'Session', 'Model', 'Input', 'Output', 'Last activity', 'Cache read', 'Cache write']),
                               ('model-table', ['Provider', 'Model', 'Sessions', 'Input', 'Output', 'Cache read']),
                               ('history-table', ['Provider', 'Window', 'Used', 'Reset (UTC)', 'Observed (UTC)'])]:
            self.query_one('#'+table, DataTable).add_columns(*columns)
        self.query_one('#projects-table', DataTable).add_columns('Project', 'Sessions', 'Avg input', 'Avg output', 'Agents/session', 'Compactions')
        self.query_one('#sources-table', DataTable).add_columns('Source', 'Sessions', 'Token events', 'Coverage')
        self.load_data()
        self.set_interval(120, self.action_reload)

    def action_page(self, index):
        self.query_one(TabbedContent).active = self.pages[index]

    def shift(self, delta):
        tabs = self.query_one(TabbedContent)
        tabs.active = self.pages[(self.pages.index(tabs.active)+delta) % len(self.pages)]

    def action_orbit(self):
        orbit = self.query_one(TokenOrbit)
        orbit.paused = not orbit.paused

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
            if c.execute("SELECT 1 FROM sqlite_master WHERE name='session_context'").fetchone():
                for r in c.execute("SELECT COALESCE(x.project,'Unknown'),COUNT(*),AVG(s.input_tokens),AVG(s.output_tokens),AVG((SELECT COUNT(*) FROM session_context child WHERE child.source=s.source AND child.parent_id=s.session_id)),SUM((SELECT COUNT(*) FROM session_events e WHERE e.source=s.source AND e.session_id=s.session_id)) FROM sessions s LEFT JOIN session_context x ON x.source=s.source AND x.session_id=s.session_id GROUP BY x.project"):
                    projects.add_row(*[str(round(v,1)) if isinstance(v,float) else str(v) for v in r])
            self.query_one('#graphs', Static).update(analytics(c))
            self.query_one('#activity', Static).update(activity(c))
            totals = c.execute('SELECT COUNT(*), SUM(input_tokens), SUM(cached_input_tokens), SUM(cache_write_tokens), SUM(output_tokens) FROM sessions').fetchone()
            for key, label, value in zip(['count','input','cache-read','cache-write','output'], ['SESSIONS','INPUT','CACHE READ','CACHE WRITE','OUTPUT'], totals):
                self.query_one('#'+key, Static).update(f'{label}\n[bold #82c783]{number(value)}[/]')
            self.session_projects={(r[0],r[1]):r[2] or 'Unknown' for r in c.execute('SELECT source,session_id,project FROM session_context')}
            self.session_groups={(r[0],r[1]):r[2] for r in c.execute('SELECT source,session_id,name FROM work_assignments')}
            self.session_rows = [tuple(r) for r in c.execute('SELECT source, session_id, model, input_tokens, output_tokens, last_seen_at, cached_input_tokens, cache_write_tokens FROM sessions ORDER BY last_seen_at DESC')]
            self.fill_sessions(self.query_one('#search', Input).value)
            table = self.query_one('#model-table', DataTable); table.clear()
            for r in c.execute('SELECT source, model, COUNT(*), SUM(input_tokens), SUM(output_tokens), SUM(cached_input_tokens) FROM model_usage GROUP BY source, model ORDER BY SUM(input_tokens) DESC'):
                table.add_row(r[0], r[1], *[number(v) for v in r[2:]])
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
                table.add_row(row[0], row[1], row[2] or 'Unknown', number(row[3]), number(row[4]), row[5] or 'Unknown', number(row[6]), number(row[7]), key=row[0]+'|'+row[1])

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
