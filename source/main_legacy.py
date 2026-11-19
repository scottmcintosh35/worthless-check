"""Main-screen access to the audited legacy working records."""
import json
import tkinter as tk
from tkinter import messagebox
import legacy_work as lw
DUE=('CK_DUE','FEE_DUE','DA_DUE','WD_DUE')

def enabled(db):
    return bool(db.execute("SELECT 1 FROM legacy_work_meta WHERE key='initialized'").fetchone())

def list_cases(db,query='',offset=0,limit=150):
    sql="FROM working_legacy WHERE table_name='WC_CASE' AND deleted=0";args=[]
    if query:
        sql+=" AND (json_extract(data_json,'$.CASE_NO') LIKE ? OR json_extract(data_json,'$.DEFENDANT') LIKE ? OR json_extract(data_json,'$.MERCHANT') LIKE ? OR json_extract(data_json,'$.CK_NO') LIKE ? OR CAST(record_no AS TEXT)=?)"
        args=['%'+query+'%']*4+[query]
    rows=db.execute('SELECT record_no,data_json '+sql+' ORDER BY record_no LIMIT ? OFFSET ?',(*args,limit+1,max(0,offset))).fetchall()
    return [(r['record_no'],json.loads(r['data_json'])) for r in rows[:limit]],len(rows)>limit

def balances(data):
    if any(key not in data for key in DUE):raise ValueError('One or more imported balance fields are missing. Review this source record.')
    return [lw.money(data[key]) for key in DUE]

class Selection:
    def __init__(self,record=None):self.rows=[];self.chosen=();self.insert('','end',iid=str(record)) if record is not None else None;self.chosen=tuple(self.rows)
    def selection(self):return self.chosen
    def get_children(self):return tuple(self.rows)
    def delete(self,*rows):
        self.rows=[r for r in self.rows if r not in rows];self.chosen=tuple(r for r in self.chosen if r in self.rows)
    def insert(self,parent,index,iid,**kw):self.rows.append(str(iid));return str(iid)
    def selection_set(self,item):self.chosen=(str(item),)
    def exists(self,item):return str(item) in self.rows

class Context:
    # Reuse the same audited editors and payment workflow without opening a workspace window.
    details=lw.Workspace.details
    details_all_fields=lw.Workspace.details_all_fields
    history=lw.Workspace.history
    payment=lw.Workspace.payment
    receipt=lw.Workspace.receipt
    print_payment=lw.Workspace.print_payment
    selected=lw.Workspace.selected
    reconcile_payment=lw.Workspace.reconcile_payment
    def __init__(self,app,record=None):
        self.app=app;self.db=app.store.db;self.win=app.root;self.table=tk.StringVar(master=app.root,value='WC_CASE');self.query=tk.StringVar(master=app.root);self.offset=0;self.tree=Selection(record)
    def refresh(self):self.app.refresh()
    def search(self):
        if self.table.get()=='WC_CASE':self.app.refresh();return
        workspace=lw.Workspace(self.app);workspace.table.set(self.table.get());workspace.query.set(self.query.get());workspace.search()
    def safe(self,fn):
        try:return fn()
        except Exception as error:messagebox.showerror('Legacy case',str(error),parent=self.win)
