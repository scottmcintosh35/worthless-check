"""WC disposition codes and ZIP/city/state reference lists."""
import datetime as dt
import json
from pathlib import Path
import re
import sqlite3
import tkinter as tk
from tkinter import ttk,messagebox
import login

CONFIG={
    'wc':('WC Codes','wc_codes',[('code','Code',90),('description','Description',500),('active','Active',80)]),
    'zip':('ZIP Codes','zip_codes',[('zip','ZIP',110),('city','City',360),('state','State',90),('active','Active',80)])
}


def setup(db):
    db.executescript('''CREATE TABLE IF NOT EXISTS lookup_seeds(name TEXT PRIMARY KEY);
    CREATE TABLE IF NOT EXISTS wc_codes(id INTEGER PRIMARY KEY AUTOINCREMENT,source_key TEXT UNIQUE,
      code TEXT NOT NULL,description TEXT NOT NULL,active INTEGER NOT NULL CHECK(active IN(0,1)));
    CREATE TABLE IF NOT EXISTS zip_codes(id INTEGER PRIMARY KEY AUTOINCREMENT,source_key TEXT UNIQUE,
      zip TEXT NOT NULL,city TEXT NOT NULL,state TEXT NOT NULL,active INTEGER NOT NULL CHECK(active IN(0,1)));
    CREATE INDEX IF NOT EXISTS zip_search ON zip_codes(zip);
    CREATE INDEX IF NOT EXISTS city_search ON zip_codes(city COLLATE NOCASE);''')
    for kind,filename in [('wc','wc-code-seed.json'),('zip','zip-code-seed.json')]:
        if db.execute('SELECT 1 FROM lookup_seeds WHERE name=?',(kind,)).fetchone():
            continue
        rows=json.loads((Path(__file__).parent/filename).read_text(encoding='utf-8'))
        with db:
            if kind=='wc':
                db.executemany('INSERT OR IGNORE INTO wc_codes(source_key,code,description,active) VALUES(?,?,?,?)',
                    [(str(r['source_row']),r['CODE'].strip(),r['DESCR'].rstrip(),int(not r['deleted'])) for r in rows])
            else:
                db.executemany('INSERT OR IGNORE INTO zip_codes(source_key,zip,city,state,active) VALUES(?,?,?,?,?)',
                    [(str(r['source_row']),r['ZIP'].strip(),r['CITY'].rstrip(),r['STATE'].strip(),int(not r['deleted'])) for r in rows])
            db.execute('INSERT INTO lookup_seeds(name) VALUES(?)',(kind,))


def search(db,kind,text='',inactive=False,page=0):
    _,table,columns=CONFIG[kind]
    keys=[key for key,_,_ in columns if key!='active']
    where=' WHERE (active=1 OR ?=1) AND ('+' OR '.join(key+' LIKE ?' for key in keys)+')'
    args=[int(inactive)]+['%'+text.strip()+'%']*len(keys)
    count=db.execute('SELECT COUNT(*) FROM '+table+where,args).fetchone()[0]
    order='code,description,id' if kind=='wc' else 'zip,city,state,id'
    rows=db.execute('SELECT * FROM '+table+where+' ORDER BY '+order+' LIMIT 250 OFFSET ?',args+[max(page,0)*250]).fetchall()
    return count,rows


def save(db,kind,values,active=True,record_id=None):
    actor=login.require(db,True)
    _,table,columns=CONFIG[kind]
    keys=[key for key,_,_ in columns if key!='active']
    data={key:str(values.get(key,'')).strip() for key in keys}
    if kind=='wc':
        if not re.fullmatch(r'[A-Za-z0-9]{1,2}',data['code']) or not data['description'] or len(data['description'])>100:
            raise ValueError('Enter a 1-2 character code and a description of up to 100 characters.')
    else:
        data['state']=data['state'].upper()
        if not re.fullmatch(r'[0-9]{5}',data['zip']) or not re.fullmatch(r'[A-Z]{2}',data['state']) or not data['city'] or len(data['city'])>100:
            raise ValueError('Enter a five-digit ZIP, a city, and a two-letter state.')
    with db:
        old=db.execute('SELECT * FROM '+table+' WHERE id=?',(record_id,)).fetchone() if record_id is not None else None
        if record_id is not None and old is None:
            raise ValueError('Entry not found.')
        duplicate_keys=['code'] if kind=='wc' else keys
        changed=old is None or any(str(old[k]).casefold()!=data[k].casefold() for k in duplicate_keys)
        if changed and db.execute('SELECT 1 FROM '+table+' WHERE '+' AND '.join(k+'=? COLLATE NOCASE' for k in duplicate_keys),[data[k] for k in duplicate_keys]).fetchone():
            raise ValueError('This entry already exists. Select and edit the existing entry.')
        if record_id is None:
            record_id=db.execute('INSERT INTO '+table+'('+','.join(keys)+',active) VALUES('+','.join('?' for _ in range(len(keys)+1))+')',
                [data[k] for k in keys]+[int(active)]).lastrowid
        else:
            db.execute('UPDATE '+table+' SET '+','.join(k+'=?' for k in keys)+',active=? WHERE id=?',
                [data[k] for k in keys]+[int(active),record_id])
        db.execute('INSERT INTO audit(at,operator,action,reference) VALUES(?,?,?,?)',
            (dt.datetime.now(dt.timezone.utc).isoformat(),actor,'SAVE_'+table.upper(),str(record_id)))
    return record_id


class Directory:
    def __init__(self,parent,db,kind,on_select=None):
        self.db,self.kind,self.on_select=db,kind,on_select
        self.page=0
        title,self.table,self.columns=CONFIG[kind]
        self.win=tk.Toplevel(parent)
        self.win.title(title)
        self.win.geometry('780x580')
        bar=ttk.Frame(self.win)
        bar.pack(fill='x',padx=12,pady=12)
        self.query=tk.StringVar()
        ttk.Label(bar,text='Code / description:' if kind=='wc' else 'ZIP / city / state:').pack(side='left')
        entry=ttk.Entry(bar,textvariable=self.query,width=28)
        entry.pack(side='left',padx=8)
        entry.bind('<Return>',lambda e:self.refresh(reset=True))
        ttk.Button(bar,text='Search',command=lambda:self.refresh(reset=True)).pack(side='left')
        ttk.Button(bar,text='Add',command=self.edit).pack(side='left',padx=5)
        ttk.Button(bar,text='Edit selected',command=self.edit_selected).pack(side='left')
        self.inactive=tk.BooleanVar(value=False)
        ttk.Checkbutton(self.win,text='Include inactive entries',variable=self.inactive,command=lambda:self.refresh(reset=True)).pack(anchor='w',padx=12)
        frame=ttk.Frame(self.win)
        frame.pack(fill='both',expand=True,padx=12,pady=10)
        self.tree=ttk.Treeview(frame,columns=[c[0] for c in self.columns],show='headings')
        for key,label,width in self.columns:
            self.tree.heading(key,text=label)
            self.tree.column(key,width=width)
        scroll=ttk.Scrollbar(frame,command=self.tree.yview)
        self.tree.configure(yscrollcommand=scroll.set)
        scroll.pack(side='right',fill='y')
        self.tree.pack(fill='both',expand=True)
        self.tree.bind('<Double-1>',lambda e:self.select() if on_select else self.edit_selected())
        bottom=ttk.Frame(self.win)
        bottom.pack(fill='x',padx=12,pady=12)
        self.status=tk.StringVar()
        ttk.Label(bottom,textvariable=self.status).pack(side='left')
        self.previous=ttk.Button(bottom,text='Previous',command=lambda:self.move(-1))
        self.previous.pack(side='right',padx=5)
        self.next=ttk.Button(bottom,text='Next',command=lambda:self.move(1))
        self.next.pack(side='right',padx=5)
        if on_select:
            ttk.Button(bottom,text='Use selected ZIP',command=self.select).pack(side='right',padx=5)
        self.refresh()

    def refresh(self,reset=False):
        if reset:
            self.page=0
        count,rows=search(self.db,self.kind,self.query.get(),self.inactive.get(),self.page)
        if self.page and self.page*250>=count:
            self.page=max((count-1)//250,0)
            count,rows=search(self.db,self.kind,self.query.get(),self.inactive.get(),self.page)
        self.tree.delete(*self.tree.get_children())
        for row in rows:
            self.tree.insert('','end',iid=str(row['id']),values=[('Yes' if row[key] else 'No') if key=='active' else row[key] for key,_,_ in self.columns])
        self.status.set(f'{count:,} matches | Page {self.page+1} of {max(1,(count+249)//250)}')
        self.previous.configure(state='normal' if self.page else 'disabled')
        self.next.configure(state='normal' if (self.page+1)*250<count else 'disabled')

    def move(self,step):
        self.page=max(0,self.page+step)
        self.refresh()

    def selected(self):
        if not self.tree.selection():
            messagebox.showinfo('Select entry','Select an entry first.',parent=self.win)
            return None
        return self.db.execute('SELECT * FROM '+self.table+' WHERE id=?',(int(self.tree.selection()[0]),)).fetchone()

    def select(self):
        row=self.selected()
        if row is not None and self.on_select:
            if not row['active']:
                messagebox.showinfo('Inactive entry','Choose an active ZIP entry.',parent=self.win)
                return
            self.on_select(row)
            self.win.destroy()

    def edit_selected(self):
        row=self.selected()
        if row is not None:
            self.edit(row)

    def edit(self,row=None):
        win=tk.Toplevel(self.win)
        win.title('Add entry' if row is None else 'Edit entry')
        entries={}
        for i,(key,label,_) in enumerate(self.columns[:-1]):
            ttk.Label(win,text=label).grid(row=i,column=0,padx=12,pady=10)
            entry=ttk.Entry(win,width=50)
            entry.insert(0,row[key] if row else '')
            entry.grid(row=i,column=1,padx=12,pady=10)
            entries[key]=entry
        active=tk.BooleanVar(value=bool(row['active']) if row else True)
        ttk.Checkbutton(win,text='Active',variable=active).grid(row=len(entries),column=1,sticky='w',padx=12)
        def persist():
            try:
                save(self.db,self.kind,{k:e.get() for k,e in entries.items()},active.get(),row['id'] if row else None)
                self.refresh()
                win.destroy()
            except (ValueError,sqlite3.Error) as error:
                messagebox.showerror('Cannot save entry',str(error),parent=win)
        ttk.Button(win,text='Save',command=persist).grid(row=len(entries)+1,column=1,padx=12,pady=15,sticky='e')
