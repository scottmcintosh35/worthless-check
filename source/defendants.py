import date_format
import shortcuts
"""Defendant directory and profile workflows."""
import datetime as dt
import json
import sqlite3
import tkinter as tk
from tkinter import ttk, messagebox
import defendant_grid
import database_tools
import login
import user_audit

GROUPS = {
    'Identity': [('NAME','Name'),('DOB','Date of birth (MM-DD-YYYY)'),('SEX','Sex'),('RACE','Race'),('LICENSE',"Driver's license"),('SSN','SSN')],
    'Contact': [('ADDRESS','Address'),('ADDRESS2','Address line 2'),('CITY','City'),('STATE','State'),('ZIP','ZIP'),('TELEPHONE','Telephone'),('EMPLOYER','Employer'),('EMP_PHONE','Employer telephone')],
    'Description': [('HEIGHT_FT','Height feet'),('HEIGHT_IN','Height inches'),('WEIGHT','Weight'),('HAIR','Hair'),('EYES','Eyes')],
}
LIMITS = {'NAME':40,'ADDRESS':60,'ADDRESS2':25,'CITY':30,'STATE':2,'ZIP':10,'TELEPHONE':10,'EMPLOYER':30,'EMP_PHONE':10,'SEX':1,'RACE':1,'LICENSE':15,'SSN':10,'HAIR':3,'EYES':3}


def setup(db):
    db.executescript('''CREATE TABLE IF NOT EXISTS defendants (
      id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL, profile TEXT NOT NULL);
      CREATE TABLE IF NOT EXISTS defendant_aliases (
      id INTEGER PRIMARY KEY AUTOINCREMENT, defendant_id INTEGER NOT NULL REFERENCES defendants(id),
      name TEXT NOT NULL, UNIQUE(defendant_id,name));''')
    if 'defendant_id' not in [r[1] for r in db.execute('PRAGMA table_info(cases)')]:
        db.execute('ALTER TABLE cases ADD COLUMN defendant_id INTEGER REFERENCES defendants(id)')
    db.commit()


def audit(db, action, reference):
    db.execute('INSERT INTO audit(at,operator,action,reference) VALUES(?,?,?,?)',
       (dt.datetime.now(dt.timezone.utc).isoformat(),login.require(db),action,str(reference)))


def save_profile(db, profile, defendant_id=None):
    login.require(db)
    allowed = {k for fields in GROUPS.values() for k,_ in fields} | {'HISTORY'}
    values = {k:str(v).strip() for k,v in profile.items() if k in allowed}
    if not values.get('NAME'):
        raise ValueError('Name is required.')
    for key,limit in LIMITS.items():
        if len(values.get(key,'')) > limit:
            raise ValueError(f'{key} allows at most {limit} characters in the legacy schema.')
    if values.get('DOB'):
        try:
            values['DOB'] = date_format.parse(values['DOB']).isoformat()
        except ValueError:
            raise ValueError('Date of birth must use MM-DD-YYYY.') from None
    for key,maximum in [('HEIGHT_FT',9),('HEIGHT_IN',11),('WEIGHT',999)]:
        value = values.get(key,'')
        if value and (not value.isascii() or not value.isdigit() or int(value)>maximum):
            raise ValueError(f'{key} must be a whole number from 0 to {maximum}.')
    with db:
        if defendant_id is None:
            defendant_id=database_tools.allocate(db,'defendant')
            db.execute('INSERT INTO defendants(id,name,profile) VALUES(?,?,?)',
                (defendant_id,values['NAME'],json.dumps(values)))
            action = 'CREATE_DEFENDANT'
        else:
            if db.execute('UPDATE defendants SET name=?,profile=? WHERE id=?',
                (values['NAME'],json.dumps(values),defendant_id)).rowcount != 1:
                raise ValueError('Defendant record not found.')
            action = 'EDIT_DEFENDANT'
        audit(db,action,defendant_id)
    return defendant_id


def add_alias(db, defendant_id, name):
    login.require(db)
    name = name.strip()
    if not name or len(name)>30:
        raise ValueError('Alias name must contain 1 to 30 characters.')
    with db:
        db.execute('INSERT INTO defendant_aliases(defendant_id,name) VALUES(?,?)',(defendant_id,name))
        audit(db,'ADD_ALIAS',defendant_id)


def link_case(db, case_id, defendant_id):
    login.require(db)
    if not db.execute('SELECT 1 FROM defendants WHERE id=?',(defendant_id,)).fetchone():
        raise ValueError('Defendant record not found.')
    with db:
        if db.execute('UPDATE cases SET defendant_id=?,revision=revision+1 WHERE id=?',(defendant_id,case_id)).rowcount != 1:
            raise ValueError('Case not found.')
        audit(db,'LINK_DEFENDANT',f'{case_id}:{defendant_id}')


def reconciliation(db):
    result = []
    for r in db.execute('''SELECT c.id,c.case_no,c.defendant,c.defendant_id,d.name
         FROM cases c LEFT JOIN defendants d ON d.id=c.defendant_id ORDER BY c.case_no'''):
        state = 'Not linked' if r['name'] is None else ('Name differs' if r['defendant'].strip().casefold()!=r['name'].strip().casefold() else 'Names match')
        result.append((r['id'],r['case_no'],r['defendant'],r['defendant_id'] or '',r['name'] or '',state))
    return result


class Directory:
    def __init__(self, app, parent=None):
        self.app, self.db = app, app.store.db
        self.win = ttk.Frame(parent) if parent is not None else tk.Toplevel(app.root)
        if parent is None:
            self.win.title('Defendant directory | Sample data')
            self.win.geometry('850x500')
        else:
            self.win.pack(fill='both',expand=True)
        bar = ttk.Frame(self.win)
        bar.pack(fill='x',padx=12,pady=12)
        self.search = tk.StringVar()
        self.offset=0;self.has_next=False
        entry = ttk.Entry(bar,textvariable=self.search,width=30)
        entry.pack(side='left')
        entry.bind('<Return>',lambda e:self.refresh())
        self.search_entry=entry
        for title,fn in [('Search',self.refresh),('New profile',self.add),('Edit selected',self.edit_selected)]:
            ttk.Button(bar,text=title,command=fn).pack(side='left',padx=3)
        self.link_button = ttk.Button(bar,text='Link to selected case',command=self.link)
        self.link_button.pack(side='left',padx=3)
        self.shortcut_strip=shortcuts.strip(self.win,'')
        pager = ttk.Frame(self.win)
        pager.pack(side='bottom',fill='x',padx=12,pady=(4,8))
        self.previous=ttk.Button(pager,text='Previous',command=lambda:self.page(-1));self.previous.pack(side='left')
        self.next=ttk.Button(pager,text='Next',command=lambda:self.page(1));self.next.pack(side='left',padx=8)
        self.page_status=tk.StringVar();ttk.Label(pager,textvariable=self.page_status).pack(side='left')
        self.tree = defendant_grid.make_grid(self.win)
        self.tree.bind('<Double-1>',lambda e:self.edit_selected())
        self.shortcut_handlers=shortcuts.bind_list(self.tree,{'<Control-Return>':self.edit_selected,'<Control-w>':self.link,'<Control-f>':lambda:shortcuts.focus_search(entry),'<F5>':self.refresh,'<Escape>':lambda:shortcuts.clear_selection(self.tree),'<F1>':lambda:shortcuts.show_help(self.win,'Defendant Information',shortcuts.DIRECTORY)})
        self.refresh()

    def page(self,direction):
        if direction>0 and not self.has_next:return
        self.offset=max(0,self.offset+direction*250);self.refresh(reset=False)

    def refresh(self,reset=True):
        if reset:self.offset=0
        self.tree.delete(*self.tree.get_children());query=self.search.get();args=[]
        legacy = self.app.legacy_mode()
        actions = 'Ctrl+Enter: Details'
        if legacy:
            self.link_button.pack_forget()
            sql = "SELECT record_no AS id, data_json AS profile FROM working_legacy WHERE table_name='WC_DEF' AND deleted=0"
            query = query.strip()
            if query:
                sql += " AND (instr(lower(json_extract(data_json,'$.NAME')),lower(?))>0 OR trim(json_extract(data_json,'$.ID'))=?)"
                args = [query, query]
            order = 'record_no'
        else:
            if not self.link_button.winfo_manager():
                self.link_button.pack(side='left',padx=3)
            actions += '   |   Ctrl+W: Link sample case'
            sql='SELECT d.* FROM defendants d'
            if query:
                sql+=' WHERE d.name LIKE ? OR EXISTS(SELECT 1 FROM defendant_aliases a WHERE a.defendant_id=d.id AND a.name LIKE ?)';args=['%'+query+'%']*2
            order = 'd.name,d.id'
        self.shortcut_strip.configure(text=actions+'   |   Ctrl+F: Search   |   F5: Refresh   |   Esc: Clear selection   |   F1: Shortcuts')
        rows=self.db.execute(f'{sql} ORDER BY {order} LIMIT 251 OFFSET ?',(*args,self.offset)).fetchall();self.has_next=len(rows)>250
        for row in rows[:250]:
            profile = json.loads(row['profile'])
            if legacy and isinstance(profile.get('ID'), str):
                profile['ID'] = profile['ID'].strip()
            self.tree.insert('','end',iid=str(row['id']),values=defendant_grid.values(profile,'' if legacy else row['id']))
        self.previous.configure(state='normal' if self.offset else 'disabled');self.next.configure(state='normal' if self.has_next else 'disabled')
        self.page_status.set(f'Rows {self.offset+1 if rows else 0}-{self.offset+min(len(rows),250)}'+(' - more available' if self.has_next else ''))

    def selected(self):
        selection = self.tree.selection()
        if not selection:
            raise ValueError('Select a defendant profile first.')
        return int(selection[0])

    def edit_selected(self):
        def open_selected():
            record = self.selected()
            if self.app.legacy_mode():
                from legacy_work import Workspace
                Workspace.details_all_fields(self,table='WC_DEF',record=record)
            else:
                self.edit(record)
        self.safe(open_selected)

    def safe(self, action):
        try:
            action()
        except (ValueError, sqlite3.Error) as error:
            messagebox.showerror('Defendant Information',str(error),parent=self.win)

    def add(self):
        if not self.app.legacy_mode():
            return self.edit()
        from legacy_navigation import add_directory_entry
        def show_saved(profile):
            self.search.set(str(profile['ID']).strip())
            self.refresh()
        self.safe(lambda:add_directory_entry(self.app,'WC_DEF',on_saved=show_saved))

    def link(self):
        if self.app.legacy_mode():
            return
        try:
            did, cid = self.selected(), self.app.selected()
            name = self.db.execute('SELECT name FROM defendants WHERE id=?',(did,)).fetchone()[0]
            case = self.app.store.case(cid)
            if messagebox.askyesno('Confirm explicit link',f'Link {case["case_no"]} to demo defendant {did}: {name}?\n\nThe case name remains unchanged so differences remain visible in reconciliation.',parent=self.win):
                link_case(self.db,cid,did)
                messagebox.showinfo('Linked','Link saved. Open Reconciliation to review it.',parent=self.win)
        except (ValueError,sqlite3.Error) as e:
            messagebox.showerror('Cannot link',str(e),parent=self.win)

    def edit(self, defendant_id=None):
        profile = {} if defendant_id is None else json.loads(self.db.execute('SELECT profile FROM defendants WHERE id=?',(defendant_id,)).fetchone()[0])
        if defendant_id is not None:
            user_audit.opened(self.db,'DEFENDANT',f'Defendant ID {defendant_id}')
        win = tk.Toplevel(self.win)
        win.title('Defendant profile | Fictional review data only')
        win.geometry('650x550')
        ttk.Label(win,text='Defendant ID: ' + (str(defendant_id) if defendant_id is not None else 'Assigned when saved')).pack(anchor='w',padx=12,pady=(8,0))
        book = ttk.Notebook(win)
        book.pack(fill='both',expand=True,padx=12,pady=12)
        entries = {}
        for title,fields in GROUPS.items():
            page = ttk.Frame(book)
            book.add(page,text=title)
            for row,(key,label) in enumerate(fields):
                ttk.Label(page,text=label).grid(row=row,column=0,padx=12,pady=8,sticky='w')
                entry = ttk.Entry(page,width=42,show='*' if key=='SSN' else '')
                entry.insert(0,date_format.display(profile.get(key,'')) if key=='DOB' else profile.get(key,''))
                entry.grid(row=row,column=1,padx=12,pady=8,sticky='ew')
                entries[key]=entry
                if key == 'SSN' and profile.get(key):
                    ttk.Label(page,text=defendant_grid.masked_ssn(profile[key])).grid(
                        row=row,column=2,padx=(0,12),sticky='w')
            if title=='Contact':
                def choose_zip():
                    import lookups
                    def apply_zip(row):
                        for field,key in [('ZIP','zip'),('CITY','city'),('STATE','state')]:
                            entries[field].delete(0,'end')
                            entries[field].insert(0,row[key])
                    lookups.Directory(win,self.db,'zip',on_select=apply_zip)
                ttk.Button(page,text='Find ZIP / city',command=choose_zip).grid(row=len(fields),column=1,padx=12,pady=8,sticky='e')
        notes = ttk.Frame(book)
        book.add(notes,text='History / notes')
        history = tk.Text(notes,wrap='word',width=65,height=15)
        history.insert('1.0',profile.get('HISTORY',''))
        history.pack(fill='both',expand=True,padx=8,pady=8)
        aliases = ttk.Frame(book)
        book.add(aliases,text='Aliases')
        alias_list = tk.Listbox(aliases)
        alias_list.pack(fill='both',expand=True,padx=10,pady=10)
        if defendant_id is not None:
            for r in self.db.execute('SELECT name FROM defendant_aliases WHERE defendant_id=? ORDER BY name',(defendant_id,)):
                alias_list.insert('end',r[0])
        alias_entry = ttk.Entry(aliases,width=40)
        alias_entry.pack(padx=10,pady=5)
        def alias():
            if defendant_id is None:
                messagebox.showinfo('Save profile','Save the profile first, then reopen it to add aliases.',parent=win)
                return
            try:
                add_alias(self.db,defendant_id,alias_entry.get())
                alias_list.insert('end',alias_entry.get().strip())
                alias_entry.delete(0,'end')
                self.refresh()
            except (ValueError,sqlite3.Error) as e:
                messagebox.showerror('Cannot add alias',str(e),parent=win)
        ttk.Button(aliases,text='Add alias name (saved immediately)',command=alias).pack(pady=8)
        ttk.Label(aliases,text='Alias names only in this version; legacy alias address and description fields remain pending.').pack(padx=8,pady=5)
        def save(event=None):
            try:
                data={k:e.get() for k,e in entries.items()}
                data['HISTORY']=history.get('1.0','end-1c')
                save_profile(self.db,data,defendant_id)
                self.refresh()
                win.destroy()
            except (ValueError,sqlite3.Error) as e:
                messagebox.showerror('Cannot save profile',str(e),parent=win)
        buttons=ttk.Frame(win)
        buttons.pack(fill='x',padx=12,pady=10)
        ttk.Button(buttons,text='Save profile (Ctrl+W)',command=save).pack(side='right')
        ttk.Button(buttons,text='Cancel profile edits',command=win.destroy).pack(side='right',padx=8)
        win.bind('<Control-w>',save)


def show_reconciliation(app, parent=None):
    win=ttk.Frame(parent) if parent is not None else tk.Toplevel(app.root)
    if parent is None:
        win.title('Reconciliation review | No automatic changes')
        win.geometry('1000x500')
    else:
        win.pack(fill='both',expand=True)
    ttk.Label(win,text='Compare stored case names with explicitly linked defendant profiles. This view does not change records.').pack(padx=12,pady=12)
    tree=ttk.Treeview(win,columns=('case','stored','id','profile','state'),show='headings')
    for col,label,width in [('case','Case number',120),('stored','Case defendant name',250),('id','Demo ID',80),('profile','Profile name',250),('state','Review status',140)]:
        tree.heading(col,text=label)
        tree.column(col,width=width)
    def refresh():
        tree.delete(*tree.get_children())
        for row in reconciliation(app.store.db):
            tree.insert('','end',values=row[1:])
    ttk.Button(win,text='Refresh reconciliation',command=refresh).pack(pady=5)
    refresh()
    tree.pack(fill='both',expand=True,padx=12,pady=12)
