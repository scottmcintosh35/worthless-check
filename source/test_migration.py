"""One-time editable test snapshot; raw history is preserved, never reposted."""
import datetime as dt
from decimal import Decimal, InvalidOperation
import json
from pathlib import Path
import sqlite3
import tkinter as tk
from tkinter import filedialog, messagebox
import database_tools
import login

RAW_TABLES=('import_meta','source_files','source_tables','legacy_records','legacy_memos','import_issues')

def load(store, path):
    actor=login.require(store.db,True)
    path=Path(path).resolve()
    if path==store.path.resolve():
        raise ValueError('Choose the separate imported legacy database.')
    source=sqlite3.connect(path.as_uri()+'?mode=ro',uri=True)
    source.row_factory=sqlite3.Row
    try:
        report=json.loads(source.execute("SELECT value FROM import_meta WHERE key='report'").fetchone()[0])
        if report.get('status')!='imported_for_read_only_review':
            raise ValueError('The source import is incomplete.')
        if store.db.execute("SELECT 1 FROM sqlite_master WHERE name='test_migration'").fetchone():
            raise ValueError('Legacy test data has already been loaded. Re-import is blocked to avoid duplicates.')
        saved=database_tools.backup(store)
        counts={'defendants':0,'merchants':0,'cases':0,'skipped':0}
        issues=[]
        db=store.db
        db.execute('BEGIN IMMEDIATE')
        try:
            db.execute('CREATE TABLE test_migration(key TEXT PRIMARY KEY,value TEXT NOT NULL)')
            db.execute('CREATE TABLE legacy_links(table_name TEXT,record_no INTEGER,target_id INTEGER,PRIMARY KEY(table_name,record_no))')
            for table in RAW_TABLES:
                sql=source.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name=?",(table,)).fetchone()
                if not sql: raise ValueError('Missing source table: '+table)
                db.execute(sql[0])
                columns=len(source.execute('PRAGMA table_info('+table+')').fetchall())
                db.executemany('INSERT INTO '+table+' VALUES('+','.join('?'*columns)+')',source.execute('SELECT * FROM '+table))
            def records(table):
                for r in source.execute('SELECT record_no,data_json FROM legacy_records WHERE table_name=? AND deleted=0 ORDER BY record_no',(table,)):
                    yield r[0],json.loads(r[1])
            def text(d,key):
                v=d.get(key)
                return '' if v is None else str(v).strip()
            def link(table,n,target):
                db.execute('INSERT INTO legacy_links VALUES(?,?,?)',(table,n,target))
            maps={}
            for table,kind in [('WC_DEF','defendants'),('WC_MERCH','merchants')]:
                ids={}
                for n,d in records(table):
                    name=text(d,'NAME' if kind=='defendants' else 'ME_NAME')
                    if not name:
                        counts['skipped']+=1; issues.append([table,n,'Blank name; retained in raw records']); continue
                    if kind=='defendants':
                        target=db.execute('INSERT INTO defendants(name,profile) VALUES(?,?)',(name,json.dumps(d))).lastrowid
                        old=text(d,'ID')
                    else:
                        vals=[text(d,k) for k in ('ME_NAME','ME_ADDR','ME_CITY','ME_STATE','ME_ZIP','ME_PHONE','ME_CONTACT')]
                        target=db.execute('INSERT INTO merchants(name,address,city,state,zip,phone,contact) VALUES(?,?,?,?,?,?,?)',vals).lastrowid
                        old=text(d,'ME_ID')
                    ids.setdefault(old,[]).append(target)
                    counts[kind]+=1; link(table,n,target)
                maps[table]=ids
            for n,d in records('WC_CASE'):
                try:
                    number=text(d,'CASE_NO')
                    if not number: raise ValueError('Blank case number')
                    amounts=[]
                    for field in ('CK_DUE','FEE_DUE','DA_DUE','WD_DUE'):
                        value=Decimal(text(d,field) or '0')
                        if not value.is_finite() or value<0 or value!=value.quantize(Decimal('.01')):
                            raise ValueError('Invalid or negative '+field)
                        amounts.append(int(value*100))
                    date=text(d,'ENTER_DATE')
                    try: dt.date.fromisoformat(date)
                    except ValueError:
                        date=''
                        issues.append(['WC_CASE',n,'Missing or invalid entry date; left blank'])
                    due=text(d,'DUE_DATE')
                    try: dt.date.fromisoformat(due)
                    except ValueError: due=None
                    defids=maps['WC_DEF'].get(text(d,'DEF_ID'),[])
                    defendant_id=defids[0] if len(defids)==1 else None
                    target=db.execute('''INSERT INTO cases(case_no,defendant,merchant,check_no,entered,due_date,restitution,merchant_fee,da_fee,withdrawal_fee,defendant_id)
                      VALUES(?,?,?,?,?,?,?,?,?,?,?)''',(number,text(d,'DEFENDANT'),text(d,'MERCHANT'),text(d,'CK_NO'),date,due,*amounts,defendant_id)).lastrowid
                    link('WC_CASE',n,target); counts['cases']+=1
                    if not defendant_id: issues.append(['WC_CASE',n,'Defendant ID missing or ambiguous; not linked'])
                except (ValueError,InvalidOperation,sqlite3.IntegrityError,OverflowError) as error:
                    counts['skipped']+=1; issues.append(['WC_CASE',n,str(error)])
            for kind,table in [('defendant','defendants'),('merchant','merchants')]:
                db.execute('UPDATE number_counters SET next_value=MAX(next_value,(SELECT COALESCE(MAX(id),0)+1 FROM '+table+')) WHERE kind=?',(kind,))
            result={'counts':counts,'issues':issues,'backup':str(saved),'source':str(path),'basis':'Legacy CK_DUE/FEE_DUE/DA_DUE/WD_DUE snapshot; historical payments and adjustments retained as raw history, not reposted.'}
            db.execute('INSERT INTO test_migration VALUES(?,?)',('report',json.dumps(result)))
            db.execute('INSERT INTO audit(at,operator,action,reference) VALUES(?,?,?,?)',(dt.datetime.now(dt.timezone.utc).isoformat(),actor,'LOAD_LEGACY_TEST_SNAPSHOT',json.dumps(counts)))
            db.commit()
            return result
        except Exception:
            db.rollback(); raise
    finally:
        source.close()

def dialog(app):
    try:
        login.require(app.store.db,True)
        path=filedialog.askopenfilename(parent=app.root,title='Select imported legacy database for testing',filetypes=[('Imported database','*.sqlite *.db')])
        if not path: return
        if not messagebox.askyesno('Load real records for testing','This adds actual legacy cases, defendants and merchants to this shared evaluation database. All RDP users will see them. A backup is made first.\n\nStarting balances use the legacy due fields; old payments remain review history. Existing test entries remain. This load can run only once.\n\nContinue?',parent=app.root): return
        app.root.config(cursor='watch'); app.root.update_idletasks()
        result=load(app.store,path)
        app.refresh()
        app.root.title('Worthless Check Unit | LEGACY TEST SNAPSHOT - balances not reconciled')
        report=app.store.path.parent/'legacy-test-load-report.json'
        report.write_text(json.dumps(result,indent=2),encoding='utf-8')
        messagebox.showinfo('Test records loaded',str(result['counts'])+'\n\nReport: '+str(report)+'\nBackup: '+result['backup']+'\n\nUse Review Original Legacy Records for full historical details.',parent=app.root)
    except Exception as error:
        messagebox.showerror('Could not load test records',str(error),parent=app.root)
    finally:
        app.root.config(cursor='')
