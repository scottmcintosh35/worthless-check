"""Bank-code directory preserving duplicate codes from BANKCODE.DBF."""
import datetime as dt
import json
from pathlib import Path
import re
import sqlite3
import tkinter as tk
from tkinter import ttk, messagebox
import login


def setup(db):
    db.executescript('''CREATE TABLE IF NOT EXISTS bank_codes (
      id INTEGER PRIMARY KEY AUTOINCREMENT,source_key TEXT UNIQUE,
      code TEXT NOT NULL,name TEXT NOT NULL,active INTEGER NOT NULL CHECK(active IN(0,1)));
      CREATE INDEX IF NOT EXISTS bank_code_lookup ON bank_codes(code);''')
    if 'bank_id' not in [r[1] for r in db.execute('PRAGMA table_info(cases)')]:
        db.execute('ALTER TABLE cases ADD COLUMN bank_id INTEGER REFERENCES bank_codes(id)')
    seed=json.loads((Path(__file__).parent/'bankcode-seed.json').read_text(encoding='utf-8'))
    with db:
        for row in seed:
            db.execute('INSERT OR IGNORE INTO bank_codes(source_key,code,name,active) VALUES(?,?,?,?)',
                ('BANKCODE:'+str(row['source_row']),row['CODE'].strip(),row['BANK'].rstrip(),int(not row['deleted'])))


def list_banks(db,search='',include_inactive=False):
    return db.execute('''SELECT * FROM bank_codes WHERE (active=1 OR ?=1)
      AND (code LIKE ? OR name LIKE ?) ORDER BY code COLLATE BINARY,name,id''',
      (int(include_inactive),'%'+search+'%','%'+search+'%')).fetchall()


def save_bank(db,code,name,active=True,bank_id=None):
    actor=login.require(db,True)
    code,name=code.strip(),name.strip()
    if not re.fullmatch(r'[A-Za-z0-9]{1,3}',code):
        raise ValueError('Enter a bank code of 1 to 3 letters or digits. Leading zeros are preserved.')
    if not name or len(name)>100:
        raise ValueError('Enter a bank name of up to 100 characters.')
    with db:
        old=db.execute('SELECT code FROM bank_codes WHERE id=?',(bank_id,)).fetchone() if bank_id is not None else None
        if bank_id is not None and old is None:
            raise ValueError('Bank entry not found.')
        if old is None or code!=old[0]:
            if db.execute('SELECT 1 FROM bank_codes WHERE code=? COLLATE NOCASE',(code,)).fetchone():
                raise ValueError('That code already exists. Select and edit the existing entry.')
        if bank_id is None:
            bank_id=db.execute('INSERT INTO bank_codes(code,name,active) VALUES(?,?,?)',(code,name,int(active))).lastrowid
            action='ADD_BANK_CODE'
        else:
            db.execute('UPDATE bank_codes SET code=?,name=?,active=? WHERE id=?',(code,name,int(active),bank_id))
            action='EDIT_BANK_CODE'
        db.execute('INSERT INTO audit(at,operator,action,reference) VALUES(?,?,?,?)',
            (dt.datetime.now(dt.timezone.utc).isoformat(),actor,action,str(bank_id)))
    return bank_id


class BankDirectory:
    def __init__(self,app):
        self.db=app.store.db
        self.win=tk.Toplevel(app.root)
        self.win.title('Bank Codes')
        self.win.geometry('760x580')
        bar=ttk.Frame(self.win)
        bar.pack(fill='x',padx=12,pady=12)
        ttk.Label(bar,text='Code or bank:').pack(side='left')
        self.search=tk.StringVar()
        entry=ttk.Entry(bar,textvariable=self.search,width=28)
        entry.pack(side='left',padx=8)
        entry.bind('<Return>',lambda e:self.refresh())
        ttk.Button(bar,text='Search',command=self.refresh).pack(side='left')
        ttk.Button(bar,text='Add Bank',command=self.edit).pack(side='left',padx=5)
        ttk.Button(bar,text='Edit selected',command=self.edit_selected).pack(side='left')
        self.inactive=tk.BooleanVar(value=False)
        ttk.Checkbutton(self.win,text='Include inactive banks',variable=self.inactive,command=self.refresh).pack(anchor='w',padx=12)
        frame=ttk.Frame(self.win)
        frame.pack(fill='both',expand=True,padx=12,pady=12)
        self.tree=ttk.Treeview(frame,columns=('code','bank','active'),show='headings')
        for key,label,width in [('code','Code',90),('bank','Bank',520),('active','Active',70)]:
            self.tree.heading(key,text=label)
            self.tree.column(key,width=width)
        scroll=ttk.Scrollbar(frame,command=self.tree.yview)
        self.tree.configure(yscrollcommand=scroll.set)
        scroll.pack(side='right',fill='y')
        self.tree.pack(fill='both',expand=True)
        self.tree.bind('<Double-1>',lambda e:self.edit_selected())
        self.win.bind('<Control-n>',lambda e:self.edit())
        self.status=tk.StringVar()
        ttk.Label(self.win,textvariable=self.status).pack(anchor='w',padx=12,pady=10)
        self.refresh()

    def refresh(self):
        self.tree.delete(*self.tree.get_children())
        rows=list_banks(self.db,self.search.get(),self.inactive.get())
        for r in rows:
            self.tree.insert('','end',iid=str(r['id']),values=(r['code'],r['name'],'Yes' if r['active'] else 'No'))
        self.status.set(f'{len(rows)} entries. Original duplicate codes are retained as separate bank entries.')

    def edit_selected(self):
        if not self.tree.selection():
            messagebox.showinfo('Select bank','Select a bank entry first.',parent=self.win)
            return
        self.edit(int(self.tree.selection()[0]))

    def edit(self,bank_id=None):
        row=self.db.execute('SELECT * FROM bank_codes WHERE id=?',(bank_id,)).fetchone() if bank_id is not None else None
        win=tk.Toplevel(self.win)
        win.title('Add Bank' if row is None else 'Edit Bank')
        entries=[]
        for i,(label,value) in enumerate([('Code',row['code'] if row else ''),('Bank',row['name'] if row else '')]):
            ttk.Label(win,text=label).grid(row=i,column=0,padx=12,pady=12)
            entry=ttk.Entry(win,width=55)
            entry.insert(0,value)
            entry.grid(row=i,column=1,padx=12,pady=12)
            entries.append(entry)
        active=tk.BooleanVar(value=bool(row['active']) if row else True)
        ttk.Checkbutton(win,text='Active',variable=active).grid(row=2,column=1,sticky='w',padx=12)
        def save():
            try:
                save_bank(self.db,entries[0].get(),entries[1].get(),active.get(),bank_id)
                self.refresh()
                win.destroy()
            except (ValueError,sqlite3.Error) as error:
                messagebox.showerror('Cannot save bank',str(error),parent=win)
        ttk.Button(win,text='Save Bank',command=save).grid(row=3,column=1,padx=12,pady=15,sticky='e')
