import date_format
import original_print
import divisions
import users
"""Legacy Functions reports, frozen test batches, draft checks and print templates."""

import calendar

import datetime as dt

from decimal import Decimal

import hashlib

import html

import json

from pathlib import Path

import re

import sqlite3

import string

import uuid

import webbrowser

import tkinter as tk

from tkinter import ttk, messagebox, simpledialog, filedialog

import login
import user_audit

import legacy_work as lw

PAY_FIELDS=('REST_PAID','SFEE_PAID','FO_PAID','WD_PAID','CC_PAID','COURT_REST','OVERPAID')

CASE_COLUMNS=('CASE_NO','DEF_ID','DEFENDANT','MERCH_ID','MERCHANT','CK_NO','CK_DATE','CK_AMT','FIRST_OFF','MERCH_FEE','CK_DUE','FEE_DUE','DA_DUE','WD_DUE')

PAY_COLUMNS=('CASE_NO','DATE','RECEIPT_NO','DEFENDANT','MERCHANT',*PAY_FIELDS)

SPEC={
 'final':('Final Draft Check Register','DRAFT_CHECK',('check_no','check_date','payee','category','amount'),'check_date'),

 'proof':('Worthless Check Entry Proof','WC_CASE',CASE_COLUMNS,'ENTER_DATE'),

 'letter1':('Letter to Defendant','WC_CASE',CASE_COLUMNS,'ENTER_DATE'),

 'letter2':('Second Letters','WC_CASE',CASE_COLUMNS,'ENTER_DATE'),

 'letter3':('Final Letters','WC_CASE',CASE_COLUMNS,'ENTER_DATE'),

 'surrender':('Surrender List','WC_CASE',('DUE_DATE',*CASE_COLUMNS),'DUE_DATE'),

 'visit':('Investigator Visit List','WC_CASE',('CITY','STATE','ADDRESS',*CASE_COLUMNS),'ENTER_DATE'),

 'warrant':('Active Warrant List','WC_CASE',('ACT_WARR','WARR_CODE','WARR_LOC',*CASE_COLUMNS),'ENTER_DATE'),

 'merchant_history':('Merchant History','WC_CASE',CASE_COLUMNS,'ENTER_DATE'),

 'defendant_history':('Defendant History','WC_CASE',CASE_COLUMNS,'ENTER_DATE'),

 'notes':('Defendant Notes','WC_DEF',('ID','NAME','ADDRESS','CITY','STATE','HISTORY'),None),

 'merchants':('Merchant Listing','WC_MERCH',('ME_ID','ME_NAME','ME_ADDR','ME_CITY','ME_STATE','ME_ZIP','ME_PHONE','ME_CONTACT'),None),

 'defendants':('Defendant Listing','WC_DEF',('ID','NAME','ADDRESS','CITY','STATE','ZIP','DOB','TELEPHONE','EMPLOYER','EMP_PHONE'),None),

 'recalls':('Marked Recalls','WC_CASE',('RECALLED',*CASE_COLUMNS),'ENTER_DATE'),

 'postal':('Postal Verification','WC_CASE',CASE_COLUMNS,'ENTER_DATE'),

 'restitution_agreement':('Restitution Agreement','WC_CASE',CASE_COLUMNS,'ENTER_DATE'),

 'restitution_form':('Restitution Form','WC_CASE',CASE_COLUMNS,'ENTER_DATE'),

 'forgery':('Forgery Affidavit','WC_CASE',CASE_COLUMNS,'ENTER_DATE'),

 'complaint':('Complaint','WC_CASE',CASE_COLUMNS,'ENTER_DATE'),

 'receipts':('Daily Receipt List','PAYMENTS',PAY_COLUMNS,'DATE'),

 'detailed':('Detailed Check Register Review','PAYMENTS',PAY_COLUMNS,'DATE'),

 'analysis':('Check Analysis / Payments','PAYMENTS',PAY_COLUMNS,'DATE'),

 'monthly':('Monthly Activity','PAYMENTS',PAY_COLUMNS,'DATE'),

 'deposits':('Deposit Register','DEPOSIT',('DEP_DATE','DEP_AMT','PROOF_AMT','BALANCED'),'DEP_DATE'),

 'labels':('Defendant Labels','WC_CASE',CASE_COLUMNS,'ENTER_DATE'),

 'folder_labels':('Folder Labels','WC_CASE',CASE_COLUMNS,'ENTER_DATE'),

}

FORMS={'letter1':'DEF_LTR1.FRX','letter2':'SEC_LTR.FRX','letter3':'DEF_LTR3.FRX','postal':'POSTMAN.FRX',

       'restitution_agreement':'REST_WC.FRX','restitution_form':'AGR_REST.FRX','forgery':'FORGERY.FRX','complaint':'COMPLT.FRX'}

POST_FIELDS={'proof':{'PROOF':'T'},'letter1':{'LTR_SENT':'@DATE'},'letter2':{'LTR_SENT2':'@DATE'},'letter3':{'LTR_SENT3':'@DATE'}}

MENU=[('Edit Case','case.edit'),('Add New Case','case.new'),('Print Reports',[

 ('Worthless Check Entry Proof',[('Create/Print New Entry Proof List','proof.create'),('Post New Entries','proof.post'),('View Current List','proof.view'),('Re-Print Current List','proof.reprint')]),

 ('Letter to Defendant','letter1.single'),('Batch Print of Defendant Letters',[

 ('All Unprinted Letters','letter1.create'),('Letters by Merchant','letter1.merchant'),('View Last List of Letters','letter1.view'),('Post Defendant Letters','letter1.post'),('Reprint Labels','labels.letter1')]),

 ('Defendant Labels by Enter Date','labels.create'),('Print Second & Final Letters',[

 ('Print 2nd Letters','letter2.create'),('View Last List Created','letter2.view'),('Print Single Second to Defendant','letter2.single'),('Post 2nd Letters','letter2.post'),('Reprint Labels (2nd)','labels.letter2'),('Print Final Letters','letter3.create'),('Post Final Letters','letter3.post'),('Reprint Labels (Final)','labels.letter3')]),

 ('Surrender List','surrender.create'),('Investigator Visit List',[('Defendant Order','visit.create'),('Ordered by City & State','visit.city'),('Reprint Visit List','visit.reprint')]),

 ('Active Warrant List','warrant.create'),('Merchant History','merchant_history.create'),('Defendant History','defendant_history.create'),('Defendant Notes','notes.create'),('Merchant Listing','merchants.create'),('Defendant Listing','defendants.create'),

 ('Print Marked Recalls','recalls.create'),('Postal Verification','postal.single'),('Restitution Agreement','restitution_agreement.single'),('Restitution Form','restitution_form.single'),('Forgery Affidavit','forgery.single'),('Complaint','complaint.single')]),

 ('Modify Reports',[('Original layouts / Letter printing','layouts.configure'),('Edited text templates','templates.edit')]),('Daily Register Reports',[

 ('Print Receipt List','receipts.create'),('Post Receipts for Deposit','receipts.post'),('View Last Receipt List','receipts.view'),('Re-Print Receipt','receipt.single'),('Print Receipts by Date Range','receipts.range')]),

 ('Month-End Process',[

 ('Create/Print Detailed Check Register','detailed.create'),('View/Edit Detailed Check Register Data','data.REGISTER'),('Re-Print Detailed Register','detailed.reprint'),

 ('Print Merchant Checks','checks.merchant'),('Print DA/Commission Checks','checks.fund'),('Re-Print Checks','checks.reprint'),('Print Final Check Register','final.create'),('View/Edit Final Check Register','checks.edit'),

 ('Print 1 Check (single Def.)','checks.single'),('Print 1 Check (all Def.)','checks.defendant'),('Append New Check to Register','checks.append'),('Post Check Registers','final.post'),

 ('Print Deposit Register','deposits.create'),('View Deposit Register','data.DEPOSIT'),('Print Daily Activity/Monthly Totals','monthly.create'),('Edit DA/Commission Fund File','data.FUNDS')]),

 ('Check Analysis Report',[('Year','analysis.year'),('Current Month','analysis.month'),('Payments by Date Range','analysis.range')]),

 ('Monthly Activity Report','monthly.create'),('Print Defendant Labels','labels.create'),('Modify Labels',[('Folder Labels','templates.folder_labels'),('Any Label','templates.labels')])]

def setup(db):

    db.executescript('''CREATE TABLE IF NOT EXISTS legacy_function_batches(

      id INTEGER PRIMARY KEY,kind TEXT NOT NULL,created_at TEXT NOT NULL,actor TEXT NOT NULL,

      start_date TEXT,end_date TEXT,payload_json TEXT NOT NULL,sha256 TEXT NOT NULL,status TEXT NOT NULL DEFAULT 'draft',posted_at TEXT,posted_by TEXT);

      CREATE TABLE IF NOT EXISTS legacy_function_members(kind TEXT NOT NULL,table_name TEXT NOT NULL,

      record_no INTEGER NOT NULL,batch_id INTEGER NOT NULL,PRIMARY KEY(kind,table_name,record_no));

      CREATE TABLE IF NOT EXISTS legacy_function_events(id INTEGER PRIMARY KEY,batch_id INTEGER,at TEXT NOT NULL,actor TEXT NOT NULL,action TEXT NOT NULL,reason TEXT NOT NULL);

      CREATE TABLE IF NOT EXISTS legacy_function_templates(kind TEXT PRIMARY KEY,body TEXT NOT NULL,revision INTEGER NOT NULL DEFAULT 0);

      CREATE TABLE IF NOT EXISTS legacy_draft_checks(id INTEGER PRIMARY KEY,payee TEXT NOT NULL,check_no TEXT NOT NULL UNIQUE,

      check_date TEXT NOT NULL,amount TEXT NOT NULL,category TEXT NOT NULL,case_refs TEXT NOT NULL,evidence TEXT NOT NULL,

      revision INTEGER NOT NULL DEFAULT 0,posted_batch INTEGER,at TEXT NOT NULL,actor TEXT NOT NULL);

      CREATE TRIGGER IF NOT EXISTS preserve_function_payload BEFORE UPDATE OF payload_json,sha256 ON legacy_function_batches BEGIN SELECT RAISE(ABORT,'Saved batch contents are immutable'); END;

      CREATE TRIGGER IF NOT EXISTS preserve_function_history BEFORE DELETE ON legacy_function_batches BEGIN SELECT RAISE(ABORT,'Saved batch history is retained'); END;

    ''')

    db.execute("CREATE INDEX IF NOT EXISTS working_legacy_profile_id ON working_legacy(table_name,trim(json_extract(data_json,'$.ID')),deleted)")
    original_print.setup(db)
    existing={r[1] for r in db.execute('PRAGMA table_info(legacy_draft_checks)')}
    for key in ('print_address','print_city','print_state','print_zip','amount_words','definition_text'):
        if key not in existing:db.execute('ALTER TABLE legacy_draft_checks ADD COLUMN '+key+" TEXT NOT NULL DEFAULT ''")
    db.commit()

def stamp():return dt.datetime.now(dt.timezone.utc).isoformat()

def truth(v):return str(v).strip().upper() in ('T','Y','1','.T.')

def iso(v):

    value=str(v or '').strip()

    if not value:return None

    try:return (dt.datetime.strptime(value,'%Y%m%d').date() if len(value)==8 else dt.date.fromisoformat(value)).isoformat()

    except ValueError:return None

def date_range(start,end):

    if not start and not end:return None,None

    if not start or not end:raise ValueError('Enter both dates or leave both blank for all dates.')

    a=date_format.parse(start).isoformat();b=date_format.parse(end).isoformat()

    if a>b:raise ValueError('Start date must not follow end date.')

    return a,b

def records(db,table,include_deleted=False):

    for row in db.execute('SELECT * FROM working_legacy WHERE table_name=? AND (deleted=0 OR ?=1) ORDER BY record_no',(table,int(include_deleted))):

        yield {'table':table,'row':row['record_no'],'revision':row['revision'],'deleted':row['deleted'],'data':json.loads(row['data_json']),'dependencies':[]}

def profile(db,item,cache=None):

    d=item['data'];identity=str(d.get('DEF_ID','')).strip()

    matches=(cache.get(identity,[]) if cache is not None else db.execute("SELECT * FROM working_legacy WHERE table_name='WC_DEF' AND deleted=0 AND trim(json_extract(data_json,'$.ID'))=?",(identity,)).fetchall()) if identity else []

    if len(matches)==1:

        row=matches[0];p=json.loads(row['data_json']);item['dependencies'].append({'table':'WC_DEF','row':row['record_no'],'revision':row['revision']})

        p['HISTORY']=lw.memo_text(db,'WC_DEF',p.get('HISTORY',''))

        d.update({k:p.get(k,'') for k in ('ADDRESS','ADDRESS2','CITY','STATE','ZIP','TELEPHONE','DOB','HISTORY','NAME')});d['PROFILE_STATUS']='Unique defendant ID';return True

    d['PROFILE_STATUS']='Missing or ambiguous defendant ID';return False

def render_template(body,values):

    result=[]

    for literal,key,format_spec,conversion in string.Formatter().parse(body):

        result.append(literal)

        if key is not None:

            if format_spec or conversion or not re.fullmatch('[A-Z][A-Z0-9_]*',key):raise ValueError('Use plain uppercase field placeholders such as {DEFENDANT}.')

            if key not in values:raise ValueError('Unknown print field: '+key)

            result.append(str(values[key]))

    return ''.join(result)

def default_template(kind, include_legacy_wording=True):

    if kind in ('labels','folder_labels'):

        return '{DEFENDANT}\n{ADDRESS}\n{ADDRESS2}\n{CITY}, {STATE} {ZIP}' if kind=='labels' else '{CASE_NO} — {DEFENDANT}\n{MERCHANT} / check {CK_NO}'

    title=SPEC[kind][0];content=''

    if kind not in FORMS:return '{REPORT_TITLE}\nPeriod: {START_DATE} to {END_DATE}\nRecords: {RECORD_COUNT}\n{TOTALS}'

    if include_legacy_wording and kind in FORMS:

        reports=json.loads((Path(__file__).parent/'legacy-report-expressions.json').read_text(encoding='utf-8'))

        for report in reports:

            if report['report']==FORMS[kind]:

                literals=[]

                for item in report['items']:

                    expr=item.get('EXPR','').strip()

                    if len(expr)>1 and expr[0] in ('\"',"'") and expr[-1]==expr[0] and not re.search(r'\w+\(',expr):

                        value=expr[1:-1].replace('\r','\n').replace('{','{{').replace('}','}}')

                        if len(value)>60 and value not in literals:literals.append(value)

                content='\n\n'.join(literals)

        if content:content='IMPORTED LEGACY WORDING — requires office review:\n\n'+content

    return title+'\n\nDate: {PRINT_DATE}\nTo: {DEFENDANT}\n{ADDRESS}\n{ADDRESS2}\n{CITY}, {STATE} {ZIP}\n\nCase: {CASE_NO}\nMerchant: {MERCHANT}\nCheck: {CK_NO} / {CK_DATE} / {CK_AMT}\nRecorded balances: Check {CK_DUE}, Merchant fee {FEE_DUE}, DA {DA_DUE}, Withdrawal {WD_DUE}\n\n'+content

def template(db,kind):

    row=db.execute('SELECT body FROM legacy_function_templates WHERE kind=?',(kind,)).fetchone()

    return row[0] if row else default_template(kind, divisions.database_division(db) == 'troy')

def save_template(db,kind,body,expected_revision,reason,layout=None):

    actor=login.require(db,True)

    if kind not in SPEC:raise ValueError('Unknown template.')

    if not reason.strip():raise ValueError('A reason is required.')

    if layout is not None:

        import reporting

        layout=reporting.validate_layout(layout)

    # Validate field names without executing expressions.

    names={f['name'] for f in lw.schema(db,'WC_CASE')}|{f['name'] for f in lw.schema(db,'WC_DEF')}|{'PRINT_DATE','PROFILE_STATUS','REPORT_TITLE','START_DATE','END_DATE','RECORD_COUNT','TOTALS'}

    if kind not in FORMS and kind not in ('labels','folder_labels'):names={'REPORT_TITLE','START_DATE','END_DATE','RECORD_COUNT','TOTALS'}
    render_template(body,{k:'' for k in names})

    try:

        db.execute('BEGIN IMMEDIATE');row=db.execute('SELECT revision FROM legacy_function_templates WHERE kind=?',(kind,)).fetchone()

        if (row[0] if row else -1)!=expected_revision:raise ValueError('Another user changed this template. Reopen it.')

        db.execute('INSERT INTO legacy_function_templates(kind,body,revision) VALUES(?,?,0) ON CONFLICT(kind) DO UPDATE SET body=excluded.body,revision=legacy_function_templates.revision+1',(kind,body))

        if layout is not None:db.execute('INSERT INTO print_settings VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value',('legacy_label_layout_'+kind,json.dumps(layout)))

        db.execute('INSERT INTO audit(at,operator,action,reference) VALUES(?,?,?,?)',(stamp(),actor,'EDIT_LEGACY_PRINT_TEMPLATE',json.dumps({'kind':kind,'reason':reason,'body':body,'layout':layout})))

        db.commit()

    except Exception:db.rollback();raise

# Troy archive review: one deleted payment and reviewed zero-amount history entries.
# Match the original identity as well as the row number, which can differ by backup.
TROY_REGISTER_EXCLUSIONS = {
    154: ('94-1243', '97R0367', '19970429'),
    15184: ('04-1909', '05R0271', '20050228'),
    21249: ('11-0306', '11R0541', '20110518'),
    14143: ('04-0874', '04R0729', '20040625'),
    15424: ('04-1960', '05R0514', '20050602'),
    17004: ('06-1726', '06R1004', '20061218'),
    17023: ('06-1720', '06R1025', '20061227'),
    17819: ('06-0284', '07R0797', '20070906'),
    17954: ('06-1595', '07R0932', '20071018'),
    18216: ('08-0122', '08R0074', '20080125'),
    18343: ('04-2003', '08R0201', '20080228'),
    18404: ('08-0339', '08R0262', '20080319'),
    19429: ('08-1218', '09R0432', '20090720'),
    19649: ('09-0788', '09R0656', '20091022'),
    20557: ('10-0553', '10R0750', '20101027'),
    21250: ('08-0094', '11R0542', '20110518'),
    21276: ('11-0261', '11R0568', '20110524'),
    21277: ('11-0262', '11R0569', '20110524'),
    21278: ('11-0263', '11R0570', '20110524'),
    21521: ('11-0453', '11R0813', '20110805'),
    21522: ('11-0450', '11R0814', '20110805'),
    21523: ('11-0451', '11R0815', '20110805'),
}


def receipt_register_exclusions(db):
    if divisions.database_division(db) != 'troy':
        return set()
    rows = db.execute(
        f"""SELECT record_no,data_json FROM legacy_records
            WHERE table_name='PAYMENTS' AND record_no IN ({",".join("?" for _ in TROY_REGISTER_EXCLUSIONS)})""",
        tuple(TROY_REGISTER_EXCLUSIONS),
    )
    excluded = set()
    for number, encoded in rows:
        data = json.loads(encoded)
        identity = tuple(str(data.get(key, '')).strip() for key in ('CASE_NO','RECEIPT_NO','DATE'))
        if identity == TROY_REGISTER_EXCLUSIONS[number]:
            excluded.add(number)
    return excluded


def build(db,kind,start='',end='',query='',selected_case=None,sort_city=False,from_batch=None,merchant_filter=False,unposted=False,output_mode='test'):
    import document_mode

    login.require(db)
    if kind=='final':return check_register(db,start,end)
    if kind not in SPEC:raise ValueError('Unknown report section.')

    start,end=date_range(start,end);title,table,columns,date_field=SPEC[kind]

    warnings=[];items=[];skipped_dates=0
    profile_cache=None
    if table=='WC_CASE' and selected_case is None:
        profile_cache={}
        for r in db.execute("SELECT * FROM working_legacy WHERE table_name='WC_DEF' AND deleted=0"):
            identity=str(json.loads(r['data_json']).get('ID') or '').strip()
            profile_cache.setdefault(identity,[]).append(r)

    if from_batch is not None:

        previous=load_batch(db,from_batch)

        allowed={i['row'] for i in previous['items'] if i['table']=='WC_CASE'}

    else:allowed=None

    excluded = receipt_register_exclusions(db) if kind == 'receipts' else set()
    if kind == 'receipts' and output_mode != document_mode.TEST:
        excluded.update(row[0] for row in db.execute("""
            SELECT payment_record FROM legacy_test_payments
            WHERE COALESCE(json_extract(party_json,'$._document_mode'),'test')<>?
        """, (output_mode,)))
    for item in records(db,table):

        if item['row'] in excluded:
            continue
        d=item['data']

        if selected_case is not None and (table!='WC_CASE' or item['row']!=selected_case):continue

        if allowed is not None and item['row'] not in allowed:continue

        searchable=' '.join(str(d.get(k,'')) for k in ('MERCHANT','MERCH_ID')) if merchant_filter or kind=='merchant_history' else (' '.join(str(d.get(k,'')) for k in ('DEFENDANT','DEF_ID')) if kind=='defendant_history' else json.dumps(d,ensure_ascii=False))

        if query and query.casefold() not in searchable.casefold():continue

        if start and date_field:

            value=iso(d.get(date_field))

            if not value:skipped_dates+=1;continue

            if not start<=value<=end:continue

        if kind=='proof' and truth(d.get('PROOF')):continue

        if kind in ('letter1','letter2','letter3'):

            date_key={'letter1':'LTR_SENT','letter2':'LTR_SENT2','letter3':'LTR_SENT3'}[kind]

            if from_batch is None and selected_case is None and str(d.get(date_key,'')).strip():continue

        if kind=='visit' and not truth(d.get('VISIT')):continue

        if kind=='warrant' and not truth(d.get('ACT_WARR')):continue

        if kind=='recalls' and not truth(d.get('RECALLED')):continue

        if table=='WC_CASE':profile(db,item,profile_cache)

        if kind in FORMS or kind=='labels':

            if d.get('PROFILE_STATUS')!='Unique defendant ID' or not str(d.get('ADDRESS','')).strip():

                raise ValueError('Case source row '+str(item['row'])+' has a missing/ambiguous defendant profile or blank address. Correct it or select other records before preparing mail.')

        if table=='WC_DEF':

            d['HISTORY']=lw.memo_text(db,'WC_DEF',d.get('HISTORY',''))

        if kind=='receipts' and unposted and db.execute('SELECT 1 FROM legacy_function_members WHERE kind=? AND table_name=? AND record_no=?',('receipts',table,item['row'])).fetchone():continue
        if table=='PAYMENTS':
            for key in PAY_FIELDS:

                lw.money(d.get(key,'')) # invalid source amounts block financial report totals instead of disappearing

        items.append(item)

    if sort_city:items.sort(key=lambda i:tuple(str(i['data'].get(k,'')) for k in ('STATE','CITY','DEFENDANT')))

    elif kind in ('visit','defendants'):items.sort(key=lambda i:str(i['data'].get('DEFENDANT',i['data'].get('NAME',''))))

    if skipped_dates:warnings.append(str(skipped_dates)+' matching records with missing/invalid dates excluded by the date filter. Use blank dates to review all records.')

    if kind in ('merchant_history','defendant_history'):

        selected_rows={i['row'] for i in items};numbers={str(i['data'].get('CASE_NO','')) for i in items};history=[]

        for p in records(db,'PAYMENTS',include_deleted=True):

            import legacy_reconcile

            link=legacy_reconcile.explicit(db,p['row'])

            if (link and link['case_record'] in selected_rows) or (not link and str(p['data'].get('CASE_NO','')) in numbers):history.append(p)

        if history:warnings.append('Payment history follows explicit case-row links first; remaining CASE_NO matches may be ambiguous.')

    else:history=[]

    totals={}

    if table=='PAYMENTS':totals={k:str(sum((lw.money(i['data'].get(k,'')) for i in items),Decimal('0'))) for k in PAY_FIELDS}

    payload={'kind':kind,'title':title,'start':start,'end':end,'columns':list(columns),'items':items,'totals':totals,'warnings':warnings,'history':history,'documents':[]}
    if kind == 'receipts' and output_mode != document_mode.TEST:
        payload['document_mode'] = output_mode

    if kind in FORMS or kind in ('labels','folder_labels'):

        body=template(db,kind)

        for i in items:

            values={f['name']:'' for f in lw.schema(db,'WC_CASE')};values.update({f['name']:'' for f in lw.schema(db,'WC_DEF')});values.update(i['data']);values['CK_DATE']=date_format.display(values.get('CK_DATE'));values['PRINT_DATE']=date_format.display(dt.date.today());values.update(REPORT_TITLE=payload['title'],START_DATE=date_format.display(payload.get('start')) or 'all dates',END_DATE=date_format.display(payload.get('end')) or 'all dates',RECORD_COUNT=len(payload['items']),TOTALS=json.dumps(payload.get('totals',{})))

            payload['documents'].append(render_template(body,values))

    if kind in FORMS:
        attach_original(db,payload,kind)

    if kind not in FORMS and kind not in ('labels','folder_labels'):

        payload['wrapper']=render_template(template(db,kind),{'REPORT_TITLE':title,'START_DATE':date_format.display(start) or 'all dates','END_DATE':date_format.display(end) or 'all dates','RECORD_COUNT':len(items),'TOTALS':json.dumps(totals)})

    if kind in ('labels','folder_labels'):

        import reporting

        row=db.execute('SELECT value FROM print_settings WHERE key=?',('legacy_label_layout_'+kind,)).fetchone()

        payload['layout']=json.loads(row[0]) if row else reporting.DEFAULT_LAYOUT

    if kind=='monthly':

        grouped={}

        for i in items:

            m=(iso(i['data'].get('DATE')) or 'Unknown date')[:7];entry=grouped.setdefault(m,{k:Decimal('0') for k in PAY_FIELDS})

            for k in PAY_FIELDS:entry[k]+=lw.money(i['data'].get(k,''))

        payload['monthly_totals']={m:{k:str(v) for k,v in sums.items()} for m,sums in sorted(grouped.items())}
        entries={}
        for i in records(db,'WC_CASE'):
            value=iso(i['data'].get('ENTER_DATE'))
            if not value or (start and not start<=value<=end):continue
            group=entries.setdefault(value[:7],{'checks_entered':0,'check_amount':Decimal('0'),'invalid_check_amounts':0});group['checks_entered']+=1
            try:group['check_amount']+=lw.money(i['data'].get('CK_AMT',''))
            except ValueError:group['invalid_check_amounts']+=1
        payload['entry_activity']={m:{k:str(v) if isinstance(v,Decimal) else v for k,v in d.items()} for m,d in sorted(entries.items())}

    return payload

def save_batch(db,payload):

    actor=login.require(db);encoded=json.dumps(payload,ensure_ascii=True);digest=hashlib.sha256(encoded.encode()).hexdigest()

    with db:

        cur=db.execute('INSERT INTO legacy_function_batches(kind,created_at,actor,start_date,end_date,payload_json,sha256) VALUES(?,?,?,?,?,?,?)',(payload['kind'],stamp(),actor,payload.get('start'),payload.get('end'),encoded,digest))

        return cur.lastrowid

def load_batch(db,batch):

    row=db.execute('SELECT * FROM legacy_function_batches WHERE id=?',(batch,)).fetchone()

    if not row:raise ValueError('Saved batch not found.')

    if hashlib.sha256(row['payload_json'].encode()).hexdigest()!=row['sha256']:raise ValueError('Saved batch integrity check failed.')

    return json.loads(row['payload_json'])

def post_batch(db,batch,reason):

    actor=login.require(db,True)

    if not reason.strip():raise ValueError('A posting reason is required.')

    try:

        db.execute('BEGIN IMMEDIATE');row=db.execute('SELECT * FROM legacy_function_batches WHERE id=?',(batch,)).fetchone()

        if not row or row['status']!='draft':raise ValueError('This batch is missing or already posted.')

        payload=load_batch(db,batch);kind=payload['kind']
        if any(page['errors'] for page in payload.get('original_pages',[])):raise ValueError('Resolve original-layout errors and create a new reviewed batch before posting.')

        if kind not in (*POST_FIELDS,'receipts','final'):raise ValueError('This report is for review/printing; it has no posting action.')

        if not payload['items']:raise ValueError('Cannot post an empty batch.')

        if kind == 'receipts':
            excluded = receipt_register_exclusions(db)
            if any(item['row'] in excluded for item in payload['items']):
                raise ValueError('This saved receipt list includes entries excluded from collections. Create a new preview before posting.')

        for item in payload['items']:

            if item['table']=='DRAFT_CHECK':

                check=db.execute('SELECT * FROM legacy_draft_checks WHERE id=?',(item['row'],)).fetchone()

                if not check or check['revision']!=item['revision'] or check['posted_batch'] is not None:raise ValueError('A draft check changed or was already posted. Regenerate the register.')
                if db.execute("SELECT 1 FROM working_legacy WHERE table_name IN ('REGISTER','CHECKS1','CHECKS2') AND trim(json_extract(data_json,'$.DA_CK_NO'))=? LIMIT 1",(check['check_no'],)).fetchone():raise ValueError('A draft check number now appears in legacy register history; nothing was posted.')

                continue

            source=lw.get(db,item['table'],item['row'])

            if source['deleted'] or source['revision']!=item['revision']:raise ValueError('Source records changed after the preview. Create a new batch before posting.')

            for dep in item.get('dependencies',[]):

                d=lw.get(db,dep['table'],dep['row'])

                if d['deleted'] or d['revision']!=dep['revision']:raise ValueError('Recipient information changed after printing; create a new batch.')

            if db.execute('SELECT 1 FROM legacy_function_members WHERE kind=? AND table_name=? AND record_no=?',(kind,item['table'],item['row'])).fetchone():raise ValueError('One or more records were already posted in this test workflow. No changes saved.')

        today=dt.date.today().strftime('%Y%m%d')

        for item in payload['items']:

            if item['table']=='DRAFT_CHECK':

                db.execute('UPDATE legacy_draft_checks SET posted_batch=?,revision=revision+1 WHERE id=?',(batch,item['row']))

            else:

                if kind in POST_FIELDS:

                    source=lw.get(db,item['table'],item['row']);data=json.loads(source['data_json'])

                    for key,value in POST_FIELDS[kind].items():data[key]=today if value=='@DATE' else value

                    lw._write(db,item['table'],item['row'],data,False,source['revision'],'Post test '+kind+' batch '+str(batch)+': '+reason,actor)

                db.execute('INSERT INTO legacy_function_members VALUES(?,?,?,?)',(kind,item['table'],item['row'],batch))

        db.execute("UPDATE legacy_function_batches SET status='posted',posted_at=?,posted_by=? WHERE id=?",(stamp(),actor,batch))

        db.execute('INSERT INTO legacy_function_events(batch_id,at,actor,action,reason) VALUES(?,?,?,?,?)',(batch,stamp(),actor,'POST_TEST_BATCH',reason))

        db.execute('INSERT INTO audit(at,operator,action,reference) VALUES(?,?,?,?)',(stamp(),actor,'POST_LEGACY_FUNCTION_BATCH',str(batch)))

        db.commit()

    except Exception:db.rollback();raise

def save_check(db,values,reason,check_id=None,expected_revision=None):

    actor=login.require(db,True)

    if not reason.strip() or not values.get('evidence','').strip():raise ValueError('Supporting evidence and a reason are required.')

    if not values.get('payee','').strip() or not values.get('check_no','').strip():raise ValueError('Payee and draft check number are required.')

    values=dict(values);values['check_date']=date_format.parse(values['check_date']).isoformat();amount=lw.money(values['amount'])

    if amount<=0:raise ValueError('A draft check requires a positive amount.')

    values['amount']=format(amount,'.2f')

    if values['category'] not in ('Merchant','DA / Commission','Defendant refund'):raise ValueError('Choose a check category.')

    try:

        db.execute('BEGIN IMMEDIATE')

        if db.execute("SELECT 1 FROM working_legacy WHERE table_name IN ('REGISTER','CHECKS1','CHECKS2') AND trim(json_extract(data_json,'$.DA_CK_NO'))=? LIMIT 1",(values['check_no'].strip(),)).fetchone():raise ValueError('This check number already appears in legacy register history.')

        before=None

        if check_id is not None:

            before=db.execute('SELECT * FROM legacy_draft_checks WHERE id=?',(check_id,)).fetchone()

            if not before or before['posted_batch'] is not None or before['revision']!=expected_revision:raise ValueError('Check changed or is posted. Reopen it; posted drafts cannot be overwritten.')

            db.execute('UPDATE legacy_draft_checks SET payee=?,check_no=?,check_date=?,amount=?,category=?,case_refs=?,evidence=?,revision=revision+1 WHERE id=?',(*(values[k].strip() for k in ('payee','check_no','check_date','amount','category','case_refs','evidence')),check_id))

        else:

            cur=db.execute('INSERT INTO legacy_draft_checks(payee,check_no,check_date,amount,category,case_refs,evidence,at,actor) VALUES(?,?,?,?,?,?,?,?,?)',(*(values[k].strip() for k in ('payee','check_no','check_date','amount','category','case_refs','evidence')),stamp(),actor));check_id=cur.lastrowid

        for key in ('print_address','print_city','print_state','print_zip','amount_words','definition_text'):
            values[key]=str(values.get(key,'')).strip()
            db.execute('UPDATE legacy_draft_checks SET '+key+'=? WHERE id=?',(values[key],check_id))
        db.execute('INSERT INTO audit(at,operator,action,reference) VALUES(?,?,?,?)',(stamp(),actor,'SAVE_DRAFT_CHECK',json.dumps({'id':check_id,'before':dict(before) if before else None,'after':values,'reason':reason})))

        db.commit();return check_id

    except Exception:db.rollback();raise

def check_register(db,start='',end='',category=None):

    start,end=date_range(start,end);items=[]

    for row in db.execute('SELECT * FROM legacy_draft_checks WHERE posted_batch IS NULL ORDER BY check_date,id'):

        if start and not start<=row['check_date']<=end:continue

        if category and row['category']!=category:continue

        items.append({'table':'DRAFT_CHECK','row':row['id'],'revision':row['revision'],'data':dict(row)})

    result={'kind':'final','title':'Final Draft Check Register','start':start,'end':end,'columns':['check_no','check_date','payee','category','amount','case_refs'],'items':items,'documents':[],'warnings':['Draft amounts are explicitly entered and reviewed. No fund percentages or bank payments are inferred.'],'totals':{'amount':str(sum((lw.money(i['data']['amount']) for i in items),Decimal('0')))}}
    result['wrapper']=render_template(template(db,'final'),{'REPORT_TITLE':result['title'],'START_DATE':date_format.display(start) or 'all dates','END_DATE':date_format.display(end) or 'all dates','RECORD_COUNT':len(items),'TOTALS':json.dumps(result['totals'])})
    return result


def report_cell(key, value):
    if key.upper() in {'DATE','ENTER_DATE','CK_DATE','DUE_DATE','DEP_DATE','CHECK_DATE','DOB'}:
        return str(date_format.display(value))
    return str(value)


def text_report(payload):
    from document_mode import report_mark

    lines=[payload.get('wrapper',payload['title']),report_mark(payload),f'From: {date_format.display(payload.get("start")) or "all dates"}  To: {date_format.display(payload.get("end")) or "all dates"}',f'Records: {len(payload["items"]):,}',*payload.get('warnings',[]),'']

    if payload.get('documents'):return '\n'.join(lines)+'\n\n'+'\n\n' .join(payload['documents'])

    lines.append('\t'.join(['Source row',*payload['columns']]))

    for i in payload['items']:lines.append('\t'.join([str(i['row']),*[report_cell(k,i['data'].get(k,'')) for k in payload['columns']]]))

    lines.extend(['','Totals: '+json.dumps(payload.get('totals',{}))])

    if payload.get('monthly_totals'):lines.extend(['','Monthly totals:',json.dumps(payload['monthly_totals'],indent=2)])
    if payload.get('entry_activity'):lines.extend(['','Entry activity (invalid amounts counted separately):',json.dumps(payload['entry_activity'],indent=2)])

    if payload.get('history'):

        lines.extend(['','Linked payment history:', '\t'.join(['Payment row','Deleted',*PAY_COLUMNS])])

        for i in payload['history']:lines.append('\t'.join([str(i['row']),str(i.get('deleted',0)),*[report_cell(k,i['data'].get(k,'')) for k in PAY_COLUMNS]]))

    return '\n'.join(lines)

def attach_original(db,payload,kind=None):
    if divisions.database_division(db) == 'enterprise':
        return
    pages=[]
    for item in payload['items']:
        selected=kind or {'Merchant':'check_merchant','DA / Commission':'check_fund','Defendant refund':'check_refund'}[item['data']['category']]
        if original_print.config(db,selected)['mode']!='original':
            if kind:payload['documents']=[original_print.update_notice(x) for x in payload['documents']]
            return
        pages.append(original_print.render_page(db,selected,item['data'] if kind else {},check=None if kind else item['data']))
    payload['original_pages']=pages
    payload['documents']=[original_print.page_text(page) for page in pages]
    for page in pages:
        payload['warnings'].extend(page['report']+': '+e for e in page['errors']+page['warnings'])

def print_html(payload,folder,office_heading=None):
    from document_mode import report_mark

    folder=Path(folder);folder.mkdir(parents=True,exist_ok=True);path=folder/(uuid.uuid4().hex+'.html')

    if 'original_pages' in payload:
        path.write_text(original_print.html_document(payload['original_pages']),encoding='utf-8');return path

    heading='<h2>Worthless Check</h2>'

    if office_heading:
        heading = '<h2>' + html.escape(office_heading).replace(chr(10), '<br>') + '</h2>'
    heading += '<p><strong>' + html.escape(report_mark(payload)) + '</strong></p>'
    if payload['kind'] in ('labels','folder_labels'):

        import reporting

        content=reporting.labels_html(payload['documents'],payload.get('layout',reporting.DEFAULT_LAYOUT))

        content=content.replace('Letter, portrait, actual size','DRAFT / TEST LABELS — Letter, portrait, actual size')

        path.write_text(content,encoding='utf-8');return path

        body='<div class="labels">'+''.join('<div class="label">'+html.escape(d).replace('\n','<br>')+'</div>' for d in payload['documents'])+'</div>'

    elif payload.get('documents'):

        body=''.join('<section>'+heading+'<pre>'+html.escape(d)+'</pre></section>' for d in payload['documents'])

    else:

        body=heading+'<h3>'+html.escape(payload['title'])+'</h3><pre>'+html.escape(payload.get('wrapper',''))+'</pre>'+''.join('<p>'+html.escape(w)+'</p>' for w in payload.get('warnings',[]))+'<table><thead><tr><th>Source row</th>'+''.join('<th>'+html.escape(k)+'</th>' for k in payload['columns'])+'</tr></thead><tbody>'

        body+=''.join('<tr><td>'+str(i['row'])+'</td>'+''.join('<td>'+html.escape(report_cell(k,i['data'].get(k,'')))+'</td>' for k in payload['columns'])+'</tr>' for i in payload['items'])+'</tbody></table><p>Totals: '+html.escape(json.dumps(payload.get('totals',{})))+'</p>'

        if payload.get('monthly_totals'):body+='<pre>'+html.escape(json.dumps(payload['monthly_totals'],indent=2))+'</pre>'

        if payload.get('entry_activity'):body+='<pre>'+html.escape(json.dumps(payload['entry_activity'],indent=2))+'</pre>'
        if payload.get('history'):body+='<h3>Payment history (source rows)</h3><pre>'+html.escape('\n'.join(str(i['row'])+(' [deleted] ' if i.get('deleted') else ' ')+json.dumps(i['data']) for i in payload['history']))+'</pre>'

    css='@page{size:letter;margin:.5in}body{font-family:Arial;font-size:9pt}pre{white-space:pre-wrap}table{border-collapse:collapse;width:100%;font-size:7pt}td,th{border:1px solid #aaa;padding:3px;word-break:break-word}thead{display:table-header-group}section{break-after:page}.labels{display:grid;grid-template-columns:repeat(3,2.625in);grid-auto-rows:1in;column-gap:.125in}.label{box-sizing:border-box;padding:.08in;font-size:10pt;overflow:hidden;break-inside:avoid}@media print{button{display:none}}'

    path.write_text('<!doctype html><html><head><meta charset="utf-8"><title>'+html.escape(payload['title'])+'</title><style>'+css+'</style></head><body><button onclick="window.print()">Print / Save PDF</button>'+body+'</body></html>',encoding='utf-8')

    return path

def labels_from_batch(db,batch,kind='labels'):

    previous=load_batch(db,batch);payload={'kind':kind,'title':'Labels from saved batch '+str(batch),'start':previous.get('start'),'end':previous.get('end'),'items':previous['items'],'columns':[],'documents':[],'totals':{},'warnings':[]}

    for i in payload['items']:

        values={f['name']:'' for f in lw.schema(db,'WC_CASE')};values.update({f['name']:'' for f in lw.schema(db,'WC_DEF')});values.update(i['data']);values['CK_DATE']=date_format.display(values.get('CK_DATE'));values['PRINT_DATE']=date_format.display(dt.date.today());values.update(REPORT_TITLE=payload['title'],START_DATE=date_format.display(payload.get('start')) or 'all dates',END_DATE=date_format.display(payload.get('end')) or 'all dates',RECORD_COUNT=len(payload['items']),TOTALS=json.dumps(payload.get('totals',{})))

        if not str(values.get('ADDRESS','')).strip():raise ValueError('Saved batch has no recipient address for source row '+str(i['row']))

        payload['documents'].append(render_template(template(db,kind),values))

    import reporting

    layout=db.execute('SELECT value FROM print_settings WHERE key=?',('legacy_label_layout_'+kind,)).fetchone()

    payload['layout']=json.loads(layout[0]) if layout else reporting.DEFAULT_LAYOUT

    return payload


def populate_menu(menu,dispatch,db):

    def add(parent,entries):

        for title,action in entries:

            if isinstance(action,list):

                child=tk.Menu(parent,tearoff=False);add(child,action);parent.add_cascade(label=title,menu=child)

            elif action=='analysis.year':

                child=tk.Menu(parent,tearoff=False)

                years={dt.date.today().year}

                for r in db.execute("SELECT DISTINCT substr(json_extract(data_json,'$.DATE'),1,4) FROM working_legacy WHERE table_name='PAYMENTS'"):

                    if str(r[0]).isdigit() and 1900<=int(r[0])<=2100:years.add(int(r[0]))

                for year in sorted(years):child.add_command(label=str(year),command=lambda y=year:dispatch('analysis.year:'+str(y)))

                child.add_command(label='Other year...',command=lambda:dispatch('analysis.year'));parent.add_cascade(label=title,menu=child)

            else:parent.add_command(label=title,accelerator={'case.edit':'Ctrl+Enter'}.get(action,''),command=lambda a=action:dispatch(a))

    add(menu,MENU)

def open_for_app(app,action):

    try:

        if hasattr(app,'legacy_mode') and app.legacy_mode():Center(app.legacy_context(False),action);return

        if action == 'labels.create':
            app.functions_tools.labels()
            return

        messagebox.showinfo('Legacy Functions',
                            'This function requires a loaded legacy workspace. Use Complete Legacy Workspace to load one.',
                            parent=app.root)

    except Exception as e:messagebox.showerror('Legacy Functions',str(e),parent=app.root)

class Center:

    def __init__(self,workspace,action='proof.create'):

        self.workspace=workspace;self.db=workspace.db;self.app=workspace.app;self.batch=None;self.payload=None;self.action=action

        self.selected_case=int(workspace.tree.selection()[0]) if workspace.table.get()=='WC_CASE' and workspace.tree.selection() else None

        setup(self.db)

        self.win=tk.Toplevel(workspace.win);self.win.title('Legacy Functions | Reports, letters and registers');self.win.geometry(f'{min(1200,self.win.winfo_screenwidth()-80)}x{min(800,self.win.winfo_screenheight()-100)}')

        menu=tk.Menu(self.win);functions=tk.Menu(menu,tearoff=False);populate_menu(functions,lambda a:self.safe(lambda:self.run(a)),self.db);menu.add_cascade(label='Functions',menu=functions);self.win.configure(menu=menu)

        ttk.Label(self.win,text='COMPLETE LEGACY DATA • Saved previews are frozen for reprinting • Draft/test outputs • Posting requires Administrator review',wraplength=1100).pack(anchor='w',padx=12,pady=8)

        bar=ttk.Frame(self.win);bar.pack(fill='x',padx=12)

        self.kind=tk.StringVar(value='proof');self.start=tk.StringVar(value=date_format.display(dt.date.today().replace(day=1)));self.end=tk.StringVar(value=date_format.display(dt.date.today()));self.query=tk.StringVar()

        ttk.Combobox(bar,textvariable=self.kind,values=list(SPEC),state='readonly',width=24).pack(side='left')

        for name,var,width in [('From',self.start,12),('To',self.end,12),('Search / merchant / ID',self.query,24)]:ttk.Label(bar,text=name).pack(side='left',padx=(7,2));ttk.Entry(bar,textvariable=var,width=width).pack(side='left')

        buttons=ttk.Frame(self.win);buttons.pack(fill='x',padx=12,pady=6)

        self.action_text=tk.StringVar();ttk.Label(buttons,textvariable=self.action_text).pack(side='left')

        ttk.Button(buttons,text='Create saved preview',command=lambda:self.safe(self.generate)).pack(side='right')

        self.book=ttk.Notebook(self.win);self.book.pack(fill='both',expand=True,padx=12,pady=8)

        preview=ttk.Frame(self.book);saved=ttk.Frame(self.book);self.book.add(preview,text='Preview / print / post');self.book.add(saved,text='Saved batches / reprints')

        self.text=tk.Text(preview,wrap='none',font=('Consolas',10));self.text.grid(row=0,column=0,sticky='nsew');scroll=ttk.Scrollbar(preview,command=self.text.yview);scroll.grid(row=0,column=1,sticky='ns');horizontal=ttk.Scrollbar(preview,orient='horizontal',command=self.text.xview);horizontal.grid(row=1,column=0,sticky='ew');self.text.configure(yscrollcommand=scroll.set,xscrollcommand=horizontal.set);preview.rowconfigure(0,weight=1);preview.columnconfigure(0,weight=1)

        self.saved=ttk.Treeview(saved,columns=('id','kind','created','actor','status','from','to'),show='headings')

        for k in self.saved['columns']:self.saved.heading(k,text=k);self.saved.column(k,width=140)

        self.saved.pack(fill='both',expand=True);self.saved.bind('<Double-1>',lambda e:self.safe(self.open_saved))

        ttk.Button(saved,text='Open selected frozen batch',command=lambda:self.safe(self.open_saved)).pack(pady=8)

        controls=ttk.Frame(self.win);controls.pack(fill='x',padx=12,pady=8)

        ttk.Button(controls,text='Print / Save PDF (Letter)',command=lambda:self.safe(self.print_current)).pack(side='left')

        ttk.Button(controls,text='Export text',command=lambda:self.safe(self.export)).pack(side='left',padx=6)

        self.post_button=ttk.Button(controls,text='Post reviewed test batch',command=lambda:self.safe(self.post),state='disabled');self.post_button.pack(side='right')

        self.status=tk.StringVar();ttk.Label(self.win,textvariable=self.status,wraplength=1100).pack(anchor='w',padx=12,pady=(0,8))

        self.refresh_saved();self.safe(lambda:self.run(action))

    def safe(self,fn):

        try:fn()

        except Exception as e:messagebox.showerror('Legacy Functions',str(e),parent=self.win)

    def refresh_saved(self):

        self.saved.delete(*self.saved.get_children())

        for r in self.db.execute('SELECT * FROM legacy_function_batches ORDER BY id DESC LIMIT 500'):self.saved.insert('','end',iid=str(r['id']),values=[r['id'],r['kind'],date_format.timestamp(r['created_at']),r['actor'],r['status'],date_format.display(r['start_date']),date_format.display(r['end_date'])])

    def display(self,batch):
        import document_mode

        payload=load_batch(self.db,batch)
        if payload.get('document_mode') == document_mode.OFFICIAL and document_mode.for_store(self.app.store) != document_mode.OFFICIAL:
            payload['document_mode'] = document_mode.REHEARSAL
        user_audit.opened(self.db,'REPORT',f"{payload['kind']} / batch {batch}")
        self.batch=batch;self.payload=payload;self.text.configure(state='normal');self.text.delete('1.0','end');self.text.insert('end',text_report(self.payload));self.text.configure(state='disabled')

        row=self.db.execute('SELECT status FROM legacy_function_batches WHERE id=?',(batch,)).fetchone()

        allowed=self.payload['kind'] in (*POST_FIELDS,'receipts','final') and row[0]=='draft'

        self.post_button.configure(state='normal' if allowed else 'disabled');self.status.set(f'Batch {batch} | {row[0]} | {len(self.payload["items"]):,} records. Reprints retain the saved values and wording.');self.book.select(0);self.refresh_saved()

    def latest(self,kind):

        row=self.db.execute('SELECT id FROM legacy_function_batches WHERE kind=? ORDER BY id DESC LIMIT 1',(kind,)).fetchone()

        if not row:raise ValueError('No saved '+kind+' batch exists yet. Create one first.')

        self.display(row[0]);return row[0]

    def generate(self):
        from document_mode import for_store

        self.status.set('Creating the frozen preview...');self.win.update_idletasks()
        selected=self.selected_case if self.action==self.kind.get()+'.single' else None
        payload=check_register(self.db,self.start.get(),self.end.get()) if self.kind.get()=='final' else build(self.db,self.kind.get(),self.start.get(),self.end.get(),self.query.get(),selected_case=selected,merchant_filter=self.action.endswith('.merchant'),unposted=self.kind.get()=='receipts' and self.action.endswith('.create'),output_mode=for_store(self.app.store))

        self.display(save_batch(self.db,payload))

    def run(self,action):
        from document_mode import for_store

        if not action.startswith('case.') and action != 'receipt.single':
            reference = action if self.selected_case is None else f'{action} / case row {self.selected_case}'
            user_audit.opened(self.db,'REPORT_TOOL',reference)
        self.action=action;self.action_text.set(action)

        if action=='case.edit':

            if self.selected_case is None:raise ValueError('Select a WC_CASE row in Complete Legacy Workspace, then choose Edit Case.')

            self.workspace.table.set('WC_CASE');self.workspace.tree.delete(*self.workspace.tree.get_children());self.workspace.tree.insert('','end',iid=str(self.selected_case));self.workspace.tree.selection_set(str(self.selected_case));self.workspace.details();return

        if action=='case.new':self.workspace.table.set('WC_CASE');self.workspace.search();self.workspace.details(new=True);return

        if action.startswith('data.'):

            self.workspace.table.set(action.split('.',1)[1]);self.workspace.query.set('');self.workspace.search();self.workspace.win.lift();return

        if action=='layouts.configure':
            if divisions.database_division(self.db) == 'enterprise':
                raise ValueError('Office 2 uses draft templates. Imported original layouts require organization-specific review.')
            original_print.editor(self.db,self.win)
            return

        if action.startswith('templates.'):

            kind=action.split('.',1)[1];self.modify_template(kind if kind in ('labels','folder_labels') else self.kind.get());return

        if action.startswith('checks.'):

            CheckManager(self,action.split('.',1)[1]);return

        if action=='receipt.single':self.workspace.print_payment();return

        kind,operation=action.split('.',1);self.kind.set(kind)

        if kind=='labels' and operation in ('letter1','letter2','letter3'):

            r=self.db.execute('SELECT id FROM legacy_function_batches WHERE kind=? ORDER BY id DESC LIMIT 1',(operation,)).fetchone()

            if not r:raise ValueError('Create a '+operation+' batch first.')

            self.display(save_batch(self.db,labels_from_batch(self.db,r[0])));return

        if operation in ('view','reprint','post'):

            self.latest(kind)

            if operation=='post':self.status.set('Review this saved batch and click Post reviewed test batch. Posting records a test workflow event; it does not send mail or move bank funds.')

            return

        if operation=='create':
            self.status.set('Choose From / To dates and an optional search, then Create saved preview. Blank dates include all history; use a date range for large batches.');return
        if operation.startswith('year'):

            year=int(operation.split(':')[1]) if ':' in operation else simpledialog.askinteger('Year','Report year:',parent=self.win,minvalue=1900,maxvalue=2100)

            if year is None:return

            self.start.set(f'01-01-{year:04d}');self.end.set(f'12-31-{year:04d}')

        elif operation=='month':

            now=dt.date.today();self.start.set(date_format.display(now.replace(day=1)));self.end.set(date_format.display(now.replace(day=calendar.monthrange(now.year,now.month)[1])))

        elif operation=='range':

            self.status.set('Enter From / To dates (MM-DD-YYYY), then Create saved preview. Leave both blank for all dates.');return

        elif operation=='merchant':

            q=simpledialog.askstring('Merchant filter','Merchant name or original ID (review selected records):',parent=self.win)

            if not q:return

            self.query.set(q)

        if operation=='single':

            if self.selected_case is None:raise ValueError('Select one exact WC_CASE row in Complete Legacy Workspace before choosing a single-case form or letter.')

            payload=build(self.db,kind,query='',selected_case=self.selected_case)

        elif kind=='final':payload=check_register(self.db,self.start.get(),self.end.get())

        else:payload=build(self.db,kind,self.start.get(),self.end.get(),self.query.get(),sort_city=operation=='city',merchant_filter=operation=='merchant',unposted=kind=='receipts' and operation=='create',output_mode=for_store(self.app.store))

        self.display(save_batch(self.db,payload))

    def open_saved(self):

        if not self.saved.selection():raise ValueError('Select a saved batch.')

        self.display(int(self.saved.selection()[0]))

    def print_current(self):

        if self.payload is None:raise ValueError('Create or open a saved preview first.')

        errors=[e for page in self.payload.get('original_pages',[]) for e in page['errors']]
        if errors:raise ValueError('Original layout needs review before printing:\n'+'\n'.join(dict.fromkeys(errors)))
        path=print_html(self.payload,self.app.store.path.parent/'legacy-print-previews',users.document_heading(self.db));webbrowser.open(path.resolve().as_uri())

    def export(self):

        if self.payload is None:raise ValueError('Create or open a preview first.')

        path=filedialog.asksaveasfilename(parent=self.win,defaultextension='.txt',filetypes=[('Text report','*.txt')])

        if path:Path(path).write_text(text_report(self.payload),encoding='utf-8')

    def post(self):

        if self.batch is None:raise ValueError('Open a saved batch first.')

        reason=simpledialog.askstring('Post test batch','Reason / review reference:',parent=self.win)

        if not reason:return

        if not messagebox.askyesno('Confirm test posting','Post this frozen batch? This updates test workflow history and the displayed case proof/letter markers where applicable. It does not send documents or move bank funds.',parent=self.win):return

        post_batch(self.db,self.batch,reason);self.workspace.refresh();self.display(self.batch)

    def modify_template(self,kind):

        login.require(self.db,True);win=tk.Toplevel(self.win);win.title('Modify report / label template');win.geometry('900x650');choice=tk.StringVar(value=kind)

        box=ttk.Combobox(win,textvariable=choice,values=list(SPEC),state='readonly');box.pack(anchor='w',padx=12,pady=8)

        ttk.Label(win,text='Letters/labels: {DEFENDANT}, {CASE_NO}, {ADDRESS}. Tabular reports: {REPORT_TITLE}, {START_DATE}, {END_DATE}, {RECORD_COUNT}, {TOTALS}. Imported wording may contain old names, addresses and legal text; review it before use.',wraplength=850).pack(padx=12)

        text=tk.Text(win,wrap='word');text.pack(fill='both',expand=True,padx=12,pady=8);state={}

        def load(e=None):

            row=self.db.execute('SELECT revision FROM legacy_function_templates WHERE kind=?',(choice.get(),)).fetchone();state['revision']=row[0] if row else -1;text.delete('1.0','end');text.insert('end',template(self.db,choice.get()))

        layout_frame=ttk.Frame(win);layout_frame.pack(fill='x',padx=12);layout_entries={}

        import reporting

        for i,key in enumerate(reporting.DEFAULT_LAYOUT):

            ttk.Label(layout_frame,text=key).grid(row=i//3,column=(i%3)*2,padx=4,pady=3);e=ttk.Entry(layout_frame,width=8);e.grid(row=i//3,column=(i%3)*2+1);layout_entries[key]=e

        original_load=load

        def load(e=None):

            original_load(e)

            row=self.db.execute('SELECT value FROM print_settings WHERE key=?',('legacy_label_layout_'+choice.get(),)).fetchone();layout=json.loads(row[0]) if row else reporting.DEFAULT_LAYOUT

            for k,e in layout_entries.items():e.delete(0,'end');e.insert(0,str(layout[k]))

            if choice.get() in ('labels','folder_labels'):layout_frame.pack(fill='x',padx=12)

            else:layout_frame.pack_forget()

        box.bind('<<ComboboxSelected>>',load);load()

        reason=ttk.Entry(win);reason.pack(fill='x',padx=12);ttk.Label(win,text='Change reason required. Saved batches keep their original template.').pack(anchor='w',padx=12)

        def save():

            def do():save_template(self.db,choice.get(),text.get('1.0','end-1c'),state['revision'],reason.get(),{k:e.get() for k,e in layout_entries.items()} if choice.get() in ('labels','folder_labels') else None);win.destroy()

            self.safe(do)

        ttk.Button(win,text='Save template',command=save).pack(pady=8)

class CheckManager:

    def __init__(self,center,action):

        self.action=action
        self.center=center;self.db=center.db;self.win=tk.Toplevel(center.win);self.win.title('Draft checks and final test register — NON-NEGOTIABLE');self.win.geometry('1000x600')

        ttk.Label(self.win,text='Enter verified payees and amounts. No DA/commission split is inferred. These are non-negotiable drafts; no bank transaction is performed.',wraplength=950).pack(anchor='w',padx=10,pady=8)

        self.tree=ttk.Treeview(self.win,columns=('id','number','date','payee','category','amount','posted'),show='headings')

        for key in self.tree['columns']:self.tree.heading(key,text=key);self.tree.column(key,width=130)

        self.tree.pack(fill='both',expand=True,padx=10,pady=8)

        bar=ttk.Frame(self.win);bar.pack(fill='x',padx=10,pady=8)

        for title,fn in [('New / append draft',lambda:self.edit()),('Edit selected draft',lambda:self.edit(self.selected())),('Preview selected draft',self.print_selected),('Print reviewed draft batch',self.print_group),('Create final register',self.final)]:ttk.Button(bar,text=title,command=lambda f=fn:center.safe(f)).pack(side='left',padx=5)

        self.category={'merchant':'Merchant','fund':'DA / Commission','single':'Defendant refund','defendant':'Defendant refund'}.get(action)

        self.refresh()

        if action in ('append','single','defendant'):self.center.safe(lambda:self.edit())

    def selected(self):

        if not self.tree.selection():raise ValueError('Select a draft check first.')

        return int(self.tree.selection()[0])

    def refresh(self):

        self.tree.delete(*self.tree.get_children())

        for row in self.db.execute('SELECT * FROM legacy_draft_checks ORDER BY id DESC'):

            if self.category and row['category']!=self.category:continue

            self.tree.insert('','end',iid=str(row['id']),values=[row['id'],row['check_no'],date_format.display(row['check_date']),row['payee'],row['category'],row['amount'],row['posted_batch']])

    def edit(self,check_id=None):

        login.require(self.db,True);row=self.db.execute('SELECT * FROM legacy_draft_checks WHERE id=?',(check_id,)).fetchone() if check_id else None

        win=tk.Toplevel(self.win);win.title('Draft check — explicit verified amounts');win.geometry('850x650');entries={}
        book=ttk.Notebook(win);book.pack(fill='both',expand=True);core=ttk.Frame(book);printing=ttk.Frame(book);book.add(core,text='Check details');book.add(printing,text='Print fields')

        defaults={'check_date':date_format.display(dt.date.today()),'category':self.category or 'Merchant'}
        if self.center.selected_case is not None:
            case=json.loads(lw.get(self.db,'WC_CASE',self.center.selected_case)['data_json'])
            defaults['case_refs']='WC_CASE source row '+str(self.center.selected_case)
            if self.action=='defendant':
                ids=[str(i['row']) for i in records(self.db,'WC_CASE') if str(i['data'].get('DEF_ID','')).strip()==str(case.get('DEF_ID','')).strip()] if str(case.get('DEF_ID','')).strip() else []
                defaults['case_refs']='WC_CASE source rows: '+', '.join(ids)
            defaults['payee']=case.get('MERCHANT','') if self.category=='Merchant' else (case.get('DEFENDANT','') if self.category=='Defendant refund' else '')

        labels={'payee':'Payee','check_no':'Draft check number','check_date':'Date MM-DD-YYYY','amount':'Amount','category':'Merchant / DA / Commission / Defendant refund','case_refs':'Case source rows / receipt references','evidence':'Evidence / allocation calculation','reason':'Change reason'}

        labels.update(print_address='Print street address',print_city='Print city',print_state='Print state',print_zip='Print ZIP',amount_words='Verified amount in words',definition_text='Verified case detail / ck_defs text')
        for i,(key,title) in enumerate(labels.items()):
            panel=core if i<8 else printing;line=i if i<8 else i-8

            ttk.Label(panel,text=title).grid(row=line,column=0,sticky='w',padx=10,pady=10)

            entry=ttk.Combobox(panel,values=['Merchant','DA / Commission','Defendant refund'],state='readonly',width=42) if key=='category' else ttk.Entry(panel,width=55)

            value=row[key] if row and key in row.keys() else defaults.get(key,'')
            if key=='check_date':value=date_format.display(value)

            if key=='category':entry.set(value)

            else:entry.insert(0,value)

            entry.grid(row=line,column=1,padx=10,pady=10);entries[key]=entry

        def commit():

            def do():save_check(self.db,{k:e.get() for k,e in entries.items() if k!='reason'},entries['reason'].get(),check_id,row['revision'] if row else None);self.refresh();win.destroy()

            self.center.safe(do)

        def words():
            entries['amount_words'].delete(0,'end');entries['amount_words'].insert(0,original_print.amount_words(lw.money(entries['amount'].get())))
        ttk.Button(printing,text='Generate words for review',command=lambda:self.center.safe(words)).grid(row=7,column=1,pady=10)
        ttk.Button(win,text='Save audited draft',command=commit).pack(pady=12)

    def print_selected(self):

        row=self.db.execute('SELECT * FROM legacy_draft_checks WHERE id=?',(self.selected(),)).fetchone();data=dict(row)

        payload={'kind':'checks','title':'Non-negotiable draft check','columns':list(data),'items':[{'table':'DRAFT_CHECK','row':row['id'],'revision':row['revision'],'data':data}],'documents':['NON-NEGOTIABLE — DRAFT CHECK\n\n'+ '\n'.join(k+': '+report_cell(k,data[k]) for k in ('check_no','check_date','payee','amount','category','case_refs','evidence'))],'totals':{},'warnings':[]}

        attach_original(self.db,payload)
        self.center.display(save_batch(self.db,payload));self.center.print_current()

    def print_group(self):
        payload=check_register(self.db,self.center.start.get(),self.center.end.get(),self.category)
        if not payload['items']:raise ValueError('No unposted drafts match this category/date range. Enter and review draft amounts first.')
        payload['kind']='checks';payload['title']='Non-negotiable draft check batch'
        payload['documents']=['NON-NEGOTIABLE - DRAFT CHECK\n\n'+'\n'.join(k+': '+report_cell(k,i['data'][k]) for k in ('check_no','check_date','payee','amount','category','case_refs','evidence')) for i in payload['items']]
        attach_original(self.db,payload)
        self.center.display(save_batch(self.db,payload));self.center.print_current()
    def final(self):self.center.display(save_batch(self.db,check_register(self.db,self.center.start.get(),self.center.end.get(),self.category)))

