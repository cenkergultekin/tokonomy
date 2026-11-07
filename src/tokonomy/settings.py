import json
from textual.screen import ModalScreen
from textual.widgets import Static, Button, Footer
from tokonomy.collector import running, control
from tokonomy.startup import enabled, configure

class CollectorSettings(ModalScreen):
    BINDINGS=[('escape','dismiss','Back')]
    CSS='#collector-info {height:auto; padding:1 2;} Button {margin:0 2;}'
    def __init__(self,directory): super().__init__(); self.directory=directory
    def compose(self):
        yield Static('',id='collector-info',markup=False)
        yield Button('Start collector',id='collector-start')
        yield Button('Stop collector',id='collector-stop')
        yield Button('Toggle start at Windows login',id='collector-login')
        yield Footer()
    def on_mount(self):
        self.show_status(); self.set_interval(2,self.show_status)
    def show_status(self):
        path=self.directory/'collector-status.json'
        try: status=json.loads(path.read_text(encoding='utf-8')) if path.exists() else {}
        except (OSError,ValueError): status={}
        lines=['COLLECTOR', 'Running' if running(self.directory) else 'Stopped',f'Windows login startup: {"On" if enabled() else "Off"}',f'Last cycle: {status.get("observed_at","Not yet recorded")}',f'Scan: {status.get("scan","Unknown")}',f'Quota: {status.get("quota",status.get("error","Unknown"))}']
        self.query_one('#collector-info',Static).update('\n'.join(lines))
    def on_button_pressed(self,event):
        event.stop()
        try:
            if event.button.id=='collector-login': configure(not enabled())
            elif event.button.id=='collector-start': control(self.directory,'start',quiet=True)
            elif event.button.id=='collector-stop': control(self.directory,'stop',quiet=True)
            self.show_status()
        except OSError as exc: self.notify(str(exc),severity='error')
