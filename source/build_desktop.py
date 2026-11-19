"""Rebuild the x64 desktop payload from this source folder."""
import subprocess
import sys
from pathlib import Path

root=Path(__file__).resolve().parent
args=[sys.executable,'-m','PyInstaller','--noconfirm','--onedir','--windowed',
    '--name','PikeCountyWC','--distpath',str(root/'build/frozen'),
    '--workpath',str(root/'build/work'),'--specpath',str(root/'build/spec'),
    '--paths',str(root)]
for path in root.iterdir():
    if path.suffix in ('.json','.txt','.tzif'):
        args.extend(['--add-data',str(path)+';.'])
args.extend(['--add-data',str(root/'licenses')+';licenses',str(root/'desktop_entry.py')])
raise SystemExit(subprocess.run(args).returncode)
