import date_format
"""Prototype reports, editable text wrappers, labels and month-end snapshots."""
import calendar
import datetime as dt
from decimal import Decimal
import hashlib
import html
import json
from pathlib import Path
import sqlite3
import string
import uuid
import webbrowser
import math
import login

TITLES={'cases':'Case Listing','case':'Case Detail','daily':'Daily Payment Register','analysis':'Check Analysis','monthly':'Monthly Activity','defendants':'Defendant Listing'}
DEFAULT_WRAPPER='{office_heading}\n{office_contact}\n\n{report_title}\n{period}\nGenerated: {generated}\n\n{body}\n\n{footer}'
DEFAULT_LABEL='{name}\n{address}\n{address2}\n{city}, {state} {zip}'
DEFAULT_LAYOUT={'columns':3,'rows':10,'width':2.625,'height':1.0,'left':0.1875,'top':0.5,'gap':0.125,'font':10}
PAY_KEYS=('restitution','merchant_fee','da_fee','withdrawal_fee','overpayment')
PAY_LABELS=('Restitution','Merchant fee','DA / warrant fee','Withdrawal fee','Overpayment')


def setup(db):
    db.executescript('''CREATE TABLE IF NOT EXISTS print_settings(key TEXT PRIMARY KEY,value TEXT NOT NULL);
      CREATE TABLE IF NOT EXISTS period_snapshots(id INTEGER PRIMARY KEY AUTOINCREMENT,month TEXT NOT NULL,
        closed_at TEXT NOT NULL,closed_by TEXT NOT NULL,snapshot_json TEXT NOT NULL,sha256 TEXT NOT NULL);
      CREATE TABLE IF NOT EXISTS accounting_periods(month TEXT PRIMARY KEY,closed INTEGER NOT NULL DEFAULT 0,snapshot_id INTEGER REFERENCES period_snapshots(id));
      CREATE TABLE IF NOT EXISTS period_events(id INTEGER PRIMARY KEY,month TEXT NOT NULL,at TEXT NOT NULL,
        actor TEXT NOT NULL,action TEXT NOT NULL,reason TEXT NOT NULL);''')
    if 'party_snapshot' not in [r[1] for r in db.execute('PRAGMA table_info(payments)')]:
        db.execute('ALTER TABLE payments ADD COLUMN party_snapshot TEXT')
    if 'revision' not in [r[1] for r in db.execute('PRAGMA table_info(cases)')]:
        db.execute('ALTER TABLE cases ADD COLUMN revision INTEGER NOT NULL DEFAULT 0')
    for row in db.execute('''SELECT p.id,c.case_no,c.defendant,c.merchant,c.check_no FROM payments p JOIN cases c ON c.id=p.case_id WHERE p.party_snapshot IS NULL''').fetchall():
        db.execute('UPDATE payments SET party_snapshot=? WHERE id=?',(json.dumps({k:row[k] for k in ('case_no','defendant','merchant','check_no')}),row['id']))
    db.commit()


def money(value):
    return '$'+format(Decimal(value)/100,',.2f')


def date_range(start,end):
    first,last=date_format.parse(start),date_format.parse(end)
    if first>last:
        raise ValueError('Start date must not follow end date.')
    return first.isoformat(),last.isoformat()


def month_range(month):
    first=dt.date.fromisoformat(month+'-01')
    return first.isoformat(),first.replace(day=calendar.monthrange(first.year,first.month)[1]).isoformat()


def assert_open(db,date):
    date=dt.date.fromisoformat(date).isoformat()
    row=db.execute('SELECT closed FROM accounting_periods WHERE month=?',(date[:7],)).fetchone()
    if row and row[0]:
        raise ValueError('This accounting month is closed. An Administrator must reopen it before changing dated transactions.')


def get_setting(db,key,default):
    row=db.execute('SELECT value FROM print_settings WHERE key=?',(key,)).fetchone()
    return row[0] if row else default


def validate_template(template,allowed):
    if len(template)>20000:
        raise ValueError('Template is too long.')
    for _,field,spec,conversion in string.Formatter().parse(template):
        if field is not None and (field not in allowed or spec or conversion):
            raise ValueError('Use only these plain placeholders: '+', '.join('{'+k+'}' for k in sorted(allowed)))


def save_report_settings(db,kind,title,wrapper,footer):
    actor=login.require(db,True)
    if kind not in TITLES or not title.strip():
        raise ValueError('Choose a report and enter its title.')
    allowed={'office_heading','office_contact','report_title','period','generated','body','footer'}
    validate_template(wrapper,allowed)
    if '{body}' not in wrapper:
        raise ValueError('The report template must include {body}.')
    with db:
        for key,value in [('title:'+kind,title.strip()),('wrapper:'+kind,wrapper),('footer:'+kind,footer)]:
            db.execute('INSERT INTO print_settings VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value',(key,value))
        audit(db,actor,'MODIFY_REPORT',kind)


def audit(db,actor,action,reference):
    db.execute('INSERT INTO audit(at,operator,action,reference) VALUES(?,?,?,?)',
        (dt.datetime.now(dt.timezone.utc).isoformat(),actor,action,str(reference)))


def report_body(store,kind,start,end,case_id=None):
    start,end=date_range(start,end)
    db=store.db
    if kind=='daily':
        rows=db.execute('''SELECT p.*,c.case_no FROM payments p JOIN cases c ON c.id=p.case_id
          WHERE p.voided=0 AND p.paid_date BETWEEN ? AND ? ORDER BY paid_date,p.id''',(start,end)).fetchall()
        totals=[sum(r[k] for r in rows) for k in PAY_KEYS]
        lines=['Totals for active payments by payment date (voids excluded):',
               *[f'{label}: {money(value)}' for label,value in zip(PAY_LABELS,totals)],
               'TOTAL RECEIVED: '+money(sum(totals)),f'Payment count: {len(rows)}','']
        for r in rows:
            lines.extend([f'{date_format.display(r["paid_date"])} | {r["receipt_code"]} | Case {r["case_no"]} | {r["operator"]} | {r["method"]}',
                '  '+'; '.join(f'{label}: {money(r[k])}' for label,k in zip(PAY_LABELS,PAY_KEYS))])
        return '\n'.join(lines)
    if kind=='case':
        case=store.case(case_id)
        balances=store.balance(case_id)
        lines=[f'Case: {case["case_no"]}',f'Defendant: {case["defendant"]}',f'Merchant: {case["merchant"]}',
            f'Check: {case["check_no"]}',f'Entered: {date_format.display(case["entered"])}',f'Due: {date_format.display(case["due_date"])}',
            f'Archived: {bool(case["archived"])}','',
            *[f'{label} balance: {money(value)}' for label,value in zip(PAY_LABELS,balances)],
            'Total current balance: '+money(sum(balances)),'','PAYMENT HISTORY (all dates)']
        for p in db.execute('SELECT * FROM payments WHERE case_id=? ORDER BY id',(case_id,)):
            lines.append(f'{p["receipt_code"]} | {date_format.display(p["paid_date"])} | {money(sum(p[k] for k in PAY_KEYS))}'+(' | VOID' if p['voided'] else ''))
        lines.extend(['','CHARGE ADJUSTMENTS (all dates)'])
        for a in db.execute('SELECT * FROM adjustments WHERE case_id=? ORDER BY id',(case_id,)):
            lines.append(f'{a["number"]} | {a["at"]} | {money(sum(a[k] for k in PAY_KEYS[:4]))} | {a["reason"]}')
        return '\n'.join(lines)
    if kind=='defendants':
        lines=[]
        for r in db.execute('SELECT * FROM defendants ORDER BY name,id'):
            p=json.loads(r['profile'])
            lines.extend([f'ID {r["id"]}: {r["name"]}',p.get('ADDRESS',''),p.get('ADDRESS2',''),
                ' '.join(p.get(k,'') for k in ('CITY','STATE','ZIP')),p.get('TELEPHONE',''),''])
        return '\n'.join(lines) or 'No defendant profiles recorded.'
    cases=db.execute('SELECT * FROM cases WHERE archived=0 AND entered BETWEEN ? AND ? ORDER BY entered,case_no',(start,end)).fetchall()
    if kind=='cases':
        return '\n'.join([f'Cases entered in range: {len(cases)}','Balances below are current, not historical balances.','',
            *[f'{r["case_no"]} | {r["entered"]}\n  {r["defendant"]} | {r["merchant"]}\n  Current balance: {money(sum(store.balance(r["id"])))}' for r in cases]])
    if kind=='analysis':
        total_charges=sum(sum(r[k] for k in PAY_KEYS[:4]) for r in cases)
        balance=sum(sum(store.balance(r['id'])) for r in cases)
        zero=sum(sum(store.balance(r['id']))==0 for r in cases)
        groups={}
        for r in cases:
            groups[r['merchant']]=groups.get(r['merchant'],0)+sum(store.balance(r['id']))
        return '\n'.join([f'Active cases entered in range: {len(cases)}',f'Original check amounts: {money(sum(r["restitution"] for r in cases))}',
            f'Original charges including fees: {money(total_charges)}',f'Current balance including adjustments: {money(balance)}',
            f'Cases with zero current balance: {zero}',f'Cases with outstanding balance: {len(cases)-zero}',
            'Zero balance is an accounting observation, not a legal disposition.','','CURRENT BALANCE BY MERCHANT',
            *[f'{name}: {money(value)}' for name,value in sorted(groups.items())]])
    if kind=='monthly':
        new=db.execute('SELECT COUNT(*),COALESCE(SUM(restitution),0) FROM cases WHERE entered BETWEEN ? AND ?',(start,end)).fetchone()
        adjustments=db.execute('SELECT COUNT(*) FROM adjustments WHERE substr(at,1,10) BETWEEN ? AND ?',(start,end)).fetchone()[0]
        voids=db.execute('SELECT COUNT(*) FROM payments WHERE voided=1 AND paid_date BETWEEN ? AND ?',(start,end)).fetchone()[0]
        return '\n'.join([f'Cases entered (including later archives): {new[0]}',f'Original check amount entered: {money(new[1])}',
            f'Charge adjustment rows created (UTC date): {adjustments}',f'Voided payments dated in range: {voids}','',
            report_body(store,'daily',start,end)])
    raise ValueError('Unknown report.')


def build_report(store,kind,start,end,case_id=None):
    import users
    if kind not in TITLES:
        raise ValueError('Choose a report.')
    start,end=date_range(start,end)
    context={'office_heading':users.document_heading(store.db),'office_contact':users.document_contact(store.db),
        'report_title':get_setting(store.db,'title:'+kind,TITLES[kind]),'period':f'Dates: {date_format.display(start)} through {date_format.display(end)}',
        'generated':date_format.timestamp(dt.datetime.now().isoformat(timespec='seconds')),
        'body':report_body(store,kind,start,end,case_id),'footer':get_setting(store.db,'footer:'+kind,'')}
    wrapper=get_setting(store.db,'wrapper:'+kind,DEFAULT_WRAPPER)
    validate_template(wrapper,set(context))
    return 'DEMONSTRATION REPORT - REVIEW PROTOTYPE\n\n'+wrapper.format_map(context)


def edit_case(store,case_id,data,charges,reason,expected_revision=None):
    actor=login.require(store.db)
    allowed={'defendant','merchant','check_no','entered','due_date','bank_id','defendant_id'}
    if set(data)-allowed or not reason.strip():
        raise ValueError('Enter a reason for the case edit.')
    old=store.case(case_id)
    if old['archived']:
        raise ValueError('Restore the case before editing it.')
    if any(not str(data.get(k,old[k])).strip() for k in ('defendant','merchant','check_no')):
        raise ValueError('Defendant, merchant and check number are required.')
    for key in ('entered','due_date'):
        if data.get(key):
            data[key] = date_format.parse(data[key]).isoformat()
    if len(charges)!=4 or any(type(n)is not int or n<0 for n in charges):
        raise ValueError('Enter nonnegative charges in cents.')
    db=store.db
    try:
        db.execute('BEGIN IMMEDIATE')
        old=store.case(case_id)
        if old['archived']:
            raise ValueError('Restore the case before editing it.')
        if expected_revision is not None and old['revision']!=expected_revision:
            raise ValueError('Another user changed this case. Close and reopen the case editor before saving.')
        assert_open(db,old['entered'])
        assert_open(db,data.get('entered',old['entered']))
        changed=any(old[k]!=charges[i] for i,k in enumerate(PAY_KEYS[:4]))
        if changed and (db.execute('SELECT 1 FROM payments WHERE case_id=?',(case_id,)).fetchone() or db.execute('SELECT 1 FROM adjustments WHERE case_id=?',(case_id,)).fetchone()):
            raise ValueError('This case has financial history. Use an adjustment to change its charges.')
        for key,table in [('bank_id','bank_codes'),('defendant_id','defendants')]:
            if data.get(key) is not None and key in data and not db.execute('SELECT 1 FROM '+table+' WHERE id=?',(data[key],)).fetchone():
                raise ValueError('Linked profile or bank entry not found.')
        if data.get('bank_id') is not None and data['bank_id']!=old['bank_id'] and not db.execute('SELECT 1 FROM bank_codes WHERE id=? AND active=1',(data['bank_id'],)).fetchone():
            raise ValueError('Choose an active bank entry.')
        values={**data,**dict(zip(PAY_KEYS[:4],charges))}
        before={key:old[key] for key in values}
        db.execute('UPDATE cases SET '+','.join(k+'=?' for k in values)+',revision=revision+1 WHERE id=?',list(values.values())+[case_id])
        audit(db,actor,'EDIT_CASE',json.dumps({'case_id':case_id,'reason':reason,'before':before,'after':values}))
        db.commit()
    except Exception:
        db.rollback()
        raise


def close_month(store,month):
    actor=login.require(store.db,True)
    start,end=month_range(month)
    import database_tools
    backup=database_tools.backup(store)
    db=store.db
    try:
        db.execute('BEGIN IMMEDIATE')
        assert_open(db,start)
        payments=[dict(r) for r in db.execute('SELECT * FROM payments WHERE paid_date BETWEEN ? AND ? ORDER BY id',(start,end))]
        cases=[dict(r) for r in db.execute('SELECT * FROM cases WHERE entered BETWEEN ? AND ? ORDER BY id',(start,end))]
        adjustments=[dict(r) for r in db.execute('SELECT * FROM adjustments WHERE substr(at,1,10) BETWEEN ? AND ? ORDER BY id',(start,end))]
        snapshot={'month':month,'payments':payments,'cases_entered':cases,'adjustments_created_utc':adjustments,
            'report':build_report(store,'monthly',start,end),
            'scope':'Prototype payment-date register snapshot; no fund distribution or accounting certification.'}
        content=json.dumps(snapshot,sort_keys=True)
        digest=hashlib.sha256(content.encode('utf-8')).hexdigest()
        at=dt.datetime.now(dt.timezone.utc).isoformat()
        sid=db.execute('INSERT INTO period_snapshots(month,closed_at,closed_by,snapshot_json,sha256) VALUES(?,?,?,?,?)',(month,at,actor,content,digest)).lastrowid
        db.execute('INSERT INTO accounting_periods VALUES(?,1,?) ON CONFLICT(month) DO UPDATE SET closed=1,snapshot_id=excluded.snapshot_id',(month,sid))
        db.execute('INSERT INTO period_events(month,at,actor,action,reason) VALUES(?,?,?,?,?)',(month,at,actor,'CLOSE','Prototype snapshot'))
        audit(db,actor,'CLOSE_PROTOTYPE_MONTH',str(sid))
        db.commit()
        return sid,backup
    except Exception:
        db.rollback()
        raise


def reopen_month(db,month,reason):
    actor=login.require(db,True)
    month_range(month)
    if not reason.strip():
        raise ValueError('A reason is required to reopen a month.')
    with db:
        if db.execute('UPDATE accounting_periods SET closed=0 WHERE month=? AND closed=1',(month,)).rowcount!=1:
            raise ValueError('That month is not closed.')
        db.execute('INSERT INTO period_events(month,at,actor,action,reason) VALUES(?,?,?,?,?)',(month,dt.datetime.now(dt.timezone.utc).isoformat(),actor,'REOPEN',reason.strip()))
        audit(db,actor,'REOPEN_PROTOTYPE_MONTH',month+': '+reason.strip())


def validate_layout(layout):
    layout={k:float(layout[k]) for k in DEFAULT_LAYOUT}
    if not all(math.isfinite(value) for value in layout.values()):
        raise ValueError('Label dimensions must be finite numbers.')
    if layout['columns']!=int(layout['columns']) or layout['rows']!=int(layout['rows']) or not 1<=layout['columns']<=4 or not 1<=layout['rows']<=20:
        raise ValueError('Choose 1-4 columns and 1-20 rows.')
    if not 6<=layout['font']<=20 or any(layout[k]<0 for k in ('left','top','gap')) or layout['width']<=0 or layout['height']<=0:
        raise ValueError('Enter positive label dimensions, nonnegative margins, and font size 6-20.')
    if 2*layout['left']+layout['columns']*layout['width']+(layout['columns']-1)*layout['gap']>8.501 or 2*layout['top']+layout['rows']*layout['height']>11.001:
        raise ValueError('This label layout does not fit letter-size paper.')
    return layout


def save_label_settings(db,template,layout):
    actor=login.require(db,True)
    validate_template(template,{'name','address','address2','city','state','zip'})
    layout=validate_layout(layout)
    with db:
        for key,value in [('label_template',template),('label_layout',json.dumps(layout))]:
            db.execute('INSERT INTO print_settings VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value',(key,value))
        audit(db,actor,'MODIFY_LABEL_LAYOUT','letter')


def label_documents(db,selected_id=None):
    template=get_setting(db,'label_template',DEFAULT_LABEL)
    validate_template(template,{'name','address','address2','city','state','zip'})
    sql='SELECT * FROM defendants'+(' WHERE id=?' if selected_id is not None else '')+' ORDER BY name,id'
    rows=db.execute(sql,(selected_id,) if selected_id is not None else ()).fetchall()
    labels=[]
    skipped=0
    for row in rows:
        p=json.loads(row['profile'])
        if not p.get('NAME','').strip() or not p.get('ADDRESS','').strip():
            skipped+=1
            continue
        values={k:p.get(k.upper(),'') for k in ('name','address','address2','city','state','zip')}
        text=template.format_map(values)
        labels.append('\n'.join(line for line in text.splitlines() if line.strip()))
    return labels,skipped


def labels_html(labels,layout):
    if not labels:
        raise ValueError('No defendants with a name and postal address are available.')
    # Validate numeric layout even when settings were loaded from disk.
    layout=validate_layout(layout)
    per_page=int(layout['columns'])*int(layout['rows'])
    if per_page<1:
        raise ValueError('Invalid label layout.')
    pages=[]
    for start in range(0,len(labels),per_page):
        cells=''.join('<div class="label">'+html.escape(text).replace('\n','<br>')+'</div>' for text in labels[start:start+per_page])
        pages.append('<section class="sheet">'+cells+'</section>')
    return '''<!doctype html><html lang="en"><head><meta charset="utf-8"><title>Defendant address labels</title><style>
@page {size:letter portrait;margin:0;} *{box-sizing:border-box;} body{margin:0;font-family:Arial,sans-serif;}
.toolbar{padding:15px;background:#eee;} .label{padding:0.08in 0.12in;overflow:hidden;overflow-wrap:anywhere;}
.sheet{width:8.5in;height:11in;display:grid;align-content:start;justify-content:start;break-after:page;
'''+f'padding:{layout["top"]}in {layout["left"]}in;grid-template-columns:repeat({int(layout["columns"])},{layout["width"]}in);grid-auto-rows:{layout["height"]}in;column-gap:{layout["gap"]}in;font-size:{layout["font"]}pt;'+'''}
.sheet:last-child{break-after:auto;} @media print{.toolbar{display:none;}}</style></head><body>
<div class="toolbar"><button onclick="window.print()">Print labels</button> Letter, portrait, actual size / 100%. Turn off headers and footers. Test alignment on plain paper first.</div>
'''+''.join(pages)+'''<script>window.addEventListener('load',()=>window.print());</script></body></html>'''


def open_labels(db,folder,selected_id=None):
    labels,skipped=label_documents(db,selected_id)
    layout=json.loads(get_setting(db,'label_layout',json.dumps(DEFAULT_LAYOUT)))
    content=labels_html(labels,layout)
    folder=Path(folder)
    folder.mkdir(parents=True,exist_ok=True)
    path=folder/('labels-'+uuid.uuid4().hex+'.html')
    path.write_text(content,encoding='utf-8')
    if not webbrowser.open(path.resolve().as_uri()):
        raise OSError('Could not open label preview: '+str(path))
    return len(labels),skipped,path
