"""Staff profiles and office settings for the review prototype."""
import datetime as dt
from decimal import Decimal, InvalidOperation
import json
import re
import sqlite3
import tkinter as tk
from tkinter import ttk, messagebox, filedialog
import login
import divisions

DEFAULTS={'ORGANIZATION':'','HEADING2':'','HEADING3':'','HEADING4':'','OFFICE_LABEL':'','DA':'','COUNTY':'','CIRCUIT':'','ADDRESS1':'','ADDRESS2':'','CITY':'','STATE':'','ZIP':'','PHONE':'','FAX':'',
          'ADMIN':'','GJ':'','VS':'','WC':'','REST':'','BACKUP_FOLDER':'','DA_FEE':'0.00','MERCHANT_FEE':'30.00','WITHDRAWAL_FEE':'30.00','DUE_BUSINESS_DAYS':'15','BUSINESS_HOLIDAYS':'','RECEIPT_START':''}
OFFICE_FIELDS=[('ORGANIZATION','Organization / office name'),('HEADING2','Heading line 2 (optional)'),('HEADING3','Heading line 3 (optional)'),('HEADING4','Heading line 4 (optional)'),('OFFICE_LABEL','Workspace name (optional)'),('ADDRESS1','Address 1'),('ADDRESS2','Address 2'),('CITY','City'),('STATE','State / region code (optional)'),('ZIP','Postal / ZIP code'),('PHONE','Phone'),('FAX','Fax')]
COORDINATORS=[('ADMIN','Administrative Assistant'),('GJ','Coordinator 2'),('VS','Coordinator 3'),('WC','Program coordinator'),('REST','Coordinator 5')]


def setup(db):
    db.executescript('''CREATE TABLE IF NOT EXISTS staff_users (
      id INTEGER PRIMARY KEY AUTOINCREMENT, username TEXT NOT NULL COLLATE NOCASE UNIQUE,
      full_name TEXT NOT NULL, initials TEXT NOT NULL, title TEXT NOT NULL DEFAULT '',
      active INTEGER NOT NULL CHECK(active IN (0,1)));
      CREATE TABLE IF NOT EXISTS office_settings(id INTEGER PRIMARY KEY CHECK(id=1),data TEXT NOT NULL);''')


def log(db,action,reference):
    db.execute('INSERT INTO audit(at,operator,action,reference) VALUES(?,?,?,?)',
       (dt.datetime.now(dt.timezone.utc).isoformat(),login.require(db),action,str(reference)))


def save_user(db,username,name,initials,title,active=True,user_id=None,*,password=None,confirm_password=None,role=None):
    actor=login.require(db,True)
    login_change=password is not None or role is not None
    credential_data=None
    if login_change:
        administrator=login.current(db)
        if not administrator or administrator['role']!='Administrator':raise ValueError('Sign in as an Administrator before changing a staff login.')
        if role not in (None,'Staff','Administrator'):raise ValueError('Choose Staff or Administrator.')
        if password is not None:
            if password!=confirm_password:raise ValueError('Passwords do not match.')
            if password or user_id is None:credential_data=login.password_data(password)
    username,name,initials,title=username.strip(),name.strip(),initials.strip().upper(),title.strip()
    if not re.fullmatch(r'[A-Za-z0-9._-]{1,40}',username):raise ValueError('Username must contain 1 to 40 letters, digits, dots, hyphens or underscores.')
    if not name or len(name)>100:raise ValueError('Enter a staff name of up to 100 characters.')
    if not re.fullmatch(r'[A-Z0-9]{1,8}',initials):raise ValueError('Initials must contain 1 to 8 letters or digits.')
    with db:
        if user_id is not None:db.execute('UPDATE staff_users SET active=active WHERE id=?',(user_id,))
        existing=db.execute('SELECT * FROM credentials WHERE user_id=?',(user_id,)).fetchone() if user_id is not None else None
        selected_role=role or (existing['role'] if existing else 'Staff')
        if user_id is not None and login.is_last_admin(db,user_id) and (not active or (login_change and selected_role!='Administrator')):
            raise ValueError('Keep at least one active Administrator login.')
        if login_change and existing is None and credential_data is None:raise ValueError('This user has no login yet. Enter and confirm a password to create it.')
        actor=login.require(db,True)
        if user_id is None:
            user_id=db.execute('INSERT INTO staff_users(username,full_name,initials,title,active) VALUES(?,?,?,?,?)',(username,name,initials,title,int(bool(active)))).lastrowid
            action='ADD_STAFF_USER'
        else:
            if db.execute('UPDATE staff_users SET username=?,full_name=?,initials=?,title=?,active=? WHERE id=?',(username,name,initials,title,int(bool(active)),user_id)).rowcount!=1:raise ValueError('Staff user not found.')
            action='EDIT_STAFF_USER'
        login.audit(db,actor,action,user_id)
        if login_change:
            if credential_data is not None:
                salt,digest=credential_data
                db.execute('''INSERT INTO credentials(user_id,salt,digest,iterations,role) VALUES(?,?,?,?,?)
                  ON CONFLICT(user_id) DO UPDATE SET salt=excluded.salt,digest=excluded.digest,iterations=excluded.iterations,
                  role=excluded.role,version=version+1,failures=0,locked_until=0''',(user_id,salt,digest,login.ITERATIONS,selected_role))
                login.audit(db,actor,'SET_STAFF_LOGIN',user_id)
            elif existing['role']!=selected_role:
                db.execute('UPDATE credentials SET role=?,version=version+1 WHERE user_id=?',(selected_role,user_id))
                login.audit(db,actor,'SET_STAFF_ROLE',user_id)
    return user_id


def get_settings(db):
    row=db.execute('SELECT data FROM office_settings WHERE id=1').fetchone()
    return {**DEFAULTS, **(json.loads(row[0]) if row else {})}


def save_settings(db,data):
    login.require(db,True)
    previous=get_settings(db)
    values={key:str(data.get(key,previous.get(key,default))).strip() for key,default in DEFAULTS.items()}
    for key in ('ORGANIZATION','HEADING2','HEADING3','HEADING4','OFFICE_LABEL'):
        if len(values[key])>120 or any(ord(c)<32 for c in values[key]):
            raise ValueError('Office heading fields must be single lines of at most 120 characters.')
    if values['STATE'] and len(values['STATE'])!=2:
        raise ValueError('State / region code must be blank or a two-letter abbreviation.')
    values['STATE']=values['STATE'].upper()
    try:
        amount=Decimal(values['DA_FEE'] or '0')
        if not amount.is_finite() or amount<0 or amount>Decimal('99999999.99') or amount!=amount.quantize(Decimal('.01')):
            raise InvalidOperation
        values['DA_FEE']=format(amount,'.2f')
    except InvalidOperation:
        raise ValueError('DA fee must be a nonnegative dollar amount with at most two decimal places.') from None
    import case_defaults
    for key in ('MERCHANT_FEE','WITHDRAWAL_FEE'):
        try:
            value=Decimal(values[key])
            if not value.is_finite() or value<0 or value>Decimal('99999999.99') or value!=value.quantize(Decimal('.01')):raise InvalidOperation
            values[key]=format(value,'.2f')
        except InvalidOperation:raise ValueError(key+' must be a nonnegative amount with two decimal places.') from None
    if not values['DUE_BUSINESS_DAYS'].isascii() or not values['DUE_BUSINESS_DAYS'].isdigit() or not 1<=int(values['DUE_BUSINESS_DAYS'])<=365:raise ValueError('Due business days must be from 1 to 365.')
    case_defaults.holiday_dates(values['BUSINESS_HOLIDAYS'])
    if values['RECEIPT_START']:
        from legacy_work import receipt_number_width
        requested = values['RECEIPT_START']
        if not re.fullmatch(r'[1-9][0-9]*', requested) or len(requested) > receipt_number_width(db):
            raise ValueError('Starting receipt number must be a positive number without leading zeros that fits the receipt field.')
    with db:
        db.execute('INSERT INTO office_settings(id,data) VALUES(1,?) ON CONFLICT(id) DO UPDATE SET data=excluded.data',(json.dumps(values),))
        log(db,'SAVE_OFFICE_INFORMATION',1)
    return values


def document_heading(db):
    settings=get_settings(db)
    lines=[settings['ORGANIZATION'],settings['HEADING2'],settings['HEADING3'],settings['HEADING4']]
    return '\n'.join(line for line in lines if line.strip()) or 'Worthless Check'


def workspace_label(db):
    settings=get_settings(db)
    return settings['OFFICE_LABEL'] or settings['ORGANIZATION'] or divisions.LABELS[divisions.database_division(db)]



def document_contact(db):
    s=get_settings(db)
    city=' '.join(v for v in (s['CITY'],s['STATE'],s['ZIP']) if v) if s['CITY'] or s['ZIP'] else ''
    return '\n'.join(v for v in (s['ADDRESS1'],s['ADDRESS2'],city,
        ('Phone: '+s['PHONE']) if s['PHONE'] else '',('Fax: '+s['FAX']) if s['FAX'] else '') if v)


class StaffDirectory:
    def __init__(self,app,parent):
        self.db=app.store.db
        self.parent=parent
        bar=ttk.Frame(parent)
        bar.pack(fill='x',padx=15,pady=15)
        ttk.Button(bar,text='Add User',command=self.edit).pack(side='left')
        ttk.Button(bar,text='Edit selected user',command=self.edit_selected).pack(side='left',padx=8)
        ttk.Button(bar,text='Refresh',command=self.refresh).pack(side='left')
        self.tree=ttk.Treeview(parent,columns=('username','name','initials','title','active'),show='headings')
        for key,label,width in [('username','Username',180),('name','Staff name',260),('initials','Initials',90),('title','Position / title',240),('active','Active',80)]:
            self.tree.heading(key,text=label)
            self.tree.column(key,width=width)
        help_text = ttk.Label(parent, text='To reset a password, use System > Edit Login/Password.')
        help_text.pack(side='bottom', fill='x', padx=15, pady=(0, 10))
        self.tree.pack(fill='both', expand=True, padx=15, pady=(0, 8))
        self.tree.bind('<Double-1>', lambda e: self.edit_selected())
        self.refresh()

    def refresh(self):
        self.tree.delete(*self.tree.get_children())
        for r in self.db.execute('SELECT * FROM staff_users ORDER BY full_name'):
            self.tree.insert('','end',iid=str(r['id']),values=(r['username'],r['full_name'],r['initials'],r['title'],'Yes' if r['active'] else 'No'))

    def edit_selected(self):
        if not self.tree.selection():
            messagebox.showinfo('Select user','Select a staff user first.',parent=self.parent)
            return
        self.edit(int(self.tree.selection()[0]))

    def edit(self,user_id=None):
        row=self.db.execute('SELECT * FROM staff_users WHERE id=?',(user_id,)).fetchone() if user_id is not None else None
        win=tk.Toplevel(self.parent)
        win.title('Add User' if row is None else 'Edit User')
        entries={}
        for index,(key,label) in enumerate([('username','Username'),('full_name','Staff name'),('initials','Initials'),('title','Position / title')]):
            ttk.Label(win,text=label).grid(row=index,column=0,padx=15,pady=10,sticky='w')
            entry=ttk.Entry(win,width=42)
            entry.insert(0,row[key] if row else '')
            entry.grid(row=index,column=1,padx=15,pady=10)
            entries[key]=entry
        active=tk.BooleanVar(value=bool(row['active']) if row else True)
        ttk.Checkbutton(win,text='Active user',variable=active).grid(row=4,column=1,sticky='w',padx=15,pady=8)
        login_fields={}
        credential=self.db.execute('SELECT role FROM credentials WHERE user_id=?',(user_id,)).fetchone() if row is not None else None
        role=ttk.Combobox(win,values=['Staff','Administrator'],state='readonly',width=39);role.set(credential['role'] if credential else 'Staff')
        ttk.Label(win,text='Login role').grid(row=5,column=0,padx=15,pady=10,sticky='w');role.grid(row=5,column=1,padx=15,pady=10);login_fields['role']=role
        for index,key,label in [(6,'password','Password (12+ characters)' if row is None else 'New password (optional)'),(7,'confirm_password','Confirm password')]:
            ttk.Label(win,text=label).grid(row=index,column=0,padx=15,pady=10,sticky='w')
            entry=ttk.Entry(win,show='*',width=42);entry.grid(row=index,column=1,padx=15,pady=10);login_fields[key]=entry
        if row is not None:
            ttk.Label(win,text='Leave both password fields blank to keep the current password.' if credential else 'No login exists yet. Enter a password (12+ characters) to enable sign-in.',wraplength=420).grid(row=8,column=0,columnspan=2,padx=15,pady=8)
        def save():
            try:
                save_user(self.db,entries['username'].get(),entries['full_name'].get(),entries['initials'].get(),entries['title'].get(),active.get(),user_id,**{k:e.get() for k,e in login_fields.items()})
                self.refresh()
                win.destroy()
            except (ValueError,sqlite3.Error) as error:
                messagebox.showerror('Cannot save user','Username is already in use.' if isinstance(error,sqlite3.IntegrityError) else str(error),parent=win)
        ttk.Button(win,text='Save User',command=save).grid(row=8 if row is None else 9,column=1,padx=15,pady=15,sticky='e')


class OfficeForm:
    def __init__(self,app,parent):
        self.app=app
        self.db=app.store.db
        self.parent=parent
        self.entries={}
        ttk.Button(parent, text='Save Office Information', command=self.save).pack(
            side='bottom', anchor='e', padx=15, pady=(0, 10))
        book=ttk.Notebook(parent)
        book.pack(fill='both',expand=True,padx=15,pady=15)
        settings=get_settings(self.db)
        staff=[r[0] for r in self.db.execute('SELECT full_name FROM staff_users WHERE active=1 ORDER BY full_name')]
        for title,fields in [('Office Information',OFFICE_FIELDS),('Coordinators',COORDINATORS),('Defaults',[('BACKUP_FOLDER','Database backup location'),('DA_FEE','Default administration / warrant fee'),('MERCHANT_FEE','Default merchant fee'),('WITHDRAWAL_FEE','Default withdrawal fee (every new case)'),('DUE_BUSINESS_DAYS','Due business days after entry'),('BUSINESS_HOLIDAYS','Holiday exclusions (MM-DD-YYYY, comma separated)'),('RECEIPT_START','Starting numeric receipt (optional)')])]:
            panel = ttk.Frame(book)
            book.add(panel, text=title)
            canvas = tk.Canvas(panel, highlightthickness=0, background=ttk.Style(panel).lookup('TFrame', 'background'))
            scroll = ttk.Scrollbar(panel, orient='vertical', command=canvas.yview)
            canvas.configure(yscrollcommand=scroll.set)
            scroll.pack(side='right', fill='y')
            canvas.pack(fill='both', expand=True)
            page = ttk.Frame(canvas)
            window = canvas.create_window(0, 0, window=page, anchor='nw')
            page.bind('<Configure>', lambda event, c=canvas: c.configure(scrollregion=c.bbox('all')))
            canvas.bind('<Configure>', lambda event, c=canvas, w=window: c.itemconfigure(w, width=event.width))

            def scroll_to_field(event, c=canvas, body=page):
                if body.winfo_height() <= c.winfo_height():
                    return
                top = c.canvasy(0)
                field = event.widget
                if field.winfo_y() < top or field.winfo_y() + field.winfo_height() > top + c.winfo_height():
                    c.yview_moveto(max(0, field.winfo_y() - 8) / body.winfo_height())

            for index,(key,label) in enumerate(fields):
                ttk.Label(page,text=label).grid(row=index,column=0,padx=15,pady=8,sticky='w')
                entry=ttk.Combobox(page,values=staff,width=48) if title=='Coordinators' else ttk.Entry(page,width=50)
                entry.insert(0,settings[key])
                entry.grid(row=index,column=1,padx=15,pady=8,sticky='ew')
                entry.bind('<FocusIn>', scroll_to_field)
                self.entries[key]=entry
                if key=='BACKUP_FOLDER':
                    def browse():
                        folder=filedialog.askdirectory(parent=parent,title='Choose default backup folder')
                        if folder:
                            self.entries['BACKUP_FOLDER'].delete(0,'end')
                            self.entries['BACKUP_FOLDER'].insert(0,folder)
                    ttk.Button(page,text='Browse...',command=browse).grid(row=index,column=2,padx=8)
            if title=='Office Information':
                ttk.Label(page,text='Enter your own organization and heading lines. Blank headings use Worthless Check; no DA, circuit, state or county heading is added automatically.',wraplength=760).grid(row=len(fields),column=0,columnspan=3,padx=15,pady=15,sticky='w')
            if title=='Defaults':
                ttk.Label(page,text='Receipt numbering starts at this number or above the highest retained numeric receipt, whichever is higher. Leave blank to continue the existing sequence.',wraplength=760).grid(row=len(fields),column=0,columnspan=3,padx=15,pady=15,sticky='w')

    def save(self):
        try:
            save_settings(self.db,{key:entry.get() for key,entry in self.entries.items()})
            from office import update_heading
            update_heading(self.app.office_heading, document_heading(self.db).splitlines())
            from deployment import RELEASE
            current=login.current(self.db)
            self.app.root.title(workspace_label(self.db)+' | Worthless Check | '+RELEASE+(' | '+current['username'] if current else ''))
            messagebox.showinfo('Saved','Office information and coordinator details saved.',parent=self.parent)
        except (ValueError,sqlite3.Error) as error:
            messagebox.showerror('Cannot save office information',str(error),parent=self.parent)
