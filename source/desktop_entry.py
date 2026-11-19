"""Windowed executable entry point with a startup error dialog."""
import ctypes
import os
from pathlib import Path
import sys
import traceback

if __name__=='__main__':
    try:
        from app import main
        raise SystemExit(main())
    except Exception as error:
        folder=Path(os.environ.get('LOCALAPPDATA',str(Path.home())))/'PikeCountyWC'/'logs'
        folder.mkdir(parents=True,exist_ok=True)
        path=folder/'startup-error.txt'
        path.write_text(traceback.format_exc(),encoding='utf-8')
        ctypes.windll.user32.MessageBoxW(None,'The application could not start.\n\n'+str(error)+'\n\nError details: '+str(path),'Worthless Check',0x10)
        raise SystemExit(1)
