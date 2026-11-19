"""Prototype numbering, adjustments, archives and database maintenance."""
import datetime as dt
from pathlib import Path
import re
import sqlite3
import uuid
import login

KINDS={'case':('CASE-',6),'adjustment':('ADJ-',7),'receipt':('DEMO-',8),'defendant':('',0),'merchant':('',0)}
AMOUNTS=('restitution','merchant_fee','da_fee','withdrawal_fee')


def add_column(db,table,name,definition):
    if name not in [r[1] for r in db.execute('PRAGMA table_info('+table+')')]:
        db.execute('ALTER TABLE '+table+' ADD COLUMN '+name+' '+definition)


def setup(db):
    db.executescript('''
    CREATE TABLE IF NOT EXISTS number_counters(kind TEXT PRIMARY KEY,prefix TEXT NOT NULL,width INTEGER NOT NULL,next_value INTEGER NOT NULL CHECK(next_value>0));
    CREATE TABLE IF NOT EXISTS allocated_numbers(kind TEXT NOT NULL,number TEXT NOT NULL,value INTEGER NOT NULL,PRIMARY KEY(kind,number));
    CREATE TABLE IF NOT EXISTS merchants(id INTEGER PRIMARY KEY,name TEXT NOT NULL,address TEXT NOT NULL DEFAULT '',city TEXT NOT NULL DEFAULT '',state TEXT NOT NULL DEFAULT '',zip TEXT NOT NULL DEFAULT '',phone TEXT NOT NULL DEFAULT '',contact TEXT NOT NULL DEFAULT '',active INTEGER NOT NULL DEFAULT 1);
    CREATE TABLE IF NOT EXISTS adjustments(id INTEGER PRIMARY KEY AUTOINCREMENT,number TEXT NOT NULL UNIQUE,case_id INTEGER NOT NULL REFERENCES cases(id),at TEXT NOT NULL,operator TEXT NOT NULL,reason TEXT NOT NULL,restitution INTEGER NOT NULL,merchant_fee INTEGER NOT NULL,da_fee INTEGER NOT NULL,withdrawal_fee INTEGER NOT NULL,reverses_id INTEGER UNIQUE REFERENCES adjustments(id));
    CREATE INDEX IF NOT EXISTS adjustments_case ON adjustments(case_id);
    ''')
    for table,col,definition in [('cases','archived',"INTEGER NOT NULL DEFAULT 0"),('cases','archive_reason',"TEXT NOT NULL DEFAULT ''"),('payments','voided','INTEGER NOT NULL DEFAULT 0'),('payments','void_reason',"TEXT NOT NULL DEFAULT ''"),('payments','receipt_code','TEXT')]:
        add_column(db,table,col,definition)
    # Preserve existing demonstration receipt numbers during the schema upgrade.
    db.execute("UPDATE payments SET receipt_code=printf('DEMO-%08d',id) WHERE receipt_code IS NULL")
    db.execute('CREATE UNIQUE INDEX IF NOT EXISTS receipt_codes ON payments(receipt_code)')
    for kind,(prefix,width) in KINDS.items():
        minimum=1
        if kind in ('defendant','merchant'):
            table='defendants' if kind=='defendant' else 'merchants'
            minimum=db.execute('SELECT COALESCE(MAX(id),0)+1 FROM '+table).fetchone()[0]
        elif kind=='receipt':
            minimum=db.execute('SELECT COALESCE(MAX(id),0)+1 FROM payments').fetchone()[0]
        db.execute('INSERT OR IGNORE INTO number_counters VALUES(?,?,?,?)',(kind,prefix,width,minimum))
    db.commit()


def log(db,operator,action,reference):
    db.execute('INSERT INTO audit(at,operator,action,reference) VALUES(?,?,?,?)',
        (dt.datetime.now(dt.timezone.utc).isoformat(),login.require(db) if login.enabled(db) else operator,action,str(reference)))


def configure_number(db,kind,prefix,width,next_value):
    login.require(db,True)
    if kind not in KINDS or not isinstance(next_value,int) or next_value<1 or next_value>999999999 or not isinstance(width,int) or not 0<=width<=12:
        raise ValueError('Enter a positive next number and a width from 0 to 12.')
    if len(prefix)>20 or any(ord(c)<32 for c in prefix):
        raise ValueError('Prefix must be at most 20 printable characters.')
    if kind in ('defendant','merchant') and (prefix or width):
        raise ValueError('Defendant and merchant IDs are plain integers; prefix and width must be empty/zero.')
    with db:
        current=db.execute('SELECT next_value FROM number_counters WHERE kind=?',(kind,)).fetchone()[0]
        if next_value<current:
            raise ValueError('The next number cannot be moved backward. Existing identifiers are preserved.')
        db.execute('UPDATE number_counters SET prefix=?,width=?,next_value=? WHERE kind=?',(prefix,width,next_value,kind))
        log(db,'DEMO','CONFIGURE_NUMBER',kind)


def allocate(db,kind):
    # Called inside the same write transaction as the new record.
    db.execute('UPDATE number_counters SET next_value=next_value WHERE kind=?',(kind,))
    row=db.execute('SELECT * FROM number_counters WHERE kind=?',(kind,)).fetchone()
    value=row['next_value']
    while True:
        number=row['prefix']+str(value).zfill(row['width'])
        used=db.execute('SELECT 1 FROM allocated_numbers WHERE kind=? AND number=?',(kind,number)).fetchone()
        if kind=='case':
            used=used or db.execute('SELECT 1 FROM cases WHERE case_no=?',(number,)).fetchone()
        elif kind=='receipt':
            used=used or db.execute('SELECT 1 FROM payments WHERE receipt_code=?',(number,)).fetchone()
        elif kind in ('defendant','merchant'):
            table='defendants' if kind=='defendant' else 'merchants'
            used=used or db.execute('SELECT 1 FROM '+table+' WHERE id=?',(value,)).fetchone()
        if not used:
            break
        value+=1
    db.execute('UPDATE number_counters SET next_value=? WHERE kind=?',(value+1,kind))
    db.execute('INSERT INTO allocated_numbers VALUES(?,?,?)',(kind,number,value))
    return value if kind in ('defendant','merchant') else number


def adjust(store,case_id,deltas,reason,operator='DEMO',reverses_id=None):
    login.require(store.db,True)
    if login.enabled(store.db):
        operator=login.initials(store.db)
    if len(deltas)!=4 or any(type(v)is not int for v in deltas) or not any(deltas) or not reason.strip() or not operator.strip():
        raise ValueError('Enter at least one signed charge adjustment, a reason and operator initials.')
    db=store.db
    try:
        db.execute('BEGIN IMMEDIATE')
        import reporting
        reporting.assert_open(db,dt.datetime.now(dt.timezone.utc).date().isoformat())
        if store.case(case_id)['archived']:
            raise ValueError('Restore the case before adjusting it.')
        remaining=store.balance(case_id)
        if any(remaining[i]+deltas[i]<0 for i in range(4)):
            raise ValueError('An adjustment cannot reduce a charge below payments already applied.')
        number=allocate(db,'adjustment')
        db.execute('INSERT INTO adjustments(number,case_id,at,operator,reason,restitution,merchant_fee,da_fee,withdrawal_fee,reverses_id) VALUES(?,?,?,?,?,?,?,?,?,?)',
            (number,case_id,dt.datetime.now(dt.timezone.utc).isoformat(),operator.strip(),reason.strip(),*deltas,reverses_id))
        log(db,operator,'ADJUST_CHARGES',number)
        db.commit()
        return number
    except Exception:
        db.rollback()
        raise


def reverse_adjustment(store,adjustment_id,reason,operator):
    row=store.db.execute('SELECT * FROM adjustments WHERE id=?',(adjustment_id,)).fetchone()
    if not row or row['reverses_id'] is not None:
        raise ValueError('Choose an original adjustment to reverse.')
    return adjust(store,row['case_id'],[-row[k] for k in AMOUNTS],reason,operator,reverses_id=adjustment_id)


def archive_case(store,case_id,reason,operator,restore=False):
    login.require(store.db,True)
    if not reason.strip() or not operator.strip():
        raise ValueError('Reason and operator initials are required.')
    db=store.db
    try:
        db.execute('BEGIN IMMEDIATE')
        row=store.case(case_id)
        if bool(row['archived'])==bool(not restore):
            raise ValueError('Case is already in that state.')
        if not restore and db.execute('SELECT 1 FROM payments WHERE case_id=? AND voided=0',(case_id,)).fetchone():
            raise ValueError('A case with active payments cannot be archived. Review its payments first.')
        db.execute('UPDATE cases SET archived=?,archive_reason=?,revision=revision+1 WHERE id=?',(int(not restore),reason.strip(),case_id))
        log(db,operator,'RESTORE_CASE' if restore else 'ARCHIVE_CASE',f'{case_id}: {reason.strip()}')
        db.commit()
    except Exception:
        db.rollback()
        raise


def void_payment(store,payment_id,reason,operator,restore=False):
    login.require(store.db,True)
    if not reason.strip() or not operator.strip():
        raise ValueError('Reason and operator initials are required.')
    db=store.db
    try:
        db.execute('BEGIN IMMEDIATE')
        row=db.execute('SELECT * FROM payments WHERE id=?',(payment_id,)).fetchone()
        if not row or bool(row['voided'])==bool(not restore):
            raise ValueError('Payment not found or already in that state.')
        import reporting
        reporting.assert_open(db,row['paid_date'])
        if store.case(row['case_id'])['archived']:
            raise ValueError('Restore the case before changing a payment.')
        if restore:
            remaining=store.balance(row['case_id'])
            if any(row[k]>remaining[i] for i,k in enumerate(AMOUNTS)):
                raise ValueError('Restoring this payment would exceed a remaining balance.')
        db.execute('UPDATE payments SET voided=?,void_reason=? WHERE id=?',(int(not restore),reason.strip(),payment_id))
        log(db,operator,'RESTORE_PAYMENT' if restore else 'VOID_PAYMENT',f'{payment_id}: {reason.strip()}')
        db.commit()
    except Exception:
        db.rollback()
        raise


def backup(store):
    folder=store.path.parent/'maintenance-backups'
    folder.mkdir(parents=True,exist_ok=True)
    path=folder/(dt.datetime.now().strftime('%Y%m%d-%H%M%S')+'-'+uuid.uuid4().hex[:8]+'.sqlite')
    target=sqlite3.connect(path)
    try:
        store.db.backup(target)
    finally:
        target.close()
    return path


def reindex(store,adjustments_only=False):
    login.require(store.db,True)
    saved=backup(store)
    store.db.execute('REINDEX adjustments_case' if adjustments_only else 'REINDEX')
    result=store.db.execute('PRAGMA integrity_check').fetchone()[0]
    with store.db:
        log(store.db,'DEMO','REINDEX_ADJUSTMENTS' if adjustments_only else 'REINDEX',result)
    return saved,result


def add_custom_column(store,table,name,typ):
    login.require(store.db,True)
    if table not in ('cases','defendants','merchants') or not re.fullmatch(r'custom_[A-Za-z][A-Za-z0-9_]{0,39}',name) or typ not in ('TEXT','INTEGER','REAL'):
        raise ValueError('Choose an allowed table, a custom_ field name and TEXT, INTEGER or REAL.')
    if name.casefold() in [r[1].casefold() for r in store.db.execute('PRAGMA table_info('+table+')')]:
        raise ValueError('That column already exists.')
    saved=backup(store)
    with store.db:
        store.db.execute('ALTER TABLE '+table+' ADD COLUMN '+name+' '+typ)
        log(store.db,'DEMO','ADD_CUSTOM_COLUMN',table+'.'+name)
    return saved


def save_merchant(db,name,address='',city='',state='',zip_code='',phone='',contact='',active=True,merchant_id=None):
    login.require(db)
    if not name.strip():
        raise ValueError('Merchant name is required.')
    with db:
        if merchant_id is None:
            # Acquire a write lock before allocating the ID.
            db.execute("UPDATE number_counters SET next_value=next_value WHERE kind='merchant'")
            merchant_id=allocate(db,'merchant')
            db.execute('INSERT INTO merchants(id,name,address,city,state,zip,phone,contact,active) VALUES(?,?,?,?,?,?,?,?,?)',
                (merchant_id,name.strip(),address.strip(),city.strip(),state.strip(),zip_code.strip(),phone.strip(),contact.strip(),int(active)))
        elif db.execute('UPDATE merchants SET name=?,address=?,city=?,state=?,zip=?,phone=?,contact=?,active=? WHERE id=?',
                (name.strip(),address.strip(),city.strip(),state.strip(),zip_code.strip(),phone.strip(),contact.strip(),int(active),merchant_id)).rowcount!=1:
            raise ValueError('Merchant not found.')
        log(db,'DEMO','SAVE_MERCHANT',merchant_id)
    return merchant_id
