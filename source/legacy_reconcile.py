"""Explicit legacy payment-to-case reconciliation with reviewable balance plans."""
import hashlib
import json
from decimal import Decimal
import tkinter as tk
from tkinter import ttk, messagebox
import login
import date_format
import user_audit
import historical_case_links

PAID=('REST_PAID','SFEE_PAID','FO_PAID','WD_PAID')
DUE=('CK_DUE','FEE_DUE','DA_DUE','WD_DUE')
MODES={'link_only':'Link only — balances already account for this payment',
       'apply':'Apply to target — verified not included in its balances',
       'transfer':'Transfer — reverse from selected old case and apply to target'}

def setup(db):
    db.executescript('''CREATE TABLE IF NOT EXISTS legacy_payment_links(
      payment_record INTEGER PRIMARY KEY,case_record INTEGER NOT NULL,revision INTEGER NOT NULL DEFAULT 0,
      basis TEXT NOT NULL,at TEXT NOT NULL,actor TEXT NOT NULL);
      CREATE INDEX IF NOT EXISTS legacy_links_target ON legacy_payment_links(case_record);
      CREATE TABLE IF NOT EXISTS legacy_reconciliations(id INTEGER PRIMARY KEY,at TEXT NOT NULL,
      actor TEXT NOT NULL,payment_record INTEGER NOT NULL,old_case_record INTEGER,target_case_record INTEGER NOT NULL,
      mode TEXT NOT NULL,evidence TEXT NOT NULL,reason TEXT NOT NULL,preview_json TEXT NOT NULL);
      CREATE TRIGGER IF NOT EXISTS preserve_reconciliation_update BEFORE UPDATE ON legacy_reconciliations
        BEGIN SELECT RAISE(ABORT,'Reconciliation history is append-only'); END;
      CREATE TRIGGER IF NOT EXISTS preserve_reconciliation_delete BEFORE DELETE ON legacy_reconciliations
        BEGIN SELECT RAISE(ABORT,'Reconciliation history is append-only'); END;''')

def explicit(db,payment):
    return db.execute('SELECT * FROM legacy_payment_links WHERE payment_record=?',(payment,)).fetchone()

def case_matches(db,number):
    return db.execute("SELECT * FROM working_legacy WHERE table_name='WC_CASE' AND deleted=0 AND json_extract(data_json,'$.CASE_NO')=?",(number,)).fetchall()

def resolve(db,payment,number):
    from legacy_work import get
    linked=explicit(db,payment)
    if linked:
        row=get(db,'WC_CASE',linked['case_record'])
        return [] if row['deleted'] else [row]
    return case_matches(db,number)

def digest(plan):
    return hashlib.sha256(json.dumps(plan,sort_keys=True,separators=(',',':')).encode()).hexdigest()

def preview(db,payment,target,mode,old_case=None):
    from legacy_work import get,money,validated,schema
    login.require(db)
    if mode not in MODES:raise ValueError('Choose a reconciliation action.')
    payment=int(payment);target=int(target);old_case=int(old_case) if old_case is not None else None
    p=get(db,'PAYMENTS',payment);pd=json.loads(p['data_json']);t=get(db,'WC_CASE',target)
    linked=explicit(db,payment)
    if linked and linked['case_record']==target:raise ValueError('Payment is already explicitly linked to that case. No further application is allowed.')
    if mode=='apply' and linked:raise ValueError('This payment already has an explicit link. Use transfer with its linked old case, or link only after reviewing balances.')
    if mode!='transfer' and old_case is not None:raise ValueError('An old case is selected only for a transfer.')
    if mode=='transfer':
        if old_case is None:raise ValueError('Select the old case to reverse.')
        if old_case==target:raise ValueError('Old and target case must differ.')
        if linked and linked['case_record']!=old_case:raise ValueError('The old case must be the current explicit linked case.')
    plan={'payment_record':payment,'target_case_record':target,'old_case_record':old_case,'mode':mode,
          'payment':dict(p),'current_link':dict(linked) if linked else None,'cases':[],'allocation':{},
          'warning':'No historical payment is added or deleted. Original backup records remain unchanged.'}
    requested=[(target,1)] if mode=='apply' else ([(old_case,-1),(target,1)] if mode=='transfer' else [(target,0)])
    if mode!='link_only':
        if p['deleted']:raise ValueError('A deleted/voided payment can be linked for review, but cannot be applied or transferred.')
        amounts=[money(pd.get(k,'')) for k in PAID]
        if any(a<0 for a in amounts) or sum(amounts)<=0:raise ValueError('Balance changes require positive, nonnegative supported allocations.')
        for key in ('CC_PAID','COURT_REST','OVERPAID','MISCL'):
            if money(pd.get(key,''))!=0:raise ValueError('Payment has '+key+' outside this balance model. Use link only and review its specialized accounting separately.')
        plan['allocation']={k:str(a) for k,a in zip(PAID,amounts)}
    for n,sign in requested:
        row=get(db,'WC_CASE',n);before=json.loads(row['data_json']);after=dict(before)
        if sign:
            if row['deleted']:raise ValueError('Balance changes require active cases; restore/review the archived case first.')
            for due,paid,amount in zip(DUE,PAID,amounts):
                if not amount:continue
                new_due=money(before.get(due,''))-sign*amount
                new_paid=money(before.get(paid,''))+sign*amount
                if new_due<0 or new_paid<0:raise ValueError('Preview would make '+due+' or '+paid+' negative in case source row '+str(n)+'. Review the recorded balances first.')
                after[due]=format(new_due,'.2f');after[paid]=format(new_paid,'.2f')
            if 'AMT_PAID' in before:
                total=money(before['AMT_PAID'])+sign*sum(amounts)
                if total<0:raise ValueError('Transfer would make AMT_PAID negative.')
                after['AMT_PAID']=format(total,'.2f')
            for field in schema(db,'WC_CASE'):
                key=field['name']
                if before.get(key)!=after.get(key):after[key]=validated(field,after[key])
        plan['cases'].append({'record_no':n,'revision':row['revision'],'deleted':row['deleted'],
                              'before':before,'after':after,'effect':sign})
    plan['signature']=digest(plan)
    return plan

def commit(db,plan,evidence,reason):
    from legacy_work import get,_write,now
    actor=login.require(db,True)
    if not evidence.strip() or not reason.strip():raise ValueError('Supporting evidence and a correction reason are both required.')
    if len(evidence)>20000 or len(reason)>2000:raise ValueError('Evidence/reason is too long.')
    try:
        db.execute('BEGIN IMMEDIATE')
        current=preview(db,plan['payment_record'],plan['target_case_record'],plan['mode'],plan['old_case_record'])
        if current!=plan:raise ValueError('The records or preview changed. Generate and review a new preview before saving.')
        for case in current['cases']:
            if case['effect']:
                _write(db,'WC_CASE',case['record_no'],case['after'],case['deleted'],case['revision'],'Reconciliation: '+reason,actor)
        p=current['payment'];data=json.loads(p['data_json'])
        _write(db,'PAYMENTS',p['record_no'],data,p['deleted'],p['revision'],'Explicit case reconciliation: '+reason,actor)
        prior=current['current_link'];revision=prior['revision']+1 if prior else 0
        db.execute('INSERT INTO legacy_payment_links(payment_record,case_record,revision,basis,at,actor) VALUES(?,?,?,?,?,?) ON CONFLICT(payment_record) DO UPDATE SET case_record=excluded.case_record,revision=excluded.revision,basis=excluded.basis,at=excluded.at,actor=excluded.actor',
                   (p['record_no'],current['target_case_record'],revision,current['mode'],now(),actor))
        cur=db.execute('INSERT INTO legacy_reconciliations(at,actor,payment_record,old_case_record,target_case_record,mode,evidence,reason,preview_json) VALUES(?,?,?,?,?,?,?,?,?)',
                   (now(),actor,p['record_no'],current['old_case_record'],current['target_case_record'],current['mode'],evidence.strip(),reason.strip(),json.dumps(current)))
        db.execute('INSERT INTO audit(at,operator,action,reference) VALUES(?,?,?,?)',(now(),actor,'RECONCILE_LEGACY_PAYMENT',str(cur.lastrowid)))
        db.commit();return cur.lastrowid
    except Exception:
        db.rollback();raise


def case_values(row):
    d=json.loads(row['data_json'])
    return (row['record_no'], 'Yes' if row['deleted'] else '',*[d.get(k,'') for k in ('CASE_NO','DEF_ID','DEFENDANT','MERCH_ID','MERCHANT','CK_NO','CK_DATE','CK_AMT','CK_DUE','FEE_DUE','DA_DUE','WD_DUE')])


class Screen:
    def __init__(self,workspace,payment=None):
        self.workspace=workspace;self.db=workspace.db;self.plan=None;self.payment=None;self.target=None;self.old=None
        login.require(self.db)
        user_audit.opened(self.db,'RECONCILIATION',f'Payment row {payment}' if payment is not None else 'Reconciliation workspace')
        self.win=tk.Toplevel(workspace.win);self.win.title('Reconcile payment to exact case | Administrator saves');self.win.geometry(f'{min(1250,self.win.winfo_screenwidth()-80)}x{min(850,self.win.winfo_screenheight()-100)}')
        self.book=ttk.Notebook(self.win);self.book.pack(fill='both',expand=True,padx=10,pady=10)
        selection=ttk.Frame(self.book);review=ttk.Frame(self.book);history=ttk.Frame(self.book)
        for page,name in [(selection,'1. Select payment and cases'),(review,'2. Evidence and balance preview'),(history,'Saved reconciliation history')]:self.book.add(page,text=name)
        self.selection=selection;self.review=review
        ttk.Label(selection,text='Select one exact payment source row. Choose cases using IDs, check details, receipts and supporting records; names alone do not establish a match.',wraplength=1150).pack(anchor='w',pady=6)
        bar=ttk.Frame(selection);bar.pack(fill='x');self.pquery=tk.StringVar();self.exceptions=tk.BooleanVar(value=True)
        ttk.Entry(bar,textvariable=self.pquery,width=35).pack(side='left');ttk.Checkbutton(bar,text='Unresolved exceptions only',variable=self.exceptions,command=self.find_payments).pack(side='left')
        ttk.Button(bar,text='Search payments',command=lambda:self.safe(self.find_payments)).pack(side='left')
        self.ptree=self.tree(selection,('row','deleted','case','receipt','date','defendant','merchant','restitution','fee','DA','withdrawal'),height=6)
        self.ptree.bind('<<TreeviewSelect>>',self.pick_payment)
        ttk.Label(selection,text='Search candidate cases (includes archived rows). Then select a row and assign its role.').pack(anchor='w',pady=6)
        bar=ttk.Frame(selection);bar.pack(fill='x');self.cquery=tk.StringVar();ttk.Entry(bar,textvariable=self.cquery,width=35).pack(side='left')
        ttk.Button(bar,text='Search cases',command=lambda:self.safe(self.find_cases)).pack(side='left')
        ttk.Button(bar,text='Use selected as TARGET',command=lambda:self.safe(lambda:self.pick_case(False))).pack(side='left',padx=8)
        ttk.Button(bar,text='Use selected as OLD case',command=lambda:self.safe(lambda:self.pick_case(True))).pack(side='left')
        ttk.Button(bar,text='Clear old case',command=lambda:self.clear_old()).pack(side='left',padx=8)
        self.ctree=self.tree(selection,('row','deleted','case','def_id','defendant','merch_id','merchant','check','check_date','check_amount','check_due','fee_due','DA_due','withdrawal_due'),height=7)
        self.summary=tk.StringVar();ttk.Label(selection,textvariable=self.summary,wraplength=1150).pack(anchor='w',pady=8)
        ttk.Button(selection,text='Continue to evidence / preview',command=lambda:self.book.select(review)).pack(anchor='e',pady=6)
        ttk.Label(review,text='Choose how the payment affects balances. Linking alone is appropriate only when your evidence shows the recorded balances already include it.',wraplength=1150).pack(anchor='w',pady=6)
        self.mode=tk.StringVar(value='link_only')
        for key,title in MODES.items():ttk.Radiobutton(review,text=title,variable=self.mode,value=key,command=self.invalidate).pack(anchor='w')
        ttk.Label(review,text='Supporting evidence — receipt/register references, dates, check and party IDs, and why balances already include or exclude this payment:').pack(anchor='w',pady=(10,0))
        self.evidence=tk.Text(review,height=4,wrap='word');self.evidence.pack(fill='x')
        ttk.Label(review,text='Correction reason:').pack(anchor='w');self.reason=ttk.Entry(review);self.reason.pack(fill='x')
        ttk.Button(review,text='Generate balance preview',command=lambda:self.safe(self.make_preview)).pack(anchor='w',pady=8)
        self.preview_text=tk.Text(review,height=10,wrap='word',state='disabled');self.preview_text.pack(fill='both',expand=True)
        self.confirm=tk.BooleanVar();ttk.Checkbutton(review,text='I reviewed the selected source rows, evidence, and balance effects.',variable=self.confirm).pack(anchor='w',pady=6)
        self.save_button=ttk.Button(review,text='Save audited reconciliation (Administrator)',command=lambda:self.safe(self.save),state='disabled');self.save_button.pack(anchor='e',pady=8)
        self.log=tk.Text(history,wrap='word');self.log.pack(fill='both',expand=True);ttk.Button(history,text='Refresh history',command=self.show_history).pack(pady=8)
        if payment is not None:
            self.exceptions.set(False);self.pquery.set(str(payment))
        self.find_payments(exact=payment)
        if payment is not None and self.ptree.exists(str(payment)):
            self.ptree.selection_set(str(payment));self.pick_payment()
        self.find_cases();self.show_history();self.update_summary()
        if getattr(workspace.app.store, 'division', None) == 'office1':
            historical_page = ttk.Frame(self.book, padding=10)
            self.book.add(historical_page, text='Historical case links')
            self.historical_links = historical_case_links.Panel(self, historical_page)
    def tree(self,parent,columns,height):
        holder=ttk.Frame(parent);holder.pack(fill='both',expand=True)
        tree=ttk.Treeview(holder,columns=columns,show='headings',height=height)
        for c in columns:tree.heading(c,text=c);tree.column(c,width=115,stretch=False)
        tree.grid(row=0,column=0,sticky='nsew');y=ttk.Scrollbar(holder,command=tree.yview);y.grid(row=0,column=1,sticky='ns');x=ttk.Scrollbar(holder,orient='horizontal',command=tree.xview);x.grid(row=1,column=0,sticky='ew');tree.configure(yscrollcommand=y.set,xscrollcommand=x.set);holder.rowconfigure(0,weight=1);holder.columnconfigure(0,weight=1)
        return tree
    def safe(self,fn):
        try:fn()
        except Exception as e:messagebox.showerror('Reconciliation',str(e),parent=self.win)
    def invalidate(self):
        self.plan=None;self.confirm.set(False);self.save_button.configure(state='disabled')
    def find_payments(self,exact=None):
        self.ptree.delete(*self.ptree.get_children())
        sql="SELECT p.* FROM working_legacy p LEFT JOIN legacy_payment_links l ON l.payment_record=p.record_no WHERE p.table_name='PAYMENTS' AND (p.data_json LIKE ? OR CAST(p.record_no AS TEXT)=?)"
        q=self.pquery.get();args=['%'+q+'%',q]
        if exact is not None:
            sql+=' AND p.record_no=?';args.append(exact)
        if self.exceptions.get():sql+=" AND p.deleted=0 AND l.payment_record IS NULL AND (SELECT COUNT(*) FROM working_legacy c WHERE c.table_name='WC_CASE' AND c.deleted=0 AND json_extract(c.data_json,'$.CASE_NO')=json_extract(p.data_json,'$.CASE_NO'))!=1"
        for r in self.db.execute(sql+' ORDER BY p.record_no LIMIT 200',args):
            d=json.loads(r['data_json'])
            d['DATE'] = date_format.display(d.get('DATE',''))
            self.ptree.insert('','end',iid=str(r['record_no']),values=[r['record_no'],r['deleted']]+[d.get(k,'') for k in ('CASE_NO','RECEIPT_NO','DATE','DEFENDANT','MERCHANT',*PAID)])
    def pick_payment(self,event=None):
        if not self.ptree.selection():return
        self.payment=int(self.ptree.selection()[0]);self.target=None;self.old=None;self.invalidate();self.update_summary();self.show_history()
    def find_cases(self):
        self.ctree.delete(*self.ctree.get_children());q=self.cquery.get()
        for r in self.db.execute("SELECT * FROM working_legacy WHERE table_name='WC_CASE' AND (data_json LIKE ? OR CAST(record_no AS TEXT)=?) ORDER BY record_no LIMIT 200",('%'+q+'%',q)):
            self.ctree.insert('','end',iid=str(r['record_no']),values=case_values(r))
    def pick_case(self,old):
        if not self.ctree.selection():raise ValueError('Select a candidate case first.')
        n=int(self.ctree.selection()[0])
        if old:self.old=n
        else:self.target=n
        self.invalidate();self.update_summary()
    def clear_old(self):self.old=None;self.invalidate();self.update_summary()
    def update_summary(self):
        linked=explicit(self.db,self.payment) if self.payment is not None else None
        current=str(linked['case_record']) if linked else 'none (legacy CASE_NO match only)'
        self.summary.set(f'Current explicit case link: {current}. Payment source row: {self.payment or "none"} | Target WC_CASE source row: {self.target or "none"} | Old WC_CASE source row: {self.old or "none"}. Lists show first 200 matches; refine the search when needed.')
    def make_preview(self):
        if self.payment is None or self.target is None:raise ValueError('Select a payment and target case first.')
        self.invalidate()
        self.plan=preview(self.db,self.payment,self.target,self.mode.get(),self.old)
        p=json.loads(self.plan['payment']['data_json']);lines=[MODES[self.mode.get()],f'Payment source row {self.payment}, original/current CASE_NO {p.get("CASE_NO","")}, receipt {p.get("RECEIPT_NO","")}, date {date_format.display(p.get("DATE",""))}',f'Payment defendant: {p.get("DEFENDANT","")}; merchant: {p.get("MERCHANT","")}', 'Payment allocations: '+', '.join(k+'='+str(p.get(k,'')) for k in PAID),self.plan['warning'],'']
        if self.mode.get()=='link_only':lines.append('BALANCE EFFECT: ZERO. Only an explicit case link is recorded. The legacy CASE_NO field is retained.')
        for c in self.plan['cases']:
            b=c['before'];a=c['after'];lines += ['',f'CASE source row {c["record_no"]}, case {b.get("CASE_NO","")}, defendant ID {b.get("DEF_ID","")}: {b.get("DEFENDANT","")}',f'Merchant ID {b.get("MERCH_ID","")}: {b.get("MERCHANT","")}; check {b.get("CK_NO","")} date {date_format.display(b.get("CK_DATE",""))} amount {b.get("CK_AMT","")}']
            for k in (*DUE,*PAID,'AMT_PAID'):lines.append(k+': '+str(b.get(k,''))+' → '+str(a.get(k,'')))
        self.preview_text.configure(state='normal');self.preview_text.delete('1.0','end');self.preview_text.insert('end','\n'.join(lines));self.preview_text.configure(state='disabled');self.save_button.configure(state='normal')
    def save(self):
        if self.plan is None or not self.confirm.get():raise ValueError('Generate and acknowledge the preview before saving.')
        if not self.evidence.get('1.0','end-1c').strip() or not self.reason.get().strip():raise ValueError('Enter supporting evidence and a correction reason.')
        if not messagebox.askyesno('Save reviewed reconciliation','Save this exact payment-to-case link and the displayed balance effects?',parent=self.win):return
        try:
            n=commit(self.db,self.plan,self.evidence.get('1.0','end-1c'),self.reason.get())
        except Exception:
            self.invalidate();raise
        self.invalidate();self.find_payments();self.find_cases();self.show_history();self.workspace.refresh()
        messagebox.showinfo('Saved','Audited reconciliation '+str(n)+' saved. Original backup records are unchanged.',parent=self.win)
    def show_history(self):
        self.log.configure(state='normal');self.log.delete('1.0','end')
        args=() if self.payment is None else (self.payment,)
        where='' if self.payment is None else ' WHERE payment_record=?'
        for r in self.db.execute('SELECT * FROM legacy_reconciliations'+where+' ORDER BY id DESC LIMIT 100',args):self.log.insert('end',json.dumps(dict(r),indent=2)+'\n\n')
        self.log.configure(state='disabled')
