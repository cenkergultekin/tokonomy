"""Explicit per-user Windows login startup registration."""
import subprocess
import sys
from pathlib import Path

KEY = r'Software\Microsoft\Windows\CurrentVersion\Run'
NAME = 'tokonomy'


def enabled():
    import winreg
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER,KEY) as key:
            winreg.QueryValueEx(key,NAME)
        return True
    except FileNotFoundError: return False


def configure(enable):
    import winreg
    with winreg.CreateKey(winreg.HKEY_CURRENT_USER,KEY) as key:
        if enable:
            command=subprocess.list2cmdline([str(Path(sys.executable).with_name('pythonw.exe')),'-m','tokonomy','collector','run'])
            winreg.SetValueEx(key,NAME,0,winreg.REG_SZ,command)
        else:
            try: winreg.DeleteValue(key,NAME)
            except FileNotFoundError: pass
