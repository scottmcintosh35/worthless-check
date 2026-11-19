"""Security grid for current application accounts; stored passwords are never exposed."""
import datetime as dt
import tkinter as tk
from tkinter import ttk,messagebox
import login
import login_activity

def local_time(value):
    if not value:return None
    try:return dt.datetime.fromisoformat(value).astimezone()
    except (ValueError,TypeError):return None

def account_rows(db,search=''):
    login.require(db);viewer=login.current(db)
    if viewer is None:raise ValueError('Sign in before viewing Security.')
    where='WHERE (u.username LIKE ? OR u.full_name LIKE ?)';args=['%'+search+'%']*2
    if viewer['role']!='Administrator':where+=' AND u.id=?';args.append(viewer['id'])
    usage,sessions,available=login_activity.snapshot(db);rows=[]
    for row in db.execute('SELECT u.id,u.username,u.full_name,u.active,c.user_id AS credential_id,c.role,c.version FROM staff_users u LEFT JOIN credentials c ON c.user_id=u.id '+where+' ORDER BY u.username COLLATE NOCASE',args):
        history=usage.get(row['id'],{});signin=local_time(history.get('last_signin'));last=local_time(history.get('last_usage'))
        online=bool(row['active'] and row['credential_id'] and any(user==row['id'] and version==row['version'] for user,version,at in sessions))
        rows.append({'id':row['id'],'login':row['username'],'password':'Set' if row['credential_id'] else 'Not set','role':row['role'] or 'Not configured','logged':'Yes' if online else ('No' if available else 'Unknown'),'date':signin.strftime('%m-%d-%Y') if signin else '', 'time':signin.strftime('%H:%M:%S') if signin else '', 'usage':last.strftime('%m-%d-%Y %H:%M:%S') if last else '', 'active':'Yes' if row['active'] else 'No'})
    return rows

class SecurityWindow:
    def __init__(self,app):
        self.app=app;self.db=app.store.db;login.require(self.db);self.win=tk.Toplevel(app.root);self.win.title('Edit Login/Password - Security');self.win.geometry('1100x570');self.win.minsize(850,420)
        ttk.Label(self.win,text='Security',background='#dbe8f4',foreground='#17324d',padding=8,font=('Segoe UI',12,'bold')).pack(fill='x',padx=12,pady=8)
        top=ttk.Frame(self.win);top.pack(fill='x',padx=12,pady=4);self.search=tk.StringVar();ttk.Label(top,text='Find login / staff name:').pack(side='left');entry=ttk.Entry(top,textvariable=self.search,width=32);entry.pack(side='left',padx=8);entry.bind('<Return>',lambda event:self.refresh());ttk.Button(top,text='Search',command=self.refresh).pack(side='left')
        bar=ttk.Frame(self.win);bar.pack(side='bottom',fill='x',padx=12,pady=10)
        administrator=login.current(self.db)['role']=='Administrator'
        for title,fn,admin in [('Add User',lambda:app.staff_directory.edit(),True),('Edit / reset selected login',self.edit_selected,True),('Change my password',app.system_tools.change_password,False),('Refresh (F5)',self.refresh,False),('Close',self.close,False)]:ttk.Button(bar,text=title,command=lambda f=fn:self.safe(f),state='normal' if administrator or not admin else 'disabled').pack(side='left',padx=4)
        ttk.Label(self.win,text='Password shows setup status. Double-click a row to edit/reset it. Logged_in means a recent application heartbeat (90 seconds), not Windows/RDP login. Usage dates display server-local time; blank dates mean not yet recorded.',wraplength=1020).pack(side='bottom',fill='x',padx=12,pady=6)
        holder=ttk.Frame(self.win);holder.pack(fill='both',expand=True,padx=12,pady=6);self.tree=ttk.Treeview(holder,columns=('login','password','role','logged','date','time','usage','active'),show='headings')
        for key,title,width in [('login','Login',160),('password','Password',100),('role','Level / Role',140),('logged','Logged_in',85),('date','Date_in',100),('time','Time_in',90),('usage','Last_usage',180),('active','Active',70)]:self.tree.heading(key,text=title);self.tree.column(key,width=width,stretch=False)
        self.tree.grid(row=0,column=0,sticky='nsew');vertical=ttk.Scrollbar(holder,command=self.tree.yview);vertical.grid(row=0,column=1,sticky='ns');horizontal=ttk.Scrollbar(holder,orient='horizontal',command=self.tree.xview);horizontal.grid(row=1,column=0,sticky='ew');self.tree.configure(yscrollcommand=vertical.set,xscrollcommand=horizontal.set);holder.rowconfigure(0,weight=1);holder.columnconfigure(0,weight=1)
        self.tree.bind('<Double-1>',lambda event:self.safe(self.edit_selected));self.tree.bind('<Control-Return>',lambda event:self.safe(self.edit_selected));self.win.bind('<F5>',lambda event:self.safe(self.refresh));self.refresh();self.after_id=self.win.after(10000,self.periodic);self.win.protocol('WM_DELETE_WINDOW',self.close);self.win.bind('<Destroy>',lambda event:self.cancel_timer() if event.widget==self.win else None)
    def safe(self,fn):
        try:return fn()
        except Exception as error:messagebox.showerror('Security',str(error),parent=self.win)
    def refresh(self):
        rows=account_rows(self.db,self.search.get());selection=self.tree.selection();self.tree.delete(*self.tree.get_children())
        for row in rows:self.tree.insert('','end',iid=str(row['id']),values=[row[key] for key in self.tree['columns']])
        if selection and self.tree.exists(selection[0]):self.tree.selection_set(selection[0])
    def edit_selected(self):
        login.require(self.db)
        if login.current(self.db)['role']!='Administrator':return self.app.system_tools.change_password()
        if not self.tree.selection():raise ValueError('Select a login to edit or reset.')
        self.app.staff_directory.edit(int(self.tree.selection()[0]))
    def cancel_timer(self):
        if getattr(self,'after_id',None):
            try:self.win.after_cancel(self.after_id)
            except tk.TclError:pass
            self.after_id=None
    def close(self):self.cancel_timer();self.win.destroy()
    def periodic(self):
        if not self.win.winfo_exists():return
        if login.current(self.db) is None:self.close();return
        self.safe(self.refresh);self.after_id=self.win.after(10000,self.periodic)
