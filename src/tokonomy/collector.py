"""Independent collector with an OS-held single-instance lock and stop signal."""
import json
import os
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path


def running(directory):
    directory.mkdir(parents=True, exist_ok=True)
    with (directory/'collector.lock').open('a+b') as lock:
        lock.seek(0)
        try:
            import msvcrt
            msvcrt.locking(lock.fileno(), msvcrt.LK_NBLCK, 1)
            msvcrt.locking(lock.fileno(), msvcrt.LK_UNLCK, 1)
            return False
        except OSError:
            return True


def control(directory, action):
    if action == 'status':
        print('Running' if running(directory) else 'Stopped')
        path=directory/'collector-status.json'
        if path.exists(): print(path.read_text(encoding='utf-8'))
    elif action == 'stop':
        (directory/'collector.stop').touch()
        print('Stop requested; collector exits after its current cycle.')
    elif action == 'start':
        if running(directory): print('Already running'); return
        (directory/'collector.stop').unlink(missing_ok=True)
        pythonw=Path(sys.executable).with_name('pythonw.exe')
        subprocess.Popen([str(pythonw), '-m','tokonomy','collector','run'],
                         stdin=subprocess.DEVNULL,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,
                         creationflags=subprocess.CREATE_NO_WINDOW,close_fds=True)
        print('Collector starting. Use tokonomy collector status.')
    elif action == 'run':
        run(directory)


def run(directory):
    import msvcrt
    from tokonomy.cli import collect
    from tokonomy.providers.codex_limits import read_rate_limits
    from tokonomy.store import Store
    directory.mkdir(parents=True,exist_ok=True)
    with (directory/'collector.lock').open('a+b') as lock:
        lock.seek(0)
        try: msvcrt.locking(lock.fileno(),msvcrt.LK_NBLCK,1)
        except OSError: return
        while not (directory/'collector.stop').exists():
            status={'pid':os.getpid(),'observed_at':datetime.now(timezone.utc).isoformat()}
            try:
                collect(directory,quiet=True)
                status['scan']='ok'
                snapshots=read_rate_limits()
                store=Store(directory/'tokonomy.sqlite3')
                try:
                    for snapshot in snapshots: store.save_limit_snapshot(snapshot)
                finally: store.close()
                status['quota']='ok'
            except Exception as exc:
                status['error']=type(exc).__name__
            target=directory/'collector-status.json'
            temp=target.with_suffix('.tmp')
            temp.write_text(json.dumps(status),encoding='utf-8'); temp.replace(target)
            for _ in range(120):
                if (directory/'collector.stop').exists(): return
                time.sleep(1)
