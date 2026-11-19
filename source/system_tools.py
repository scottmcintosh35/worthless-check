import date_format
"""System dialogs: local login, credentials, calculator and diary."""
import ast
import calendar
import datetime as dt
from decimal import Decimal,InvalidOperation,localcontext
import operator
import sqlite3
import tkinter as tk
import divisions
import users
from tkinter import ttk,messagebox
import login


def calculate(expression):
    if not expression.strip() or len(expression)>200:
        raise ValueError('Enter an arithmetic expression of up to 200 characters.')
    operations={ast.Add:operator.add,ast.Sub:operator.sub,ast.Mult:operator.mul,ast.Div:operator.truediv}
    def visit(node,depth=0):
        if depth>20:
            raise ValueError('Expression is too complex.')
        if isinstance(node,ast.Constant) and type(node.value) in (int,float):
            return Decimal(ast.get_source_segment(expression,node))
        if isinstance(node,ast.UnaryOp) and type(node.op) in (ast.UAdd,ast.USub):
            value=visit(node.operand,depth+1)
            return value if isinstance(node.op,ast.UAdd) else -value
        if isinstance(node,ast.BinOp) and type(node.op) in operations:
            return operations[type(node.op)](visit(node.left,depth+1),visit(node.right,depth+1))
        raise ValueError('Use numbers, parentheses and + - * / only.')
    try:
        with localcontext() as context:
            context.prec=28
            value=visit(ast.parse(expression,mode='eval').body)
            if not value.is_finite() or abs(value)>Decimal('1e50'):
                raise ValueError('Result is outside the supported range.')
            return str(value)
    except (SyntaxError,InvalidOperation,ZeroDivisionError):
        raise ValueError('Invalid expression or division by zero.') from None


def division_picker(win, row, division, choices, on_select):
    ttk.Label(win, text='Division').grid(row=row, column=0, padx=15, pady=6)
    picker = ttk.Combobox(win, state='readonly', values=[divisions.LABELS[key] for key in choices])
    picker.current(choices.index(division))
    picker.grid(row=row, column=1, padx=15, pady=6)

    def selected(event):
        target = choices[picker.current()]
        if target != division:
            on_select(target)
            win.winfo_toplevel().destroy()

    picker.bind('<<ComboboxSelected>>', selected)


def login_dialog(parent,db,required=False,division=None,*,choices=(),on_select=None,maximized=False):
    win=tk.Toplevel(parent)
    label = divisions.LABELS.get(division)
    bootstrap = not login.enabled(db)
    if bootstrap:
        win.title(f'{label} - Create first Administrator login' if label else 'Create first Administrator login')
    else:
        win.title('DA12th Worthless Check')
    if parent.winfo_viewable():
        win.transient(parent)
    win.grab_set()
    success=[]
    staff=db.execute('SELECT * FROM staff_users WHERE active=1 ORDER BY full_name').fetchall()
    if bootstrap and not staff:
        ttk.Label(win,text='Add an active user in the Users tab, then return here to create the first Administrator login.',wraplength=450).pack(padx=20,pady=20)
        ttk.Button(win,text='Close',command=win.destroy).pack(pady=15)
        parent.wait_window(win)
        return False
    form = ttk.Frame(win, name='login_form', padding=20) if maximized else win
    if maximized:
        form.place(relx=0.5, rely=0.5, anchor='center')
    ttk.Label(form,text='Choose the first Administrator user:' if bootstrap else 'Username').grid(row=0,column=0,padx=15,pady=12)
    username=ttk.Combobox(form,values=[r['username'] for r in staff],state='readonly') if bootstrap else ttk.Entry(form)
    username.grid(row=0,column=1,padx=15,pady=12)
    if bootstrap:
        username.current(0)
    ttk.Label(form,text='Password (12+ characters)' if bootstrap else 'Password').grid(row=1,column=0,padx=15,pady=10)
    password=ttk.Entry(form,show='*',width=35)
    password.grid(row=1,column=1,padx=15,pady=10)
    confirm=None
    if bootstrap:
        ttk.Label(form,text='Confirm password').grid(row=2,column=0,padx=15,pady=10)
        confirm=ttk.Entry(form,show='*',width=35)
        confirm.grid(row=2,column=1,padx=15,pady=10)
    elif label and not choices:
        ttk.Label(form,text=label).grid(row=2,column=0,columnspan=2,pady=(4,0))
    if choices:
        division_picker(form, 4 if bootstrap else 2, division, choices, on_select)
    def submit(event=None):
        try:
            if bootstrap:
                if password.get()!=confirm.get():
                    raise ValueError('Passwords do not match.')
                user=next(r for r in staff if r['username']==username.get())
                login.set_password(db,user['id'],password.get(),bootstrap=True)
            login.authenticate(db,username.get(),password.get())
            success.append(True)
            win.destroy()
        except (ValueError,sqlite3.Error) as error:
            messagebox.showerror('Login',str(error),parent=win)
    ttk.Button(form,text='Create Administrator login' if bootstrap else 'Sign in',
               command=submit,style='Primary.TButton').grid(row=3,column=1,padx=15,pady=15)
    win.bind('<Return>',submit)
    if maximized:
        win.state('zoomed')
    win.update_idletasks()
    win.deiconify()
    win.lift()
    password.focus_set()
    parent.wait_window(win)
    return bool(success)


class SystemTools:
    def __init__(self,app):
        self.app,self.db=app,app.store.db

    def about(self):
        from deployment import RELEASE
        messagebox.showinfo('About Worthless Check',
            users.document_heading(self.db)+f'\n\nServer Deployment Candidate {RELEASE}\nShared local evaluation database and read-only legacy review.\n\nDatabase: '+str(self.app.store.path),parent=self.app.root)

    def calculator(self):
        win=tk.Toplevel(self.app.root)
        win.title('Calculator')
        expression=ttk.Entry(win,width=45,font=('Segoe UI',14))
        expression.pack(padx=18,pady=15)
        result=tk.StringVar()
        ttk.Label(win,textvariable=result,font=('Segoe UI',16)).pack(padx=18,pady=10)
        def run(event=None):
            try:
                result.set(calculate(expression.get()))
            except ValueError as error:
                result.set(str(error))
        ttk.Label(win,text='Use + - * / and parentheses.').pack(pady=5)
        ttk.Button(win,text='Calculate',command=run).pack(pady=15)
        expression.bind('<Return>',run)

    def sign_in(self):
        if login_dialog(self.app.root,self.db):
            self.app.root.title((divisions.LABELS.get(getattr(self.app, 'division', None), 'Worthless Check') + ' | Signed in: ')+login.current(self.db)['username'])

    def sign_out(self):
        if not login.enabled(self.db):
            return
        login.logout(self.db)
        self.app.root.withdraw()
        if login_dialog(self.app.root,self.db,True):
            self.app.root.deiconify()
            self.app.root.title((divisions.LABELS.get(getattr(self.app, 'division', None), 'Worthless Check') + ' | Signed in: ')+login.current(self.db)['username'])
        else:
            self.app.root.destroy()

    def credentials(self):
        if not login.enabled(self.db):self.sign_in();return
        try:
            login.require(self.db)
            from security_ui import SecurityWindow
            return SecurityWindow(self.app)
        except (ValueError,sqlite3.Error) as error:messagebox.showerror('Login required',str(error),parent=self.app.root)

    def change_password(self):
        if not login.enabled(self.db):
            self.sign_in()
            return
        try:
            login.require(self.db)
        except ValueError as error:
            messagebox.showerror('Login required',str(error),parent=self.app.root)
            return
        row=login.current(self.db)
        win=tk.Toplevel(self.app.root)
        win.title('Edit Login/Password')
        fields=[]
        for i,label in enumerate(['Current password','New password (12+ characters)','Confirm new password']):
            ttk.Label(win,text=label).grid(row=i,column=0,padx=15,pady=10)
            e=ttk.Entry(win,show='*',width=35)
            e.grid(row=i,column=1,padx=15,pady=10)
            fields.append(e)
        def change():
            try:
                if fields[1].get()!=fields[2].get():
                    raise ValueError('New passwords do not match.')
                login.change_own_password(self.db,fields[0].get(),fields[1].get())
                win.destroy()
                messagebox.showinfo('Password changed','Password updated.',parent=self.app.root)
            except (ValueError,sqlite3.Error) as error:
                messagebox.showerror('Cannot change password',str(error),parent=win)
        ttk.Button(win,text='Change my password',command=change).grid(row=3,column=1,pady=15)
        if row['role']=='Administrator':
            ttk.Button(win,text='Set staff password / role',command=self.staff_credentials).grid(row=4,column=1,pady=15)

    def staff_credentials(self):
        try:
            login.require(self.db,True)
        except ValueError as error:
            messagebox.showerror('Administrator required',str(error),parent=self.app.root)
            return
        rows=self.db.execute('SELECT * FROM staff_users WHERE active=1 ORDER BY username').fetchall()
        win=tk.Toplevel(self.app.root)
        win.title('Set staff login')
        user=ttk.Combobox(win,values=[r['username'] for r in rows],state='readonly',width=35)
        user.current(0)
        user.pack(padx=15,pady=10)
        role=ttk.Combobox(win,values=['Staff','Administrator'],state='readonly',width=35)
        role.current(0)
        role.pack(padx=15,pady=10)
        ttk.Label(win,text='New password / passphrase (12+ characters)').pack(padx=15)
        password=ttk.Entry(win,show='*',width=38)
        password.pack(padx=15,pady=10)
        ttk.Label(win,text='Confirm password').pack(padx=15)
        confirm=ttk.Entry(win,show='*',width=38)
        confirm.pack(padx=15,pady=10)
        def save():
            try:
                if password.get()!=confirm.get():
                    raise ValueError('Passwords do not match.')
                selected=next(r for r in rows if r['username']==user.get())
                login.set_password(self.db,selected['id'],password.get(),role.get())
                if selected['id']==login.SESSIONS.get(self.db,(None,))[0]:
                    login.authenticate(self.db,user.get(),password.get())
                win.destroy()
                messagebox.showinfo('Saved','Staff password and login role saved.',parent=self.app.root)
            except (ValueError,sqlite3.Error) as error:
                messagebox.showerror('Cannot save login',str(error),parent=win)
        ttk.Button(win,text='Save staff login',command=save).pack(pady=15)

    def diary(self):
        win=tk.Toplevel(self.app.root)
        win.title('Calendar / Diary')
        win.geometry('850x650')
        bar=ttk.Frame(win)
        bar.pack(fill='x',padx=12,pady=10)
        today=dt.date.today()
        month=tk.StringVar(value=today.strftime('%Y-%m'))
        ttk.Label(bar,text='Month YYYY-MM:').pack(side='left')
        ttk.Entry(bar,textvariable=month,width=12).pack(side='left',padx=8)
        calendar_text=tk.StringVar()
        ttk.Label(win,textvariable=calendar_text,font=('Consolas',12),justify='left').pack(padx=12,pady=8)
        tree=ttk.Treeview(win,columns=('date','subject','owner','done'),show='headings',height=7)
        for key,label in [('date','Date'),('subject','Subject'),('owner','Created by'),('done','Completed')]:
            tree.heading(key,text=label)
        tree.pack(fill='both',expand=True,padx=12,pady=10)
        def refresh():
            try:
                first=dt.date.fromisoformat(month.get()+'-01')
            except ValueError:
                messagebox.showerror('Invalid month','Use YYYY-MM.',parent=win)
                return
            calendar_text.set(calendar.month(first.year,first.month))
            tree.delete(*tree.get_children())
            for r in self.db.execute('SELECT * FROM diary_entries WHERE substr(date,1,7)=? ORDER BY date,id',(month.get(),)):
                tree.insert('','end',iid=str(r['id']),values=(date_format.display(r['date']),r['subject'],r['owner'],'Yes' if r['completed'] else 'No'))
        ttk.Button(bar,text='Show month',command=refresh).pack(side='left')
        def edit(new=True):
            if not new and not tree.selection():
                return
            old=self.db.execute('SELECT * FROM diary_entries WHERE id=?',(int(tree.selection()[0]),)).fetchone() if not new else None
            form,entries=self.app.form('Diary entry',['Date MM-DD-YYYY','Subject'],[date_format.display(old['date'] if old else today),old['subject'] if old else ''])
            note=tk.Text(form,width=55,height=8)
            note.insert('1.0',old['note'] if old else '')
            note.grid(row=2,column=0,columnspan=2,padx=15,pady=10)
            completed=tk.BooleanVar(value=bool(old['completed']) if old else False)
            ttk.Checkbutton(form,text='Completed',variable=completed).grid(row=3,column=1,padx=15,pady=8)
            def save():
                try:
                    actor=login.require(self.db)
                    date=date_format.parse(entries[0].get()).isoformat()
                    subject=entries[1].get().strip()
                    if not subject:
                        raise ValueError('Subject is required.')
                    with self.db:
                        if old:
                            self.db.execute('UPDATE diary_entries SET date=?,subject=?,note=?,completed=? WHERE id=?',(date,subject,note.get('1.0','end-1c'),int(completed.get()),old['id']))
                        else:
                            self.db.execute('INSERT INTO diary_entries(date,subject,note,owner,completed) VALUES(?,?,?,?,?)',(date,subject,note.get('1.0','end-1c'),actor,int(completed.get())))
                    form.destroy()
                    refresh()
                except (ValueError,sqlite3.Error) as error:
                    messagebox.showerror('Cannot save diary entry',str(error),parent=form)
            ttk.Button(form,text='Save diary entry',command=save).grid(row=4,column=1,pady=15)
        ttk.Button(win,text='Add diary entry',command=edit).pack(side='left',padx=12,pady=12)
        ttk.Button(win,text='Edit selected / mark completed',command=lambda:edit(False)).pack(side='left',padx=12,pady=12)
        tree.bind('<Double-1>',lambda e:edit(False))
        refresh()
