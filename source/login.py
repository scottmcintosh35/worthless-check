import login_activity
"""Local prototype sign-in. Password storage uses salted PBKDF2-HMAC-SHA256."""
import hashlib
import hmac
import secrets
import time
import sqlite3
import datetime as dt

SESSIONS={}
ITERATIONS=600000


def audit(db,username,action,user_id):
    db.execute('INSERT INTO audit(at,operator,action,reference) VALUES(?,?,?,?)',
        (dt.datetime.now(dt.timezone.utc).isoformat(),username,action,str(user_id)))


def setup(db):
    db.executescript('''CREATE TABLE IF NOT EXISTS credentials (
      user_id INTEGER PRIMARY KEY REFERENCES staff_users(id),salt BLOB NOT NULL,digest BLOB NOT NULL,
      iterations INTEGER NOT NULL,role TEXT NOT NULL CHECK(role IN ('Administrator','Staff')),
      version INTEGER NOT NULL DEFAULT 1,failures INTEGER NOT NULL DEFAULT 0,locked_until REAL NOT NULL DEFAULT 0);
      CREATE TABLE IF NOT EXISTS diary_entries (
      id INTEGER PRIMARY KEY AUTOINCREMENT,date TEXT NOT NULL,subject TEXT NOT NULL,note TEXT NOT NULL,
      owner TEXT NOT NULL,completed INTEGER NOT NULL DEFAULT 0);''')


def enabled(db):
    return bool(db.execute('SELECT 1 FROM credentials LIMIT 1').fetchone())


def current(db):
    session=SESSIONS.get(db)
    if not session:
        return None
    row=db.execute('''SELECT u.*,c.role,c.version FROM staff_users u JOIN credentials c ON c.user_id=u.id WHERE u.id=? AND u.active=1''',(session[0],)).fetchone()
    return row if row and row['version']==session[1] else None


def require(db,admin=False):
    if not enabled(db):
        return 'DEMO'
    row=current(db)
    if not row:
        raise ValueError('Sign in to the system before making changes.')
    if admin and row['role']!='Administrator':
        raise ValueError('An Administrator login is required for this action.')
    return row['username']


def initials(db):
    row=current(db)
    return row['initials'] if row else 'DEMO'


def is_last_admin(db,user_id):
    row=db.execute('SELECT role FROM credentials WHERE user_id=?',(user_id,)).fetchone()
    return row and row['role']=='Administrator' and db.execute("SELECT COUNT(*) FROM credentials c JOIN staff_users u ON u.id=c.user_id WHERE c.role='Administrator' AND u.active=1").fetchone()[0]<=1


def password_data(password):
    if not isinstance(password,str) or not 12<=len(password)<=256:
        raise ValueError('Use a password or passphrase of 12 to 256 characters.')
    salt=secrets.token_bytes(16)
    return salt,hashlib.pbkdf2_hmac('sha256',password.encode('utf-8'),salt,ITERATIONS)


def set_password(db,user_id,password,role='Staff',bootstrap=False):
    salt,digest=password_data(password)
    if role not in ('Administrator','Staff'):
        raise ValueError('Choose Administrator or Staff.')
    try:
        db.execute('BEGIN IMMEDIATE')
        if bootstrap:
            if enabled(db):
                raise ValueError('The first Administrator login has already been created.')
            role='Administrator'
        else:
            require(db,admin=True)
        user=db.execute('SELECT * FROM staff_users WHERE id=? AND active=1',(user_id,)).fetchone()
        if not user:
            raise ValueError('Choose an active staff user.')
        if role!='Administrator' and is_last_admin(db,user_id):
            raise ValueError('Keep at least one active Administrator login.')
        actor=user['username'] if bootstrap else current(db)['username']
        db.execute('''INSERT INTO credentials(user_id,salt,digest,iterations,role) VALUES(?,?,?,?,?)
          ON CONFLICT(user_id) DO UPDATE SET salt=excluded.salt,digest=excluded.digest,
          iterations=excluded.iterations,role=excluded.role,version=version+1,failures=0,locked_until=0''',
          (user_id,salt,digest,ITERATIONS,role))
        audit(db,actor,'CREATE_FIRST_LOGIN' if bootstrap else 'SET_STAFF_LOGIN',user_id)
        db.commit()
    except Exception:
        db.rollback()
        raise


def authenticate(db,username,password):
    row=db.execute('''SELECT u.*,c.salt,c.digest,c.iterations,c.version,c.locked_until,c.failures FROM staff_users u
      JOIN credentials c ON c.user_id=u.id WHERE u.username=? COLLATE NOCASE''',(username.strip(),)).fetchone()
    if row is None or not row['active'] or row['locked_until']>time.time():
        hashlib.pbkdf2_hmac('sha256',b'dummy',b'local-login-dummy',ITERATIONS)
        raise ValueError('Login unsuccessful. Check credentials or try again later.')
    candidate=hashlib.pbkdf2_hmac('sha256',password.encode('utf-8'),row['salt'],row['iterations'])
    if not hmac.compare_digest(candidate,row['digest']):
        failures=row['failures']+1
        with db:
            db.execute('UPDATE credentials SET failures=failures+1,locked_until=CASE WHEN failures+1>=5 THEN ? ELSE 0 END WHERE user_id=? AND version=?',(time.time()+300,row['id'],row['version']))
        raise ValueError('Login unsuccessful. Check credentials or try again later.')
    with db:
        changed=db.execute('''UPDATE credentials SET failures=0,locked_until=0 WHERE user_id=? AND version=? AND locked_until<=?
          AND EXISTS(SELECT 1 FROM staff_users WHERE id=? AND active=1)''',(row['id'],row['version'],time.time(),row['id'])).rowcount
        if changed!=1:
            raise ValueError('Login unsuccessful. Credentials changed or account unavailable; try again.')
        audit(db,row['username'],'LOGIN_SUCCESS',row['id'])
    SESSIONS[db]=(row['id'],row['version'])
    login_activity.begin(db,row['id'],row['version'])
    return current(db)


def change_own_password(db,old_password,new_password):
    require(db)
    row=current(db)
    if row is None:
        raise ValueError('Create and sign in to a login first.')
    authenticate(db,row['username'],old_password)
    salt,digest=password_data(new_password)
    with db:
        db.execute('UPDATE credentials SET salt=?,digest=?,iterations=?,version=version+1 WHERE user_id=?',(salt,digest,ITERATIONS,row['id']))
        audit(db,row['username'],'CHANGE_OWN_PASSWORD',row['id'])
    version=db.execute('SELECT version FROM credentials WHERE user_id=?',(row['id'],)).fetchone()[0]
    SESSIONS[db]=(row['id'],version)
    login_activity.begin(db,row['id'],version)


def logout(db):
    login_activity.end(db)
    SESSIONS.pop(db,None)
