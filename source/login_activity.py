"""Recent application sessions in a separate activity database, without password data."""
import contextlib
import datetime as dt
from pathlib import Path
import sqlite3
import time
import uuid

TOKENS={}
PENDING={}
_MEMORY={}
TTL=90

def utc():return dt.datetime.now(dt.timezone.utc).isoformat()

@contextlib.contextmanager
def connection(db):
    path=next((r[2] for r in db.execute('PRAGMA database_list') if r[1]=='main'),'')
    temporary=not path
    if temporary:
        if db not in _MEMORY:_MEMORY[db]=sqlite3.connect(':memory:')
        activity=_MEMORY[db]
    else:activity=sqlite3.connect(Path(path).with_name(Path(path).name+'.login-activity.sqlite'),timeout=.1)
    try:
        activity.executescript('''CREATE TABLE IF NOT EXISTS usage(user_id INTEGER PRIMARY KEY,last_signin TEXT,last_usage TEXT);
          CREATE TABLE IF NOT EXISTS sessions(token TEXT PRIMARY KEY,user_id INTEGER,version INTEGER,login_at TEXT,last_seen REAL,ended_at TEXT);
          CREATE INDEX IF NOT EXISTS sessions_user ON sessions(user_id,last_seen);''')
        yield activity
    finally:
        if not temporary:activity.close()

def begin(db,user_id,version,login_at=None):
    token=uuid.uuid4().hex;now=login_at or utc();PENDING[db]=(user_id,version,now)
    try:
        with connection(db) as activity,activity:
            previous=TOKENS.get(db)
            if previous:activity.execute('UPDATE sessions SET ended_at=? WHERE token=?',(now,previous))
            activity.execute('INSERT INTO sessions VALUES(?,?,?,?,?,NULL)',(token,user_id,version,now,time.time()))
            activity.execute('INSERT INTO usage VALUES(?,?,?) ON CONFLICT(user_id) DO UPDATE SET last_signin=excluded.last_signin,last_usage=excluded.last_usage',(user_id,now,now))
        TOKENS[db]=token;PENDING.pop(db,None);return True
    except (sqlite3.Error,OSError):
        TOKENS.pop(db,None);return False

def end(db):
    PENDING.pop(db,None)
    token=TOKENS.pop(db,None)
    if not token:return
    try:
        with connection(db) as activity,activity:activity.execute('UPDATE sessions SET ended_at=? WHERE token=?',(utc(),token))
    except (sqlite3.Error,OSError):pass

def touch(db,interaction=False):
    token=TOKENS.get(db)
    if not token:return False
    try:
        with connection(db) as activity,activity:
            row=activity.execute('SELECT user_id FROM sessions WHERE token=? AND ended_at IS NULL',(token,)).fetchone()
            if row is None:return False
            activity.execute('UPDATE sessions SET last_seen=? WHERE token=?',(time.time(),token))
            if interaction:activity.execute('UPDATE usage SET last_usage=? WHERE user_id=?',(utc(),row[0]))
        return True
    except (sqlite3.Error,OSError):return False

def snapshot(db):
    try:
        with connection(db) as activity:
            usage={r[0]:{'last_signin':r[1],'last_usage':r[2]} for r in activity.execute('SELECT user_id,last_signin,last_usage FROM usage')}
            sessions=activity.execute('SELECT user_id,version,login_at FROM sessions WHERE ended_at IS NULL AND last_seen>=?',(time.time()-TTL,)).fetchall()
        return usage,sessions,True
    except (sqlite3.Error,OSError):return {},[],False

def install(app):
    import login
    root=app.root;db=app.store.db;last=[0.0]
    def event(ignored=None):
        now=time.monotonic()
        if now-last[0]<15:return
        last[0]=now
        try:
            if login.current(db):touch(db,True)
        except sqlite3.Error:pass
    def pulse():
        nonlocal heartbeat_timer
        try:
            if not root.winfo_exists():return
            row=login.current(db)
            if row and not touch(db):
                pending=PENDING.get(db)
                begin(db,row['id'],row['version'],pending[2] if pending and pending[:2]==(row['id'],row['version']) else None)
        except sqlite3.Error:pass
        except Exception:return
        heartbeat_timer = root.after(30000, pulse)

    def cancel_heartbeat(destroyed):
        if destroyed.widget is root:
            root.after_cancel(heartbeat_timer)

    root.bind_all('<KeyPress>', event, add='+')
    root.bind_all('<ButtonPress>', event, add='+')
    heartbeat_timer = root.after(30000, pulse)
    root.bind('<Destroy>', cancel_heartbeat, add='+')
