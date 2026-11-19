"""Legacy Database menu groups routed to audited working data."""
import json
import sqlite3
import tkinter as tk
from tkinter import ttk,messagebox
import login
import legacy_work as lw

STRUCTURES=[('Case','WC_CASE'),('Defendant','WC_DEF'),('Victim','WC_MERCH'),('Payments','PAYMENTS'),('User','USER'),('Bank Codes','BANKCODE'),('Adjustment Table','WC_ADJ')]
COUNTERS=[('Case Number','WCCASENO'),('Adjustment Number','ADJ_NO'),('Receipt Number','RECEIPT'),('Defendant ID','WCDEFID'),('Merchant ID','MERCHID')]

def safe(app,fn):
    try:return fn()
    except Exception as error:messagebox.showerror('Database',str(error),parent=app.root)

def show_table(app,table,deleted_only=False,admin=False):
    login.require(app.store.db,admin or table in ('USER','SECURITY','FOXUSER','WC_USER'))
    lw.schema(app.store.db,table)
    workspace=lw.Workspace(app);workspace.table.set(table);workspace.deleted.set(deleted_only);workspace.deleted_only=deleted_only;workspace.search()
    if deleted_only:workspace.win.title('Deleted / recoverable '+table+' records - originals retained')
    return workspace


def add_directory_entry(app, table, parent=None, on_saved=None):
    db = app.store.db
    login.require(db, True)
    title, id_field, fields = {
        'BANKCODE': ('Add Bank / Code',None,[('CODE','Bank code'),('BANK','Bank name')]),
        'WC_MERCH': ('Add Merchant / ID','ME_ID',[
            ('ME_NAME','Merchant name'),('ME_ADDR','Address'),('ME_CITY','City'),
            ('ME_STATE','State'),('ME_ZIP','ZIP'),('ME_PHONE','Phone'),('ME_CONTACT','Contact')]),
        'WC_DEF': ('Add Defendant','ID',[
            ('NAME','Defendant name'),('DOB','Date of birth (MM-DD-YYYY)'),('ADDRESS','Address'),
            ('ADDRESS2','Address line 2'),('CITY','City'),('STATE','State'),('ZIP','ZIP'),('TELEPHONE','Phone')]),
    }[table]
    party = 'Defendant' if table == 'WC_DEF' else 'Merchant'
    schema = {field['name'] for field in lw.schema(db, table)}
    fields = [item for item in fields if item[0] in schema]
    win = tk.Toplevel(parent or app.root)
    win.title(title)
    win.transient(parent or app.root)
    if id_field:
        ttk.Label(win,text=f'{party} ID is assigned when saved.').grid(row=0,column=0,columnspan=2,pady=8)
    entries = {}
    for row, (key, label) in enumerate([*fields, ('reason','Reason')],start=1):
        ttk.Label(win,text=label).grid(row=row,column=0,sticky='w',padx=12,pady=5)
        entry = ttk.Entry(win,width=42)
        entry.grid(row=row,column=1,padx=12,pady=5)
        entries[key] = entry

    def save():
        data = {key:entries[key].get().strip() for key, _ in fields}
        try:
            record = lw.create(db,table,data,entries['reason'].get())
        except (ValueError, sqlite3.Error) as error:
            messagebox.showerror(title,str(error),parent=win)
            return
        data = json.loads(lw.get(db,table,record)['data_json'])
        win.destroy()
        if on_saved:
            on_saved(data)
        elif id_field:
            messagebox.showinfo(title,f"{party} ID {data[id_field]} assigned.",parent=parent or app.root)

    ttk.Button(win,text='Save',command=save).grid(row=len(entries)+1,column=1,pady=12)
    win.grab_set()
    next(iter(entries.values())).focus_set()
    return win

def show_schema(app,table):
    fields=lw.schema(app.store.db,table);win=tk.Toplevel(app.root);win.title(table+' - preserved field definitions');tree=ttk.Treeview(win,columns=('name','type','width','decimals'),show='headings');tree.pack(fill='both',expand=True,padx=12,pady=12)
    for key in tree['columns']:tree.heading(key,text=key)
    for field in fields:tree.insert('','end',values=(field['name'],field['type'],field['length'],field.get('decimals',0)))
    ttk.Label(win,text='Original field definitions are preserved. Edit record values through the audited record editor.',wraplength=750).pack(padx=12,pady=12);return win

def swap_defendant(app):
    login.require(app.store.db,True)
    from case_window import CaseWindow
    window=CaseWindow(app,app.legacy_record());window.choose_party('WC_DEF');return window

def review_amounts(app):
    login.require(app.store.db,True);win=tk.Toplevel(app.root);win.title('Review missing, invalid or zero check amounts');win.geometry('950x560');tree=ttk.Treeview(win,columns=('row','case','defendant','amount'),show='headings');tree.pack(fill='both',expand=True,padx=12,pady=12)
    for key in tree['columns']:tree.heading(key,text=key)
    count=0
    for row in app.store.db.execute("SELECT record_no,data_json FROM working_legacy WHERE table_name='WC_CASE' AND deleted=0 ORDER BY record_no"):
        data=json.loads(row['data_json'])
        try:flag=lw.money(data.get('CK_AMT',''))<=0
        except ValueError:flag=True
        if flag:
            count+=1
            if count<=500:tree.insert('','end',iid=str(row['record_no']),values=(row['record_no'],data.get('CASE_NO',''),data.get('DEFENDANT',''),data.get('CK_AMT','')))
    ttk.Label(win,text=str(count)+' records to review; first 500 shown. Double-click opens the selected source case. No amounts are changed automatically.').pack(padx=12,pady=8)
    def open_case(event=None):
        if tree.selection():
            from case_window import CaseWindow
            CaseWindow(app,int(tree.selection()[0]))
    tree.bind('<Double-1>',lambda event:safe(app,open_case));return win

def populate(menu,app):
    menu.delete(0,'end')
    def command(parent,label,fn):parent.add_command(label=label,command=lambda:safe(app,fn))
    for label,table in [('Bank Codes','BANKCODE'),('WC Codes','WC_CODE'),('Zip Codes','AZIPS'),*COUNTERS]:command(menu,label,lambda t=table:show_table(app,t))
    command(menu,'Add Bank / Code',lambda:add_directory_entry(app,'BANKCODE'))
    command(menu,'Add Merchant / ID',lambda:add_directory_entry(app,'WC_MERCH'))
    structures=tk.Menu(menu,tearoff=False)
    for label,table in STRUCTURES:command(structures,label,lambda t=table:show_schema(app,t))
    menu.add_cascade(label='Modify table structures',menu=structures)
    command(menu,'Reindex',app.database_tools.reindex)
    command(menu,'View Deleted Records',lambda:show_table(app,'WC_CASE',True))
    command(menu,'View Deleted Payments',lambda:show_table(app,'PAYMENTS',True))
    command(menu,'Index Adjustment Table',lambda:app.database_tools.reindex(True))
    command(menu,'View Adjustment Records',lambda:show_table(app,'WC_ADJ'))
    supervisor=tk.Menu(menu,tearoff=False)
    for label,table in [('Delete/Edit Merchant Records','WC_MERCH'),('Delete/Edit Defendant Records','WC_DEF'),('Delete/Edit Case Records','WC_CASE'),('Delete/Edit Payment Table','PAYMENTS')]:command(supervisor,label,lambda t=table:show_table(app,t,False,True))
    command(supervisor,'Case Recovery',lambda:show_table(app,'WC_CASE',True,True));command(supervisor,'Browse for Check Amount = ???',lambda:review_amounts(app));command(supervisor,'Defendant Swap',lambda:swap_defendant(app));menu.add_cascade(label='Supervisor Actions',menu=supervisor)
    menu.add_separator()
    command(menu,'Defendant directory',lambda:show_table(app,'WC_DEF'))
    command(menu,'Merchant directory',lambda:show_table(app,'WC_MERCH'))
    command(menu,'Archived payment backup (DEL_PAY)',lambda:show_table(app,'DEL_PAY'))
    command(menu,'Complete Legacy Workspace',lambda:lw.open_workspace(app))
