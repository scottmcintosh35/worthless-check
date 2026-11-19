import shortcuts
from defendant_grid import masked_ssn
import performance
"""Full-fidelity working legacy records; immutable originals and audited revisions."""
import datetime as dt
from decimal import Decimal, InvalidOperation
import json
import re
from pathlib import Path
import users
import divisions
import sqlite3
import uuid
from receipt_print import receipt_html
import webbrowser
import tkinter as tk
from tkinter import ttk, filedialog, messagebox, simpledialog
import login
import user_audit
import database_tools
import legacy_reconcile
import case_defaults
import date_format
import document_mode
from test_migration import RAW_TABLES


def setup(db):
    db.executescript('''
    CREATE TABLE IF NOT EXISTS working_legacy(table_name TEXT NOT NULL,record_no INTEGER NOT NULL,
      deleted INTEGER NOT NULL,data_json TEXT NOT NULL,revision INTEGER NOT NULL DEFAULT 0,
      PRIMARY KEY(table_name,record_no));
    CREATE TABLE IF NOT EXISTS legacy_changes(id INTEGER PRIMARY KEY,at TEXT NOT NULL,actor TEXT NOT NULL,
      table_name TEXT NOT NULL,record_no INTEGER NOT NULL,reason TEXT NOT NULL,
      before_json TEXT,after_json TEXT NOT NULL,before_deleted INTEGER,after_deleted INTEGER NOT NULL);
    CREATE TABLE IF NOT EXISTS legacy_work_meta(key TEXT PRIMARY KEY,value TEXT NOT NULL);
    CREATE TABLE IF NOT EXISTS legacy_test_payments(id TEXT PRIMARY KEY,case_record INTEGER NOT NULL,
      payment_record INTEGER NOT NULL,receipt TEXT NOT NULL UNIQUE,at TEXT NOT NULL,actor TEXT NOT NULL,
      method TEXT NOT NULL,allocations_json TEXT NOT NULL,party_json TEXT NOT NULL);
    ''')
    db.execute("CREATE INDEX IF NOT EXISTS working_legacy_case ON working_legacy(table_name,json_extract(data_json,'$.CASE_NO'),deleted)")
    db.execute("CREATE INDEX IF NOT EXISTS working_legacy_receipt ON working_legacy(table_name,trim(json_extract(data_json,'$.RECEIPT_NO')))")
    db.execute('CREATE INDEX IF NOT EXISTS perf_legacy_page ON working_legacy(table_name,deleted,record_no)')
    db.execute("CREATE INDEX IF NOT EXISTS perf_legacy_payment_year ON working_legacy(substr(json_extract(data_json,'$.DATE'),1,4)) WHERE table_name='PAYMENTS'")
    legacy_reconcile.setup(db)
    import legacy_functions
    legacy_functions.setup(db)
    db.commit()


def source_division(db):
    """Identify the office from the preserved legacy USER table."""
    offices = set()
    for (encoded,) in db.execute(
        "SELECT data_json FROM legacy_records WHERE upper(table_name)='USER' AND deleted=0"
    ):
        office = json.loads(encoded)
        city = str(office.get('CITY', '')).strip().casefold()
        county = str(office.get('COUNTY', '')).strip().casefold().removesuffix(' county')
        if city in divisions.LABELS:
            offices.add(city)
        if county == 'pike':
            offices.add('troy')
    return next(iter(offices)) if len(offices) == 1 else None


def initialize(store,path=None,*,confirmed_division=None):
    db=store.db
    actor=login.require(db,True)
    if db.execute("SELECT 1 FROM legacy_work_meta WHERE key='initialized'").fetchone():
        raise ValueError('The full legacy workspace is already loaded. No records were changed.')
    source=None
    if path is not None:
        if Path(path).resolve()==store.path.resolve(): raise ValueError('Choose the separate imported database.')
        source=sqlite3.connect(Path(path).resolve().as_uri()+'?mode=ro',uri=True)
    else:
        if not db.execute("SELECT 1 FROM sqlite_master WHERE name='legacy_records'").fetchone():
            raise ValueError('Choose the imported WC-Imported.sqlite database.')
        source=db
    try:
        report=json.loads(source.execute("SELECT value FROM import_meta WHERE key='report'").fetchone()[0])
        if report.get('status')!='imported_for_read_only_review': raise ValueError('Source import is incomplete.')
        if getattr(store, 'division', None) in divisions.LABELS:
            actual_division = source_division(source)
            if actual_division and actual_division != store.division:
                raise ValueError('The source office does not match the destination division.')
            if confirmed_division and actual_division != confirmed_division:
                raise ValueError('The source office changed. Select and review the database again.')
        backup=database_tools.backup(store)
        db.execute('BEGIN IMMEDIATE')
        try:
            if db.execute("SELECT 1 FROM legacy_work_meta WHERE key='initialized'").fetchone():
                raise ValueError('Another session already initialized the workspace.')
            if source is not db:
                for table in RAW_TABLES:
                    row=source.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name=?",(table,)).fetchone()
                    if not row: raise ValueError('Missing source table: '+table)
                    db.execute(row[0])
                    size=len(source.execute('PRAGMA table_info('+table+')').fetchall())
                    db.executemany('INSERT INTO '+table+' VALUES('+','.join('?'*size)+')',source.execute('SELECT * FROM '+table))
            db.execute('INSERT INTO working_legacy(table_name,record_no,deleted,data_json) SELECT table_name,record_no,deleted,data_json FROM legacy_records')
            difference=db.execute('''SELECT COUNT(*) FROM legacy_records l LEFT JOIN working_legacy w
              ON l.table_name=w.table_name AND l.record_no=w.record_no
              WHERE w.record_no IS NULL OR l.data_json!=w.data_json OR l.deleted!=w.deleted''').fetchone()[0]
            if difference: raise ValueError('Full record verification failed; load rolled back.')
            counts=dict(db.execute('SELECT table_name,COUNT(*) FROM working_legacy GROUP BY table_name').fetchall())
            result={'at':now(),'actor':actor,'counts':counts,'backup':str(backup),'initial_differences':difference}
            db.execute('INSERT INTO legacy_work_meta VALUES(?,?)',('initialized',json.dumps(result)))
            db.execute('INSERT INTO audit(at,operator,action,reference) VALUES(?,?,?,?)',(now(),actor,'FULL_LEGACY_WORKSPACE_LOADED',json.dumps(counts)))
            db.commit()
            return result
        except Exception:
            db.rollback(); raise
    finally:
        if source is not db: source.close()


def now(): return dt.datetime.now(dt.timezone.utc).isoformat()

def schema(db,table):
    row=db.execute('SELECT fields_json FROM source_tables WHERE name=?',(table,)).fetchone()
    if not row: raise ValueError('Unknown legacy table.')
    return json.loads(row[0])

def get(db,table,record):
    row=db.execute('SELECT * FROM working_legacy WHERE table_name=? AND record_no=?',(table,record)).fetchone()
    if not row: raise ValueError('Record not found.')
    return row

def memo_text(db,table,value):
    if isinstance(value,dict) and 'memo' in value:
        if not value['memo']: return ''
        r=db.execute('SELECT text,error FROM legacy_memos WHERE table_name=? AND pointer=?',(table,value['memo'])).fetchone()
        if r and r[0] is not None and not r[1]: return r[0]
        return '[Original memo unavailable or binary; preserved unchanged]'
    return str(value or '')

def validated(field,value):
    typ=field['type']; name=field['name']
    if typ=='M': return value
    if typ=='C':
        if len(value)>field['length']: raise ValueError(name+' exceeds its legacy field width.')
    elif typ in ('N','F'):
        if value.strip():
            try: n=Decimal(value)
            except InvalidOperation: raise ValueError(name+' must be numeric.')
            if not n.is_finite() or n!=n.quantize(Decimal(1).scaleb(-field['decimals'])):
                raise ValueError(name+' has too many decimal places or is not finite.')
            if len(format(n,'f'))>field['length']: raise ValueError(name+' exceeds legacy numeric width.')
    elif typ=='D':
        if value:
            try:
                d=date_format.parse(value)
            except ValueError: raise ValueError(name+' must be MM-DD-YYYY or blank.')
            value=d.strftime('%Y%m%d')
    elif typ=='L':
        if value.upper() not in ('','T','F','Y','N','?'): raise ValueError(name+' must be T, F, or blank.')
        value=value.upper()
    else: raise ValueError(name+' has an unsupported binary type; retain its original value.')
    return value

def _write(db,table,record,data,deleted,revision,reason,actor):
    old=get(db,table,record)
    if old['revision']!=revision: raise ValueError('Another user changed this record. Reopen it before saving.')
    encoded=json.dumps(data,ensure_ascii=True)
    if db.execute('UPDATE working_legacy SET data_json=?,deleted=?,revision=revision+1 WHERE table_name=? AND record_no=? AND revision=?',(encoded,int(deleted),table,record,revision)).rowcount!=1:
        raise ValueError('Record changed; reopen it.')
    db.execute('INSERT INTO legacy_changes(at,actor,table_name,record_no,reason,before_json,after_json,before_deleted,after_deleted) VALUES(?,?,?,?,?,?,?,?,?)',(now(),actor,table,record,reason,old['data_json'],encoded,old['deleted'],int(deleted)))

def save(db,table,record,changes,deleted,revision,reason):
    actor=login.require(db,True)
    if not reason.strip(): raise ValueError('A correction reason is required.')
    try:
        db.execute('BEGIN IMMEDIATE')
        old=get(db,table,record);data=json.loads(old['data_json']);fields={f['name']:f for f in schema(db,table)}
        for key,value in changes.items():
            if key not in fields: raise ValueError('Unknown field: '+key)
            data[key]=validated(fields[key],value)
        if table=='PAYMENTS':
            previous=json.loads(old['data_json'])
            paid_fields=('REST_PAID','SFEE_PAID','FO_PAID','WD_PAID')
            if old['deleted']!=int(deleted) or any(previous.get(k,'')!=data.get(k,'') for k in (*paid_fields,'CASE_NO')):
                deltas={}
                for entry,marker,sign in [(previous,old['deleted'],-1),(data,int(deleted),1)]:
                    number=str(entry.get('CASE_NO',''))
                    delta=deltas.setdefault(number,[Decimal('0')]*4)
                    if not marker:
                        for i,key in enumerate(paid_fields):delta[i]+=sign*money(entry.get(key,''))
                for number,delta in deltas.items():
                    if not any(delta):continue
                    if legacy_reconcile.explicit(db,record) and previous.get('CASE_NO','')!=data.get('CASE_NO',''):
                        raise ValueError('Use the reconciliation screen to reassign an explicitly linked payment; its legacy CASE_NO stays preserved.')
                    matches=legacy_reconcile.resolve(db,record,number)
                    if len(matches)!=1:raise ValueError('This financial correction has no unique active case. Resolve its case number/link first; no changes were saved.')
                    case_row=matches[0];case=json.loads(case_row['data_json'])
                    for due,paid_key,amount in zip(('CK_DUE','FEE_DUE','DA_DUE','WD_DUE'),paid_fields,delta):
                        if amount:
                            new_due=money(case.get(due,''))-amount
                            if new_due<0:raise ValueError('Correction would make '+due+' negative; reconcile the case first.')
                            case[due]=format(new_due,'.2f');case[paid_key]=format(money(case.get(paid_key,''))+amount,'.2f')
                    if 'AMT_PAID' in case:case['AMT_PAID']=format(money(case['AMT_PAID'])+sum(delta),'.2f')
                    _write(db,'WC_CASE',case_row['record_no'],case,False,case_row['revision'],'Payment correction: '+reason,actor)
        _write(db,table,record,data,deleted,revision,reason,actor)
        db.commit()
    except Exception:
        db.rollback(); raise


def next_case_number(db, entered):
    year = case_defaults.entered_date(entered).strftime('%y')
    rows = db.execute("""SELECT json_extract(data_json,'$.CASE_NO') AS number
        FROM working_legacy WHERE table_name='WC_CASE'
        UNION ALL
        SELECT json_extract(data_json,'$.CASE_NO') FROM legacy_records WHERE table_name='WC_CASE'
        UNION ALL
        SELECT json_extract(after_json,'$.CASE_NO') FROM legacy_changes WHERE table_name='WC_CASE'
    """)
    pattern = re.compile(re.escape(year) + r'-([0-9]+)')
    highest = 0
    for (number,) in rows:
        match = pattern.fullmatch(str(number or '').strip())
        if match:
            highest = max(highest, int(match[1]))
    if highest >= 999:
        raise ValueError(f'No case numbers remain for year {year} in the YY-NNN format.')
    return f'{year}-{highest + 1:03}'


PARTY_ID_FIELDS = {'WC_MERCH': ('ME_ID','MERCH_ID'), 'WC_DEF': ('ID','DEF_ID')}


def next_party_id(db, table):
    from case_window import id_value

    # Include archived records, prior assignments and IDs referenced by cases.
    field, case_field = PARTY_ID_FIELDS[table]
    path, case_path = '$.' + field, '$.' + case_field
    rows = db.execute("""SELECT
        json_extract(data_json, CASE table_name WHEN 'WC_CASE' THEN ? ELSE ? END)
        FROM working_legacy WHERE table_name IN (?,'WC_CASE')
        UNION ALL SELECT
        json_extract(data_json, CASE table_name WHEN 'WC_CASE' THEN ? ELSE ? END)
        FROM legacy_records WHERE table_name IN (?,'WC_CASE')
        UNION ALL SELECT json_extract(after_json,?)
        FROM legacy_changes WHERE table_name=?
        UNION ALL SELECT json_extract(before_json,?)
        FROM legacy_changes WHERE table_name=?""",
        (case_path,path,table,case_path,path,table,path,table,path,table))
    highest = 0
    for (value,) in rows:
        number = id_value(value)
        if number and number.isascii() and number.isdecimal():
            highest = max(highest, int(number))
    return str(highest + 1)


def create(db,table,data,reason):
    # Staff may create a new case; changing existing records and creating
    # other legacy record types retain their Administrator requirement.
    actor=login.require(db,table!='WC_CASE')
    if not reason.strip():raise ValueError('A reason is required.')
    fields=schema(db,table)
    allowed={f['name'] for f in fields}
    if set(data)-allowed:raise ValueError('Unknown fields.')
    if table=='WC_CASE':
        data={k:v for k,v in case_defaults.apply_missing(db,data).items() if k in allowed and k != 'CASE_NO'}
    elif table in PARTY_ID_FIELDS:
        id_field = PARTY_ID_FIELDS[table][0]
        data={k:v for k,v in data.items() if k != id_field}
    values={f['name']:validated(f,data.get(f['name'],'')) if f['type'] in ('C','N','F','D','L','M') else {'raw_hex':''} for f in fields}
    required={'WC_CASE':('DEFENDANT','MERCHANT'),'WC_DEF':('NAME',),'WC_MERCH':('ME_NAME',),
              'BANKCODE':('CODE','BANK')}
    for key in required.get(table,()):
        if not str(values.get(key,'')).strip():raise ValueError(key+' is required for a new record.')
    if table=='PAYMENTS':raise ValueError('Use Record test payment for new payments, so balances update atomically.')
    try:
        db.execute('BEGIN IMMEDIATE')
        if table == 'BANKCODE':
            exists = db.execute("""SELECT 1 FROM working_legacy WHERE table_name='BANKCODE'
                AND trim(json_extract(data_json,'$.CODE'))=? COLLATE NOCASE LIMIT 1""",
                (values['CODE'].strip(),)).fetchone()
            if exists:
                raise ValueError('That bank code already exists.')
        if table in PARTY_ID_FIELDS:
            field = next(f for f in fields if f['name'] == id_field)
            values[id_field] = validated(field, next_party_id(db, table))
        if table == 'WC_CASE':
            field = next(f for f in fields if f['name'] == 'CASE_NO')
            values['CASE_NO'] = validated(field, next_case_number(db, values['ENTER_DATE']))
        n=db.execute('SELECT COALESCE(MAX(record_no),0)+1 FROM working_legacy WHERE table_name=?',(table,)).fetchone()[0]
        encoded=json.dumps(values)
        db.execute('INSERT INTO working_legacy(table_name,record_no,deleted,data_json) VALUES(?,?,0,?)',(table,n,encoded))
        db.execute('INSERT INTO legacy_changes(at,actor,table_name,record_no,reason,after_json,after_deleted) VALUES(?,?,?,?,?,?,0)',(now(),actor,table,n,reason,encoded))
        db.commit();return n
    except Exception:
        db.rollback();raise


def money(value):
    try:
        n=Decimal(str(value).strip() or '0')
        if not n.is_finite() or n!=n.quantize(Decimal('.01')): raise InvalidOperation
        return n
    except (InvalidOperation,ValueError): raise ValueError('Invalid legacy money value; correct it before posting.')


def receipt_number_width(db):
    exists = db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='source_tables'").fetchone()
    record = db.execute("SELECT fields_json FROM source_tables WHERE name='PAYMENTS'").fetchone() if exists else None
    if record:
        field = next((item for item in json.loads(record[0]) if item['name']=='RECEIPT_NO'), None)
        if field:
            return min(18, field['length'])
    return 18


def next_payment_receipt(db):
    # Read under the payment transaction's write lock. Include deleted and original rows.
    highest = db.execute("""SELECT MAX(CAST(number AS INTEGER)) FROM (
        SELECT trim(json_extract(data_json,'$.RECEIPT_NO')) AS number
            FROM working_legacy WHERE table_name='PAYMENTS'
        UNION ALL
        SELECT trim(json_extract(data_json,'$.RECEIPT_NO'))
            FROM legacy_records WHERE table_name='PAYMENTS'
        UNION ALL
        SELECT trim(receipt) FROM legacy_test_payments
    ) WHERE number <> '' AND number NOT GLOB '*[^0-9]*'""").fetchone()[0]
    configured = int(users.get_settings(db)['RECEIPT_START'] or 1)
    number = str(max((highest or 0) + 1, configured))
    if len(number) > receipt_number_width(db):
        raise ValueError('The next numeric receipt does not fit the legacy receipt field. Review the sequence before posting.')
    return number


def payment_date_from_form(value):
    value = value.strip()
    try:
        parsed = dt.datetime.strptime(value, '%m-%d-%Y').date()
        if f'{parsed.month:02}-{parsed.day:02}-{parsed.year:04}' != value:
            raise ValueError
        return parsed.isoformat()
    except ValueError:
        raise ValueError('Enter a valid payment date in MM-DD-YYYY format.') from None


def payment_date_display(value):
    if isinstance(value, str) and len(value) == 8 and value.isascii() and value.isdigit():
        return f'{value[4:6]}-{value[6:8]}-{value[:4]}'
    return value


PAYMENT_DUE_FIELDS = ('CK_DUE','FEE_DUE','DA_DUE','WD_DUE')
PAYMENT_BALANCE_LABELS = ('Restitution','Merchant fee','DA / warrant fee','Withdrawal fee')


def remaining_payment_amounts(case):
    return [money(case.get(field,'')) for field in PAYMENT_DUE_FIELDS]


def receipt_balance_lines(amounts, format_amount, *, current=False):
    prefix = 'Current remaining' if current else 'Remaining'
    total_label = 'Current remaining case balance' if current else 'Remaining balance after payment'
    return {
        **{f'{prefix} {label}': format_amount(amount)
           for label, amount in zip(
               ('restitution','merchant fee','DA / warrant fee','withdrawal fee'), amounts)},
        total_label: format_amount(sum(amounts)),
    }


def payment_balance_preview(parent, entries, balances, parse, format_amount):
    """Follow edits, including pasted amounts, without changing the case."""
    inputs = [tk.StringVar(master=parent,value=entry.get()) for entry in entries]
    for entry, value in zip(entries,inputs):
        entry.configure(textvariable=value)
    first_row = entries[0].grid_info()['row']
    ttk.Label(parent,text='After payment').grid(row=first_row-1,column=2,padx=12,sticky='e')
    breakdown = []
    for entry in entries:
        label = ttk.Label(parent)
        label.grid(row=entry.grid_info()['row'],column=2,padx=12,sticky='e')
        breakdown.append(label)
    preview = ttk.Label(parent)

    def update(*_):
        remaining = []
        for value, due, label in zip(inputs, balances, breakdown):
            try:
                amount = parse(value.get().strip() or '0')
                if amount < 0 or (amount and amount > due):
                    raise ValueError
            except ValueError:
                label.configure(text='Check amount')
            else:
                balance = due - amount
                remaining.append(balance)
                label.configure(text=format_amount(balance))
        if len(remaining) != len(balances):
            preview.configure(text='Remaining after payment: check payment amounts')
        else:
            preview.configure(text='Remaining after payment: ' + format_amount(sum(remaining)))

    for value in inputs:
        value.trace_add('write',update)
    update()
    return preview


def payment_receipt_balance(db, payment_record, payment):
    label = 'Remaining balance after payment'
    saved = db.execute('SELECT party_json FROM legacy_test_payments WHERE payment_record=?',
                       (payment_record,)).fetchone()
    snapshot = json.loads(saved[0]) if saved else {}
    if 'Remaining restitution' in snapshot:
        return {key: value for key, value in snapshot.items() if key.startswith('Remaining ')}
    historical = {label: snapshot[label]} if label in snapshot else {}
    # Older payments may only have a saved total. Label live values separately.
    cases = legacy_reconcile.resolve(db,payment_record,payment.get('CASE_NO',''))
    if len(cases) == 1:
        try:
            amounts = remaining_payment_amounts(json.loads(cases[0]['data_json']))
            return {**historical, **receipt_balance_lines(amounts, lambda value:f'${value:,.2f}', current=True)}
        except ValueError:
            pass
    return {**historical, 'Current remaining case balance': 'Unavailable'}


def posted_receipt_text(db, row, *, reprint=False):
    payment = json.loads(row['party_json'])
    paid = [money(value) for value in json.loads(row['allocations_json'])]
    balance = payment_receipt_balance(db, row['payment_record'], payment)
    return '\n'.join([
        users.document_heading(db), users.document_contact(db), '',
        'Payment Receipt' + (' (reprint)' if reprint else ''),
        {document_mode.OFFICIAL: 'OFFICIAL RECEIPT', document_mode.REHEARSAL: document_mode.REHEARSAL_MARK}.get(
            payment.get('_document_mode'), 'TEST RECEIPT — NOT OFFICIAL'), '',
        f"Receipt number: {row['receipt']}",
        f"Case number: {payment.get('CASE_NO', '').strip()}",
        f"Payment date: {payment_date_display(payment.get('DATE', ''))}",
        f"Defendant: {payment.get('DEFENDANT', '').strip()}",
        f"Merchant: {payment.get('MERCHANT', '').strip()}",
        f"Payment method: {row['method']}",
        f"Recorded by: {row['actor']}", '',
        *[f'{label} paid: ${amount:,.2f}' for label, amount in zip(PAYMENT_BALANCE_LABELS, paid)],
        f'Total received: ${sum(paid):,.2f}', '',
        *[f'{label}: {amount}' for label, amount in balance.items()],
    ])


def has_unofficial_payments(db):
    return db.execute("""
        SELECT 1 FROM legacy_test_payments
        WHERE COALESCE(json_extract(party_json,'$._document_mode'),'test') <> 'official'
        LIMIT 1
    """).fetchone() is not None


def post_payment(db,case_record,revision,date,receipt,method,amounts,*,output_mode=document_mode.TEST):
    actor=login.require(db)
    import reporting
    paid_on = dt.date.fromisoformat(date)
    if receipt is not None:
        receipt=receipt.strip()
        if not receipt or len(receipt)>40: raise ValueError('Enter a receipt number of at most 40 characters.')
    if method not in ('Cash','Money order','Other'): raise ValueError('Choose a payment method.')
    if len(amounts)!=4: raise ValueError('Four allocations are required.')
    amounts=[money(a) for a in amounts]
    if any(a<0 for a in amounts) or sum(amounts)<=0: raise ValueError('Enter positive, nonnegative payment allocations.')
    try:
        db.execute('BEGIN IMMEDIATE')
        official_started = db.execute("SELECT 1 FROM legacy_work_meta WHERE key='official_payments_started'").fetchone()
        if official_started and output_mode != document_mode.OFFICIAL:
            raise ValueError('Official payments already started in this workspace. Use a rehearsal copy for test payments.')
        if output_mode == document_mode.OFFICIAL and not official_started:
            if has_unofficial_payments(db):
                raise ValueError('This workspace contains test payments. Use the verified final cutoff import for official payments.')
            db.execute("INSERT INTO legacy_work_meta VALUES('official_payments_started','1')")
        reporting.assert_open(db,paid_on.isoformat())
        row=get(db,'WC_CASE',case_record)
        if row['revision']!=revision: raise ValueError('Case changed; reopen it before posting.')
        if row['deleted']: raise ValueError('Restore this deleted case before posting.')
        case=json.loads(row['data_json']); number=str(case.get('CASE_NO',''))
        if not number.strip(): raise ValueError('The case number is blank; correct it first.')
        # Duplicate case numbers cannot be safely linked to the old payment table.
        same=db.execute("SELECT COUNT(*) FROM working_legacy WHERE table_name='WC_CASE' AND deleted=0 AND json_extract(data_json,'$.CASE_NO')=?",(number,)).fetchone()[0]
        if same!=1: raise ValueError('Duplicate case number. Resolve the case identity before posting.')
        if receipt is None:
            receipt = next_payment_receipt(db)
        exists=db.execute("SELECT 1 FROM working_legacy WHERE table_name='PAYMENTS' AND trim(json_extract(data_json,'$.RECEIPT_NO'))=? LIMIT 1",(receipt,)).fetchone()
        if exists or db.execute('SELECT 1 FROM legacy_test_payments WHERE receipt=?',(receipt,)).fetchone(): raise ValueError('Receipt number already exists, including retained/deleted history.')
        paid=('REST_PAID','SFEE_PAID','FO_PAID','WD_PAID')
        for due,paid_key,amount in zip(PAYMENT_DUE_FIELDS,paid,amounts):
            balance=money(case.get(due,''))
            if amount and amount>balance: raise ValueError(due+' allocation exceeds the recorded balance.')
            if amount:
                case[due]=format(balance-amount,'.2f');case[paid_key]=format(money(case.get(paid_key,''))+amount,'.2f')
        if 'AMT_PAID' in case: case['AMT_PAID']=format(money(case['AMT_PAID'])+sum(amounts),'.2f')
        payment={f['name']:'' for f in schema(db,'PAYMENTS')}
        payment.update({'CASE_NO':number,'DATE':paid_on.isoformat().replace('-',''),'RECEIPT_NO':receipt,'DEFENDANT':case.get('DEFENDANT',''),'MERCHANT':case.get('MERCHANT',''),'INITIALS':login.initials(db)[:2]})
        for key,amount in zip(paid,amounts):payment[key]=format(amount,'.2f')
        payment['CASH']=format(sum(amounts) if method=='Cash' else Decimal('0'),'.2f');payment['MONEY_ORD']=format(sum(amounts) if method=='Money order' else Decimal('0'),'.2f')
        # Validate all newly populated fields against source widths before any writes.
        for f in schema(db,'PAYMENTS'):
            if payment[f['name']]!='':payment[f['name']]=validated(f,payment[f['name']])
        n=db.execute("SELECT COALESCE(MAX(record_no),0)+1 FROM working_legacy WHERE table_name='PAYMENTS'").fetchone()[0]
        encoded=json.dumps(payment)
        db.execute("INSERT INTO working_legacy(table_name,record_no,deleted,data_json) VALUES('PAYMENTS',?,0,?)",(n,encoded))
        reason={'official':'New payment ', 'official-rehearsal':'New rehearsal payment '}.get(output_mode,'New test payment ')+receipt
        db.execute("INSERT INTO legacy_changes(at,actor,table_name,record_no,reason,after_json,after_deleted) VALUES(?,?,'PAYMENTS',?,?,?,0)",(now(),actor,n,reason,encoded))
        _write(db,'WC_CASE',case_record,case,False,revision,reason,actor)
        token=uuid.uuid4().hex
        receipt_data = dict(payment, **receipt_balance_lines(
            remaining_payment_amounts(case), lambda value:f'${value:,.2f}'))
        if output_mode != document_mode.TEST:
            receipt_data['_document_mode'] = output_mode
        db.execute('INSERT INTO legacy_test_payments VALUES(?,?,?,?,?,?,?,?,?)',(token,case_record,n,receipt,now(),actor,method,json.dumps([str(a) for a in amounts]),json.dumps(receipt_data)))
        db.execute('INSERT INTO legacy_payment_links(payment_record,case_record,basis,at,actor) VALUES(?,?,?,?,?)',(n,case_record,'new_payment',now(),actor))
        db.commit();return n
    except Exception:
        db.rollback();raise


def reconciliation(db):
    original=db.execute('SELECT COUNT(*) FROM legacy_records').fetchone()[0]
    counts=dict(db.execute('SELECT table_name,COUNT(*) FROM working_legacy GROUP BY table_name').fetchall())
    duplicates=db.execute("SELECT COUNT(*) FROM (SELECT json_extract(data_json,'$.CASE_NO') FROM working_legacy WHERE table_name='WC_CASE' AND deleted=0 GROUP BY json_extract(data_json,'$.CASE_NO') HAVING COUNT(*)>1)").fetchone()[0]
    unmatched=db.execute("""SELECT COUNT(*) FROM working_legacy p WHERE p.table_name='PAYMENTS' AND p.deleted=0 AND
      NOT EXISTS(SELECT 1 FROM legacy_payment_links l WHERE l.payment_record=p.record_no) AND
      (SELECT COUNT(*) FROM working_legacy c WHERE c.table_name='WC_CASE' AND c.deleted=0 AND json_extract(c.data_json,'$.CASE_NO')=json_extract(p.data_json,'$.CASE_NO'))!=1""").fetchone()[0]
    totals={}
    for origin in ('legacy_records','working_legacy'):
        sums={k:Decimal('0') for k in ('REST_PAID','SFEE_PAID','FO_PAID','CC_PAID','WD_PAID','COURT_REST','OVERPAID')}
        invalid={k:0 for k in sums}
        for r in db.execute("SELECT data_json FROM "+origin+" WHERE table_name='PAYMENTS' AND deleted=0"):
            d=json.loads(r[0])
            for k in sums:
                try:sums[k]+=money(d.get(k,''))
                except ValueError:invalid[k]+=1
        totals[origin]={'active_payment_totals':{k:str(v) for k,v in sums.items()},'invalid_values_retained':invalid}
    return {'explicit_payment_links':db.execute('SELECT COUNT(*) FROM legacy_payment_links').fetchone()[0],'audited_reconciliations':db.execute('SELECT COUNT(*) FROM legacy_reconciliations').fetchone()[0],'payment_totals':totals,'original_records':original,'working_counts':counts,'duplicate_case_numbers':duplicates,'payments_without_unique_active_case':unmatched,'corrections':db.execute('SELECT COUNT(*) FROM legacy_changes').fetchone()[0]}


class Workspace:
    def __init__(self,app):
        self.app=app;self.db=app.store.db
        app.legacy_workspace=self
        login.require(self.db)
        user_audit.opened(self.db,'LEGACY_WORKSPACE','Complete Legacy Workspace')
        self.win=tk.Toplevel(app.root);self.win.title('Complete Legacy Workspace | Test candidate');self.win.geometry('1250x780')
        import legacy_functions
        navigation=tk.Menu(self.win);functions=tk.Menu(navigation,tearoff=False);legacy_functions.populate_menu(functions,lambda action:self.safe(lambda:legacy_functions.Center(self,action)),self.db);navigation.add_cascade(label='Functions',menu=functions);self.win.configure(menu=navigation)
        ttk.Label(self.win,text='All original fields and payment rows retained. Corrections require an Administrator and a reason. New test payments update this workspace only.',wraplength=1200).pack(anchor='w',padx=12,pady=8)
        bar=ttk.Frame(self.win);bar.pack(fill='x',padx=12)
        self.shortcut_strip=shortcuts.strip(self.win,'Ctrl+Enter: Details   |   Ctrl+W: Case payment history   |   Ctrl+F: Search   |   F5: Refresh   |   Esc: Clear selection   |   F1: Shortcuts')
        self.table=tk.StringVar(value='WC_CASE');self.query=tk.StringVar();self.deleted=tk.BooleanVar();self.offset=0
        self.names=[r[0] for r in self.db.execute('SELECT name FROM source_tables ORDER BY name')]
        user=login.current(self.db)
        if user and user['role']!='Administrator': self.names=[n for n in self.names if n not in ('SECURITY','FOXUSER','WC_USER','USER')]
        choice=ttk.Combobox(bar,textvariable=self.table,values=self.names,state='readonly',width=18);choice.pack(side='left');choice.bind('<<ComboboxSelected>>',lambda e:self.search())
        entry=ttk.Entry(bar,textvariable=self.query,width=30);entry.pack(side='left',padx=8);entry.bind('<Return>',lambda e:self.search())
        ttk.Button(bar,text='Search all fields',command=self.search).pack(side='left')
        ttk.Checkbutton(bar,text='Include deleted',variable=self.deleted,command=self.search).pack(side='left')
        ttk.Button(bar,text='Reconcile payment / case',command=lambda:self.safe(self.reconcile_payment)).pack(side='left',padx=8)
        ttk.Button(bar,text='Reconciliation totals',command=self.report).pack(side='left',padx=4)
        holder=ttk.Frame(self.win);holder.pack(fill='both',expand=True,padx=12,pady=10)
        self.tree=ttk.Treeview(holder,show='headings');self.tree.grid(row=0,column=0,sticky='nsew')
        y=ttk.Scrollbar(holder,orient='vertical',command=self.tree.yview);y.grid(row=0,column=1,sticky='ns')
        x=ttk.Scrollbar(holder,orient='horizontal',command=self.tree.xview);x.grid(row=1,column=0,sticky='ew');self.tree.configure(yscrollcommand=y.set,xscrollcommand=x.set)
        holder.rowconfigure(0,weight=1);holder.columnconfigure(0,weight=1)
        self.tree.bind('<Double-1>',lambda e:self.details())
        self.shortcut_handlers=shortcuts.bind_list(self.tree,{'<Control-Return>':lambda:self.safe(self.details),'<Control-w>':lambda:self.safe(self.history),'<Control-f>':lambda:shortcuts.focus_search(entry),'<F5>':lambda:self.safe(self.refresh),'<Escape>':lambda:shortcuts.clear_selection(self.tree),'<F1>':lambda:shortcuts.show_help(self.win,'Complete Legacy Workspace',shortcuts.LEGACY)})
        edit_menu=tk.Menu(navigation,tearoff=False)
        for label,key,fn in [('Selected row details','Ctrl+Enter',lambda:self.safe(self.details)),('Case payment history','Ctrl+W',lambda:self.safe(self.history)),('Find records','Ctrl+F',lambda:shortcuts.focus_search(entry)),('Refresh table','F5',lambda:self.safe(self.refresh)),('Clear selection','Esc',lambda:shortcuts.clear_selection(self.tree)),('Keyboard shortcuts','F1',lambda:shortcuts.show_help(self.win,'Complete Legacy Workspace',shortcuts.LEGACY))]:edit_menu.add_command(label=label,accelerator=key,command=fn)
        navigation.add_cascade(label='Edit',menu=edit_menu)

        buttons=ttk.Frame(self.win);buttons.pack(fill='x',padx=12,pady=8)
        for title,fn in [('Previous',lambda:self.page(-1)),('Next',lambda:self.page(1)),('New record',lambda:self.details(new=True)),('View / correct all fields',self.details),('Case payment history',self.history),('Record test payment',self.payment),('Print payment',self.print_payment)]:ttk.Button(buttons,text=title,command=lambda f=fn:self.safe(f)).pack(side='left',padx=3)
        self.status=tk.StringVar();ttk.Label(self.win,textvariable=self.status).pack(anchor='w',padx=12,pady=8)
        self.search()

    def safe(self,fn):
        try:fn()
        except Exception as e:messagebox.showerror('Cannot complete action',str(e),parent=self.win)
    def search(self):self.offset=0;self.refresh()
    def page(self,delta):self.offset=max(0,self.offset+delta*150);self.refresh()
    def refresh(self):
        table=self.table.get()
        definitions = schema(self.db,table)
        fields = [f['name'] for f in definitions]
        date_fields = {f['name'] for f in definitions if f['type']=='D'}
        columns=['_row','_deleted']+fields
        if tuple(self.tree['columns'])!=tuple(columns):
            self.tree['columns']=columns
            for field in columns:
                self.tree.heading(field,text={'_row':'Source row','_deleted':'Deleted'}.get(field,field));self.tree.column(field,width=140,stretch=False)
        sql='FROM working_legacy WHERE table_name=?';args=[table]
        if getattr(self,'deleted_only',False):sql+=' AND deleted=1'
        elif not self.deleted.get():sql+=' AND deleted=0'
        query=self.query.get()
        if query:sql+=' AND data_json LIKE ?';args.append('%'+query+'%')
        cache_key=(table,query,bool(self.deleted.get()),bool(getattr(self,'deleted_only',False)),performance.change_marker(self.db))
        if getattr(self,'_count_key',None)!=cache_key:
            self._match_count=self.db.execute('SELECT COUNT(*) '+sql,args).fetchone()[0];self._count_key=cache_key
        count=self._match_count
        rows=self.db.execute('SELECT * '+sql+' ORDER BY record_no LIMIT 150 OFFSET ?',(*args,self.offset)).fetchall()
        decoded=[(r,json.loads(r['data_json'])) for r in rows]
        pointers={value['memo'] for r,data in decoded for value in data.values() if isinstance(value,dict) and value.get('memo')}
        memos={}
        ids=list(pointers)
        for start in range(0,len(ids),500):
            part=ids[start:start+500]
            for r in self.db.execute('SELECT pointer,text,error FROM legacy_memos WHERE table_name=? AND pointer IN ('+','.join('?'*len(part))+')',(table,*part)):
                memos[r[0]]=r[1] if r[1] is not None and not r[2] else '[Original memo unavailable or binary; preserved unchanged]'
        def display(value):
            if isinstance(value,dict) and 'memo' in value:
                return memos.get(value['memo'],'[Original memo unavailable or binary; preserved unchanged]') if value['memo'] else ''
            return str(value or '')
        selected=self.tree.selection();self.tree.delete(*self.tree.get_children())
        for r,data in decoded:
            cells = [display(data.get(field,''))[:400] for field in fields]
            cells = [date_format.display(value) if field in date_fields else value for field,value in zip(fields,cells)]
            if table == 'WC_DEF' and 'SSN' in fields:
                index = fields.index('SSN')
                cells[index] = masked_ssn(cells[index])
            self.tree.insert('','end',iid=str(r['record_no']),values=[r['record_no'],'Yes' if r['deleted'] else '',*cells])
        if selected and self.tree.exists(selected[0]):self.tree.selection_set(selected[0])
        first=self.offset+1 if count else 0
        self.status.set(f'{table}: {count:,} matching records. Rows {first}-{min(self.offset+150,count)}. Scroll horizontally for every field. Refresh/search to see other users\' changes.')
    def selected(self):
        if not self.tree.selection():raise ValueError('Select a record first.')
        return int(self.tree.selection()[0])
    def details(self,new=False):
        if self.table.get()=='WC_CASE':
            from case_window import CaseWindow
            return CaseWindow(self.app,None if new else self.selected())
        return self.details_all_fields(new)

    def details_all_fields(self,new=False,*,table=None,record=None):
        table = table or self.table.get()
        n = None if new else (self.selected() if record is None else record)
        row={'deleted':0,'revision':0} if new else get(self.db,table,n);data=(case_defaults.legacy_defaults(self.db) if table=='WC_CASE' else {}) if new else json.loads(row['data_json'])
        if not new:
            user_audit.opened(self.db,{'WC_DEF':'DEFENDANT','WC_MERCH':'MERCHANT','PAYMENTS':'PAYMENT'}.get(table,'RECORD'),f'{table} / row {n}')
        win=tk.Toplevel(self.win);win.title(f'{table} / source row {n} - all fields');win.geometry('900x680')
        book=ttk.Notebook(win);book.pack(fill='both',expand=True,padx=10,pady=10)
        entries={};initial={}
        fields=schema(self.db,table)
        if new and table in PARTY_ID_FIELDS:
            fields = [field for field in fields if field['name'] != PARTY_ID_FIELDS[table][0]]
            party = 'Defendant' if table == 'WC_DEF' else 'Merchant'
            ttk.Label(win,text=f'{party} ID is assigned when saved.').pack(anchor='w',padx=12)
        for start in range(0,len(fields),10):
            page=ttk.Frame(book);book.add(page,text=f'Fields {start+1}-{min(start+10,len(fields))}')
            for i,f in enumerate(fields[start:start+10]):
                key=f['name'];value=data.get(key,'');display=memo_text(self.db,table,value)
                if f['type']=='D':display=date_format.display(display)
                ttk.Label(page,text=key+' ('+('MM-DD-YYYY' if f['type']=='D' else f['type'])+')').grid(row=i,column=0,sticky='w',padx=8,pady=7)
                if table == 'WC_DEF' and key == 'SSN':
                    widget = ttk.Entry(page, width=75, show='*')
                    widget.insert(0, display)
                    ttk.Label(page,text=masked_ssn(display)).grid(row=i,column=2,sticky='w',padx=8)
                else:
                    widget=tk.Text(page,width=75,height=3 if f['type']=='M' else 1,wrap='word')
                    widget.insert('1.0',display)
                widget.grid(row=i,column=1,sticky='ew',padx=8,pady=7)
                entries[key]=widget;initial[key]=display
            page.columnconfigure(1,weight=1)
        history=ttk.Frame(book);book.add(history,text='Original / change history')
        original=self.db.execute('SELECT data_json,deleted FROM legacy_records WHERE table_name=? AND record_no=?',(table,n)).fetchone()
        text=tk.Text(history,wrap='word');text.pack(fill='both',expand=True)
        def display_record(encoded):
            record = json.loads(encoded)
            if table == 'WC_DEF' and 'SSN' in record:
                record['SSN'] = masked_ssn(record['SSN'])
            return json.dumps(record, indent=2)
        text.insert('end','ORIGINAL BACKUP (unchanged)\n'+(display_record(original[0]) if original else 'New record')+'\n\nAUDITED CORRECTIONS\n')
        for change in self.db.execute('SELECT at,actor,reason,before_json,after_json FROM legacy_changes WHERE table_name=? AND record_no=? ORDER BY id',(table,n)):
            visible = dict(change)
            if table == 'WC_DEF':
                for key in ('before_json','after_json'):
                    if visible[key]:
                        visible[key] = display_record(visible[key])
            text.insert('end',json.dumps(visible,indent=2)+'\n')
        text.configure(state='disabled')
        flag=tk.BooleanVar(value=bool(row['deleted']));ttk.Checkbutton(win,text='Deleted / archived marker (original remains preserved)',variable=flag).pack(anchor='w',padx=12)
        ttk.Label(win,text='Reason required. Payment allocation corrections/voids update a unique linked case. Other fields are saved as entered.').pack(anchor='w',padx=12)
        reason=ttk.Entry(win,width=100);reason.pack(fill='x',padx=12,pady=6)
        def commit():
            def do():
                values = {k:w.get('1.0','end-1c') if isinstance(w,tk.Text) else w.get()
                          for k,w in entries.items()}
                changes={k:v for k,v in values.items() if v!=initial[k]}
                if new:
                    if table=='WC_CASE' and values.get('DUE_DATE','')==initial.get('DUE_DATE','') and values.get('ENTER_DATE','')!=initial.get('ENTER_DATE',''):values['DUE_DATE']=case_defaults.due_date(self.db,values['ENTER_DATE']).strftime('%Y%m%d')
                    create(self.db,table,values,reason.get())
                else:
                    save(self.db,table,n,changes,flag.get(),row['revision'],reason.get())
                win.destroy();self.refresh()
            self.safe(do)
        if table=='WC_CASE':
            bar=ttk.Frame(win);bar.pack(fill='x',padx=12)
            def set_fields(values):
                for k,v in values.items():
                    if k in entries:entries[k].delete('1.0','end');entries[k].insert('1.0',str(v))
            def recalc():set_fields({'DUE_DATE':date_format.display(case_defaults.due_date(self.db,entries['ENTER_DATE'].get('1.0','end-1c')))})
            def withdrawal():
                import users
                fee=users.get_settings(self.db)['WITHDRAWAL_FEE'];paid=money(entries['WD_PAID'].get('1.0','end-1c')) if 'WD_PAID' in entries else money(data.get('WD_PAID','0'));due=money(fee)-paid
                if due<0:raise ValueError('The configured withdrawal fee is below payments already recorded. Review the case instead.')
                set_fields({'WITHDRAWAL':fee,'WD_DUE':format(due,'.2f')})
            ttk.Button(bar,text='Recalculate due date (business days)',command=lambda:self.safe(recalc)).pack(side='left')
            ttk.Button(bar,text='Apply configured withdrawal fee',command=lambda:self.safe(withdrawal)).pack(side='left',padx=8)
        ttk.Button(win,text='Save audited correction (Administrator)',command=commit).pack(pady=8)
    def history(self):
        if self.table.get()!='WC_CASE':raise ValueError('Select a case in WC_CASE first.')
        case_record=self.selected()
        case=json.loads(get(self.db,'WC_CASE',case_record)['data_json']);number=str(case.get('CASE_NO',''))
        user_audit.opened(self.db,'PAYMENT_HISTORY',user_audit.case_ref(number,case_record))
        self.table.set('PAYMENTS');self.query.set('');self.offset=0
        self.refresh()
        # Dedicated exact-case list: all rows including deleted, without assuming a unique identity.
        win=tk.Toplevel(self.win);win.title('Exact payment rows for case '+number);win.geometry('1050x600')
        ttk.Label(win,text='Explicit source-row links take priority. Unlinked rows use CASE_NO and may be ambiguous for duplicates. Deleted rows are included.',wraplength=1000).pack(pady=8)
        tree=ttk.Treeview(win,columns=('row','deleted','date','receipt','rest','fee','da','wd'),show='headings')
        for col in tree['columns']:tree.heading(col,text=col);tree.column(col,width=120)
        tree.pack(fill='both',expand=True)
        for r in self.db.execute("SELECT p.* FROM working_legacy p LEFT JOIN legacy_payment_links l ON l.payment_record=p.record_no WHERE p.table_name='PAYMENTS' AND (l.case_record=? OR (l.payment_record IS NULL AND json_extract(p.data_json,'$.CASE_NO')=?)) ORDER BY p.record_no",(case_record,number)):
            d=json.loads(r['data_json'])
            d['DATE'] = payment_date_display(d.get('DATE',''))
            tree.insert('','end',iid=str(r['record_no']),values=[r['record_no'],r['deleted']]+[d.get(k,'') for k in ('DATE','RECEIPT_NO','REST_PAID','SFEE_PAID','FO_PAID','WD_PAID')])
        def open_row(e=None):
            if tree.selection():
                self.query.set('');self.offset=0;self.refresh()
                n=int(tree.selection()[0]);self.offset=((n-1)//150)*150
                # Details reads selected source row, regardless of current page.
                self.tree.delete(*self.tree.get_children());self.tree.insert('','end',iid=str(n));self.tree.selection_set(str(n));self.details()
        tree.bind('<Double-1>',open_row)
        ttk.Button(win,text='View / correct selected payment',command=lambda:self.safe(open_row)).pack(pady=8)
        def print_row():
            if not tree.selection():raise ValueError('Select a payment row first.')
            n=int(tree.selection()[0]);self.table.set('PAYMENTS');self.tree.delete(*self.tree.get_children());self.tree.insert('','end',iid=str(n));self.tree.selection_set(str(n));self.print_payment()
        ttk.Button(win,text='Print selected payment record',command=lambda:self.safe(print_row)).pack(pady=8)
    def payment(self,prefill=None):
        if self.table.get()!='WC_CASE':raise ValueError('Select a WC_CASE record first.')
        n=self.selected();row=get(self.db,'WC_CASE',n);d=json.loads(row['data_json'])
        balances = [money(d.get(field,'')) for field in PAYMENT_DUE_FIELDS]
        remaining = sum(balances)
        user_audit.opened(self.db,'PAYMENT_ENTRY',user_audit.case_ref(d.get('CASE_NO',''),n))
        output_mode = document_mode.for_store(self.app.store)
        payment_label = {'official':'payment', 'official-rehearsal':'rehearsal payment'}.get(output_mode,'test payment')
        win=tk.Toplevel(self.win);win.title(f'Record {payment_label} - '+str(d.get('CASE_NO','')));win.geometry('570x480')
        values={}
        today = dt.datetime.now(user_audit.CENTRAL).date()
        labels=[('date','Date (MM-DD-YYYY)',today.strftime('%m-%d-%Y')),('receipt','Receipt #','Assigned when posted'),('method','Method: Cash / Money order / Other','Cash')]
        allocation_fields = ('REST_PAID','SFEE_PAID','FO_PAID','WD_PAID')
        labels += [(field,f'{category} (due ${due:,.2f})','0.00')
                   for field, category, due in zip(allocation_fields,PAYMENT_BALANCE_LABELS,balances)]
        for i,(key,label,value) in enumerate(labels):
            if key == 'receipt':
                ttk.Label(win,text=label).grid(row=i,column=0,padx=10,pady=9,sticky='w')
                ttk.Label(win,text=value).grid(row=i,column=1,sticky='w')
                continue
            ttk.Label(win,text=label).grid(row=i,column=0,padx=10,pady=9,sticky='w');entry=ttk.Entry(win,width=25);entry.insert(0,value);entry.grid(row=i,column=1);values[key]=entry
            if prefill and key in prefill:entry.delete(0,'end');entry.insert(0,prefill[key])
        ttk.Label(win,text=f'Remaining before payment: ${remaining:,.2f}').grid(row=7,column=0,columnspan=2,pady=8)
        preview = payment_balance_preview(win,[values[key] for key in allocation_fields],
                                          balances,money,lambda value:f'${value:,.2f}')
        preview.grid(row=8,column=0,columnspan=3,pady=8)
        def commit():
            def do():
                date = payment_date_from_form(values['date'].get())
                p = post_payment(self.db,n,row['revision'],date,None,values['method'].get(),
                                 [values[k].get() for k in allocation_fields],output_mode=output_mode)
                win.destroy()
                self.refresh()
                self.receipt(p)
            self.safe(do)
        ttk.Button(win,text=f'Post {payment_label} and open receipt',command=commit).grid(row=9,column=0,columnspan=2,pady=12)
    def receipt(self,n,*,reprint=False):
        row=self.db.execute('SELECT * FROM legacy_test_payments WHERE payment_record=?',(n,)).fetchone()
        if row is None:
            raise ValueError('The posted receipt could not be found.')
        user_audit.opened(self.db,'RECEIPT_PREVIEW',f'Payment row {n}')
        folder=self.app.store.path.parent/'test-receipts';folder.mkdir(exist_ok=True)
        path=folder/(row['id']+'.html')
        path.write_text(receipt_html([posted_receipt_text(self.db,row,reprint=reprint)], auto_print=False),encoding='utf-8')
        webbrowser.open(path.resolve().as_uri())
    def print_payment(self):
        if self.table.get()!='PAYMENTS':raise ValueError('Select a PAYMENTS record first.')
        n=self.selected();row=get(self.db,'PAYMENTS',n);d=json.loads(row['data_json'])
        mode = document_mode.for_store(self.app.store)
        if not row['deleted'] and mode != document_mode.TEST:
            saved = self.db.execute('SELECT party_json FROM legacy_test_payments WHERE payment_record=?',(n,)).fetchone()
            if saved and json.loads(saved[0]).get('_document_mode') == mode:
                return self.receipt(n,reprint=True)
        user_audit.opened(self.db,'RECEIPT_PREVIEW',f'Payment row {n}')
        d['DATE'] = payment_date_display(d.get('DATE',''))
        d.update(payment_receipt_balance(self.db,n,d))
        body='\n'.join(k+': '+str(v) for k,v in d.items())
        folder=self.app.store.path.parent/'test-receipts';folder.mkdir(exist_ok=True)
        path=folder/('history-'+str(n)+'.html')
        document = (f"{users.document_heading(self.db)}\n\nTEST COPY OF PAYMENT RECORD\n"
                    f"Source row {n}; deleted marker: {row['deleted']}\n\n{body}")
        path.write_text(receipt_html([document], auto_print=False),encoding='utf-8')
        webbrowser.open(path.resolve().as_uri())

    def reconcile_payment(self):
        payment=self.selected() if self.table.get()=='PAYMENTS' and self.tree.selection() else None
        legacy_reconcile.Screen(self,payment)

    def report(self):
        result=reconciliation(self.db);win=tk.Toplevel(self.win);win.title('Legacy reconciliation');text=tk.Text(win,width=90,height=32);text.pack(fill='both',expand=True);text.insert('end',json.dumps(result,indent=2));text.configure(state='disabled')


def open_workspace(app):
    try:
        if not app.store.db.execute("SELECT 1 FROM legacy_work_meta WHERE key='initialized'").fetchone():
            login.require(app.store.db,True)
            division_key = getattr(app.store, 'division', None)
            division = divisions.LABELS.get(division_key)
            destination = app.store.path.resolve()
            path = None
            if app.store.db.execute("SELECT 1 FROM sqlite_master WHERE name='legacy_records'").fetchone():
                source = f'{destination}\n(Original records already stored in this database)'
                owner = source_division(app.store.db)
            else:
                selected = filedialog.askopenfilename(
                    parent=app.root,
                    title='Choose imported SQLite database'+(' for '+division if division else ''),
                    filetypes=[('Imported SQLite','*.sqlite *.db')])
                if not selected:
                    return
                path = Path(selected).resolve()
                if path == destination:
                    raise ValueError('Choose the separate imported database.')
                source = str(path)
                from contextlib import closing
                try:
                    with closing(sqlite3.connect(path.as_uri()+'?mode=ro', uri=True)) as imported:
                        owner = source_division(imported)
                except sqlite3.OperationalError as error:
                    raise ValueError('Could not read the legacy office information. Select an imported legacy SQLite database.') from error
            details = (f'Source database\n{source}\n'
                       f'Source division: {divisions.LABELS.get(owner, "Unverified")}\n\n'
                       f'Destination workspace\n{division or "Local evaluation workspace"}\n{destination}')
            if owner and division and owner != division_key:
                messagebox.showwarning('Division mismatch',
                    details+'\n\nThis file belongs to a different division. The load was canceled.',
                    parent=app.root)
                return
            if not owner:
                details += '\n\nThe legacy office information could not verify the source division. Continue only if you have verified the file separately.'
            if not messagebox.askyesno(
                'Load complete legacy workspace',
                details+'\n\nLoad these records for editable testing? A full backup is made first. '
                'Authorized users of the destination share the working copy.',
                default=messagebox.NO, parent=app.root):
                return
            app.root.config(cursor='watch');app.root.update_idletasks()
            initialize(app.store,path,confirmed_division=owner)
        return Workspace(app)
    except Exception as e:messagebox.showerror('Legacy workspace',str(e),parent=app.root)
    finally:app.root.config(cursor='')
