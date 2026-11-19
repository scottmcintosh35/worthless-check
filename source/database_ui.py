"""Database menu tools for the editable review database."""
import tkinter as tk
from tkinter import ttk,messagebox,simpledialog
from decimal import Decimal,InvalidOperation
import sqlite3
import database_tools as tools
import login


class DatabaseUI:
    def __init__(self,app):
        self.app,self.store,self.db=app,app.store,app.store.db

    def error(self,error,parent=None):
        messagebox.showerror('Database action',str(error),parent=parent or self.app.root)

    def reason(self,parent):
        operator=simpledialog.askstring('Operator','Operator initials:',parent=parent)
        if operator is None:
            return None
        reason=simpledialog.askstring('Reason','Reason for this action:',parent=parent)
        return (reason,operator) if reason is not None else None

    def table(self,title,columns,rows):
        win=tk.Toplevel(self.app.root)
        win.title(title)
        win.geometry('1000x520')
        tree=ttk.Treeview(win,columns=[c[0] for c in columns],show='headings')
        for key,label,width in columns:
            tree.heading(key,text=label)
            tree.column(key,width=width)
        scroll=ttk.Scrollbar(win,command=tree.yview)
        scroll.pack(side='right',fill='y')
        tree.configure(yscrollcommand=scroll.set)
        tree.pack(fill='both',expand=True,padx=12,pady=12)
        for row in rows:
            tree.insert('','end',iid=str(row[0]),values=row)
        return win,tree

    def numbering(self,kind):
        row=self.db.execute('SELECT * FROM number_counters WHERE kind=?',(kind,)).fetchone()
        title={'case':'Case Number','adjustment':'Adjustment Number','receipt':'Receipt Number','defendant':'Defendant ID','merchant':'Merchant ID'}[kind]
        win,entries=self.app.form(title,['Prefix','Minimum digits','Next number'],[row['prefix'],str(row['width']),str(row['next_value'])])
        ttk.Label(win,text='Applies to future records only. Numbers cannot be moved backward.').grid(row=3,column=0,columnspan=2,padx=15,pady=10)
        def save():
            try:
                tools.configure_number(self.db,kind,entries[0].get(),int(entries[1].get()),int(entries[2].get()))
                win.destroy()
            except (ValueError,sqlite3.Error) as e:
                self.error(e,win)
        ttk.Button(win,text='Save numbering',command=save).grid(row=4,column=1,padx=15,pady=15)
        if kind=='merchant':
            ttk.Button(win,text='Merchant directory',command=self.merchants).grid(row=4,column=0,padx=15,pady=15)

    def merchants(self):
        rows=[tuple(r) for r in self.db.execute('SELECT id,name,address,city,state,zip,phone,contact,active FROM merchants ORDER BY name')]
        win,tree=self.table('Merchant directory',[('id','ID',65),('name','Merchant',200),('address','Address',200),('city','City',120),('state','State',50),('zip','ZIP',80),('phone','Phone',100),('contact','Contact',100),('active','Active',60)],rows)
        def edit(new=True):
            if not new and not tree.selection():
                return
            row=self.db.execute('SELECT * FROM merchants WHERE id=?',(int(tree.selection()[0]),)).fetchone() if not new else None
            keys=['name','address','city','state','zip','phone','contact']
            form,entries=self.app.form('Merchant details',['Merchant name','Address','City','State','ZIP','Phone','Contact'],[row[k] if row else '' for k in keys])
            active=tk.BooleanVar(value=bool(row['active']) if row else True)
            ttk.Checkbutton(form,text='Active',variable=active).grid(row=7,column=1,padx=15,pady=8)
            def save():
                try:
                    tools.save_merchant(self.db,*[e.get() for e in entries],active=active.get(),merchant_id=row['id'] if row else None)
                    form.destroy()
                    win.destroy()
                    self.merchants()
                except (ValueError,sqlite3.Error) as e:
                    self.error(e,form)
            ttk.Button(form,text='Save merchant',command=save).grid(row=8,column=1,pady=15)
        ttk.Button(win,text='Add merchant',command=edit).pack(side='left',padx=12,pady=10)
        ttk.Button(win,text='Edit selected',command=lambda:edit(False)).pack(side='left',padx=12,pady=10)

    def adjustments(self):
        rows=[tuple(r) for r in self.db.execute('''SELECT a.id,a.number,c.case_no,a.at,a.operator,a.reason,
            printf('%.2f',(a.restitution+a.merchant_fee+a.da_fee+a.withdrawal_fee)/100.0),COALESCE(a.reverses_id,'')
            FROM adjustments a JOIN cases c ON c.id=a.case_id ORDER BY a.id''')]
        win,tree=self.table('Adjustment records',[('id','ID',55),('number','Adjustment',120),('case','Case',120),('date','UTC timestamp',180),('operator','Operator',75),('reason','Reason',240),('amount','Charge change',100),('reverse','Reverses ID',90)],rows)
        def new():
            try:
                cid=self.app.selected()
            except ValueError as e:
                self.error(e,win)
                return
            case=self.store.case(cid)
            form,entries=self.app.form('Adjust charges: '+case['case_no'],['Restitution change','Merchant fee change','DA fee change','Withdrawal fee change','Operator initials','Reason'],['0.00']*4+['DEMO',''])
            ttk.Label(form,text='Positive adds a charge; negative reduces it. Payments are kept separately.').grid(row=6,column=0,columnspan=2,padx=15,pady=10)
            def save():
                try:
                    deltas=[]
                    for entry in entries[:4]:
                        amount=Decimal(entry.get())
                        if not amount.is_finite() or abs(amount)>Decimal('99999999.99') or amount!=amount.quantize(Decimal('.01')):
                            raise ValueError('Enter signed dollar amounts with at most two decimal places.')
                        deltas.append(int(amount*100))
                    tools.adjust(self.store,cid,deltas,entries[5].get(),entries[4].get())
                    form.destroy()
                    win.destroy()
                    self.app.refresh()
                    self.adjustments()
                except (ValueError,InvalidOperation,sqlite3.Error) as e:
                    self.error(e,form)
            ttk.Button(form,text='Save adjustment',command=save).grid(row=7,column=1,pady=15)
        def reverse():
            if not tree.selection():
                return
            why=self.reason(win)
            if why:
                try:
                    tools.reverse_adjustment(self.store,int(tree.selection()[0]),*why)
                    win.destroy()
                    self.app.refresh()
                    self.adjustments()
                except (ValueError,sqlite3.Error) as e:
                    self.error(e,win)
        ttk.Button(win,text='New adjustment for selected main-window case',command=new).pack(side='left',padx=12,pady=10)
        ttk.Button(win,text='Reverse selected adjustment',command=reverse).pack(side='left',padx=8,pady=10)

    def deleted(self,payments=False):
        if payments:
            rows=[tuple(r) for r in self.db.execute('SELECT p.id,p.receipt_code,c.case_no,p.paid_date,p.void_reason FROM payments p JOIN cases c ON c.id=p.case_id WHERE voided=1')]
            columns=[('id','Payment ID',80),('receipt','Receipt',170),('case','Case',140),('date','Payment date',120),('reason','Void reason',350)]
        else:
            rows=[tuple(r) for r in self.db.execute('SELECT id,case_no,defendant,merchant,archive_reason FROM cases WHERE archived=1')]
            columns=[('id','Case ID',70),('case','Case',140),('defendant','Defendant',220),('merchant','Merchant',220),('reason','Archive reason',300)]
        win,tree=self.table('Deleted Payments (voided)' if payments else 'Deleted Records (archived cases)',columns,rows)
        def restore():
            if not tree.selection():
                return
            why=self.reason(win)
            if why:
                try:
                    fn=tools.void_payment if payments else tools.archive_case
                    fn(self.store,int(tree.selection()[0]),*why,restore=True)
                    win.destroy()
                    self.app.refresh()
                    self.deleted(payments)
                except (ValueError,sqlite3.Error) as e:
                    self.error(e,win)
        ttk.Button(win,text='Restore selected',command=restore).pack(anchor='w',padx=12,pady=10)

    def reindex(self,adjustments_only=False):
        try:
            path,result=tools.reindex(self.store,adjustments_only)
            messagebox.showinfo('Reindex complete',f'Database check: {result}\nBackup saved to:\n{path}',parent=self.app.root)
        except (OSError,sqlite3.Error) as e:
            self.error(e)

    def schema(self):
        win=tk.Toplevel(self.app.root)
        win.title('Modify table structures - optional custom columns')
        win.geometry('800x520')
        table=ttk.Combobox(win,values=['cases','defendants','merchants'],state='readonly')
        table.current(0)
        table.pack(anchor='w',padx=12,pady=12)
        tree=ttk.Treeview(win,columns=('column','type','required'),show='headings')
        for key,label in [('column','Column'),('type','Type'),('required','Required')]:
            tree.heading(key,text=label)
        tree.pack(fill='both',expand=True,padx=12,pady=8)
        def refresh(event=None):
            tree.delete(*tree.get_children())
            for r in self.db.execute('PRAGMA table_info('+table.get()+')'):
                tree.insert('','end',values=(r[1],r[2],bool(r[3])))
        table.bind('<<ComboboxSelected>>',refresh)
        def add():
            name=simpledialog.askstring('Add custom field','Field name, starting with custom_:',initialvalue='custom_',parent=win)
            if name is None:
                return
            typ=simpledialog.askstring('Field type','TEXT, INTEGER or REAL:',initialvalue='TEXT',parent=win)
            if typ is None:
                return
            try:
                path=tools.add_custom_column(self.store,table.get(),name.strip(),typ.strip().upper())
                refresh()
                messagebox.showinfo('Field added','Optional storage column added. It is not automatically added to entry forms.\nBackup: '+str(path),parent=win)
            except (ValueError,OSError,sqlite3.Error) as e:
                self.error(e,win)
        ttk.Label(win,text='Inspect fields or add optional custom_ columns. Existing column types cannot be changed or removed.').pack(padx=12,pady=8)
        ttk.Button(win,text='Add optional custom field',command=add).pack(pady=12)
        refresh()

    def supervisor(self):
        win=tk.Toplevel(self.app.root)
        win.title('Supervisor Actions - review prototype')
        ttk.Label(win,text='Administrator maintenance tools. Login is required after the first Administrator account is created.',wraplength=600).pack(padx=15,pady=15)
        def archive():
            try:
                cid=self.app.selected()
                why=self.reason(win)
                if why:
                    tools.archive_case(self.store,cid,*why)
                    self.app.refresh()
                    messagebox.showinfo('Archived','Case moved to View Deleted Records.',parent=win)
            except (ValueError,sqlite3.Error) as e:
                self.error(e,win)
        def void():
            value=simpledialog.askstring('Void payment','Receipt number or payment ID:',parent=win)
            if value is None:
                return
            row=self.db.execute('SELECT id FROM payments WHERE receipt_code=?',(value.strip(),)).fetchone()
            if row is None and value.strip().isdigit():
                row=self.db.execute('SELECT id FROM payments WHERE id=?',(int(value),)).fetchone()
            if row is None:
                self.error(ValueError('Payment not found.'),win)
                return
            why=self.reason(win)
            if why:
                try:
                    tools.void_payment(self.store,row['id'],*why)
                    self.app.refresh()
                    messagebox.showinfo('Voided','Payment retained in View Deleted Payments. Its receipt is marked VOID.',parent=win)
                except (ValueError,sqlite3.Error) as e:
                    self.error(e,win)
        def audit():
            rows=[tuple(r) for r in self.db.execute('SELECT id,at,operator,action,reference FROM audit ORDER BY id DESC LIMIT 1000')]
            self.table('Audit history - latest 1,000 actions',[('id','ID',65),('at','UTC timestamp',230),('operator','Operator',100),('action','Action',220),('reference','Reference / reason',350)],rows)
        for label,fn in [('Archive selected main-window case',archive),('Void payment',void),('View audit history',audit),('Back up database',self.app.backup),('Run integrity check',lambda:messagebox.showinfo('Database integrity',self.db.execute('PRAGMA integrity_check').fetchone()[0],parent=win))]:
            ttk.Button(win,text=label,command=fn).pack(fill='x',padx=15,pady=7)
