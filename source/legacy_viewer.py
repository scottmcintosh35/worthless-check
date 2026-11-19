"""Read-only imported database review, integrated with the prototype launcher."""
import json
from pathlib import Path
import sqlite3
import tkinter as tk
from tkinter import ttk, messagebox
from office import show_heading
import defendant_grid
import date_format


class Viewer:
    def __init__(self, root, path):
        self.db=sqlite3.connect(Path(path).resolve().as_uri()+'?mode=ro',uri=True)
        self.db.row_factory=sqlite3.Row
        try:
            row=self.db.execute("SELECT value FROM import_meta WHERE key='report'").fetchone()
            if not row:
                raise ValueError('This import is incomplete; it cannot be reviewed.')
            self.report=json.loads(row[0])
            if self.report.get('status')!='imported_for_read_only_review':
                raise ValueError('This import is incomplete.')
        except Exception:
            self.db.close()
            raise
        self.root=root
        root.title('Check Management | Imported legacy records - READ ONLY')
        root.geometry('1150x780')
        import import_dialog
        menu=tk.Menu(root)
        file_menu=tk.Menu(menu,tearoff=False)
        file_menu.add_command(label='Import Database...',command=lambda:import_dialog.ImportDialog(root))
        file_menu.add_command(label='Open Imported Database...',command=lambda:import_dialog.open_database(root))
        file_menu.add_separator()
        file_menu.add_command(label='Close',command=self.close)
        menu.add_cascade(label='File',menu=file_menu)
        root.configure(menu=menu)
        show_heading(root)
        ttk.Label(root,text='READ ONLY REVIEW • Actual backup records • No payment posting or balance recalculation',foreground='#9c3b12').pack(anchor='w',padx=16)
        book=ttk.Notebook(root)
        book.pack(fill='both',expand=True,padx=12,pady=12)
        for title,table in [('Cases','WC_CASE'),('Defendant Information','WC_DEF'),('Payments','PAYMENTS'),('Merchants','WC_MERCH'),('Adjustments','WC_ADJ'),('Bank Codes','BANKCODE')]:
            page=ttk.Frame(book)
            book.add(page,text=title)
            self.browser(page,table)
        other=ttk.Frame(book)
        book.add(other,text='Other tables')
        names=[r[0] for r in self.db.execute('SELECT name FROM source_tables ORDER BY name') if r[0] not in ('SECURITY','FOXUSER','WC_USER')]
        choice=ttk.Combobox(other,values=names,state='readonly',width=30)
        choice.pack(anchor='w',padx=12,pady=8)
        holder=ttk.Frame(other)
        holder.pack(fill='both',expand=True)
        def change(event=None):
            for child in holder.winfo_children():
                child.destroy()
            self.browser(holder,choice.get())
        choice.bind('<<ComboboxSelected>>',change)
        summary=ttk.Frame(book)
        book.add(summary,text='Import checks')
        tree=ttk.Treeview(summary,columns=('table','all','active','deleted','encoding'),show='headings')
        for key,label in [('table','Table'),('all','Physical records'),('active','Active'),('deleted','Deleted marker'),('encoding','Encoding')]:
            tree.heading(key,text=label)
            tree.column(key,width=160)
        for t in self.report['tables']:
            tree.insert('','end',values=(t['table'],t['records'],t['active'],t['deleted'],t['encoding']))
        tree.pack(fill='both',expand=True,padx=12,pady=12)
        ttk.Label(summary,text='Import issues: '+str(self.report['issues'])+'\nEncoding for unmarked tables is an assumption; original bytes are preserved.',wraplength=1050).pack(padx=12,pady=10)
        root.protocol('WM_DELETE_WINDOW',self.close)

    def close(self):
        self.db.close()
        self.root.destroy()

    def browser(self,parent,table):
        bar=ttk.Frame(parent)
        bar.pack(fill='x',padx=10,pady=10)
        query=tk.StringVar()
        ttk.Label(bar,text='Name / case number / receipt / ID:').pack(side='left')
        entry=ttk.Entry(bar,textvariable=query,width=35)
        entry.pack(side='left',padx=8)
        include=tk.BooleanVar(value=False)
        ttk.Checkbutton(bar,text='Include deleted',variable=include).pack(side='left',padx=8)
        if table=='WC_DEF':
            tree=defendant_grid.make_grid(parent)
            tree.tag_configure('deleted',foreground='#888888')
        elif table=='BANKCODE':
            tree=ttk.Treeview(parent,columns=('code','bank','record','deleted'),show='headings')
            for key,label,width in [('code','Code',90),('bank','Bank',620),('record','Source row',100),('deleted','Deleted',80)]:
                tree.heading(key,text=label)
                tree.column(key,width=width)
            scroll=ttk.Scrollbar(parent,command=tree.yview)
            scroll.pack(side='right',fill='y')
            tree.configure(yscrollcommand=scroll.set)
            tree.pack(fill='both',expand=True,padx=10,pady=8)
        else:
            tree=ttk.Treeview(parent,columns=('record','case','name','id','receipt','deleted'),show='headings')
            for key,label,width in [('record','Source row',90),('case','Case',130),('name','Name',350),('id','Defendant ID',130),('receipt','Receipt',130),('deleted','Deleted',80)]:
                tree.heading(key,text=label)
                tree.column(key,width=width)
            tree.pack(fill='both',expand=True,padx=10,pady=8)
        status=tk.StringVar()
        ttk.Label(parent,textvariable=status).pack(anchor='w',padx=12,pady=8)
        def search(event=None):
            tree.delete(*tree.get_children())
            text=query.get().strip()
            sql='FROM legacy_records WHERE table_name=? AND (deleted=0 OR ?=1)'
            args=[table,int(include.get())]
            if text:
                if table=='BANKCODE':
                    sql+=" AND (json_extract(data_json,'$.CODE') LIKE ? OR json_extract(data_json,'$.BANK') LIKE ?)"
                    args.extend(['%'+text+'%']*2)
                else:
                    sql+=' AND (name LIKE ? OR case_no LIKE ? OR receipt_no LIKE ? OR def_id=?)'
                    args.extend(['%'+text+'%']*3+[text])
            count=self.db.execute('SELECT COUNT(*) '+sql,args).fetchone()[0]
            limit='' if table=='BANKCODE' else ' LIMIT 250'
            order=" ORDER BY json_extract(data_json,'$.CODE'),record_no" if table=='BANKCODE' else ' ORDER BY record_no'
            for r in self.db.execute('SELECT * '+sql+order+limit,args):
                row_values=defendant_grid.values(json.loads(r['data_json'])) if table=='WC_DEF' else (r['record_no'],r['case_no'],r['name'],r['def_id'],r['receipt_no'],'Yes' if r['deleted'] else '')
                if table=='BANKCODE':
                    bank=json.loads(r['data_json'])
                    row_values=(bank.get('CODE',''),bank.get('BANK',''),r['record_no'],'Yes' if r['deleted'] else '')
                tree.insert('','end',iid=str(r['record_no']),values=row_values,tags=('deleted',) if r['deleted'] else ())
            status.set(f'{table}: {count:,} matching records. '+('All matches shown.' if table=='BANKCODE' else 'Showing first 250.')+' Double-click a record for all fields.')
        def details(event=None):
            if tree.selection():
                self.details(table,int(tree.selection()[0]))
        ttk.Button(bar,text='Search',command=search).pack(side='left',padx=5)
        ttk.Button(bar,text='View information',command=details).pack(side='left')
        entry.bind('<Return>',search)
        tree.bind('<Double-1>',details)
        tree.bind('<Control-Return>',details)
        search()

    def details(self,table,record_no):
        r=self.db.execute('SELECT * FROM legacy_records WHERE table_name=? AND record_no=?',(table,record_no)).fetchone()
        values=json.loads(r['data_json'])
        win=tk.Toplevel(self.root)
        win.title(f'{table} - source row {record_no} - read only')
        win.geometry('900x650')
        issues=self.db.execute('SELECT field,issue FROM import_issues WHERE table_name=? AND record_no=?',(table,record_no)).fetchall()
        if issues:
            ttk.Label(win,text='Source issues: '+'; '.join(f'{i[0]}: {i[1]}' for i in issues),foreground='#9c3b12',wraplength=850).pack(padx=12,pady=8)
        book=ttk.Notebook(win)
        book.pack(fill='both',expand=True,padx=12,pady=12)
        if table=='WC_DEF':
            groups={'Identity':['ID','NAME','DOB','SEX','RACE','LICENSE','SSN'],
                    'Contact':['ADDRESS','ADDRESS2','CITY','STATE','ZIP','TELEPHONE','EMPLOYER','EMP_PHONE'],
                    'Description':['HEIGHT_FT','HEIGHT_IN','WEIGHT','HAIR','EYES'],
                    'History':['HISTORY']}
        elif table=='WC_CASE':
            groups={'Case / parties':['CASE_NO','DEF_ID','DEFENDANT','MERCH_ID','MERCHANT','CK_NO','CK_DATE','BANK','BANK_CODE','ITEM_CODE','ITEM'],
                    'Amounts / balances':['CK_AMT','MERCH_FEE','FIRST_OFF','WITHDRAWAL','COURT_COST','CK_DUE','DA_DUE','FEE_DUE','WD_DUE','REST_PAID','SFEE_PAID','FO_PAID','WD_PAID','CC_PAID','OVERPAID','AMT_PAID'],
                    'Dates / status':['ENTER_DATE','ISSUE_DATE','DUE_DATE','CT_DATE','DISP_DATE','DISP_CODE','DISP_NARR','PENDING','PAID','REGISTER','LOCKED'],
                    'Notes':['DISP','COMMENT','ADJ_REASON']}
        else:
            groups={}
        used={k for keys in groups.values() for k in keys}
        schema = self.db.execute('SELECT fields_json FROM source_tables WHERE name=?',(table,)).fetchone()
        date_fields = {field['name'] for field in json.loads(schema[0]) if field['type']=='D'} if schema else set()
        groups['All other fields']=[k for k in values if k not in used]
        for label,keys in groups.items():
            if not keys:
                continue
            page=ttk.Frame(book)
            book.add(page,text=label)
            text=tk.Text(page,wrap='word',font=('Consolas',11))
            scroll=ttk.Scrollbar(page,command=text.yview)
            text.configure(yscrollcommand=scroll.set)
            scroll.pack(side='right',fill='y')
            text.pack(fill='both',expand=True)
            for key in keys:
                value=values.get(key,'')
                if isinstance(value,dict) and 'memo' in value:
                    memo=self.db.execute('SELECT text,error,kind FROM legacy_memos WHERE table_name=? AND pointer=?',(table,value['memo'])).fetchone()
                    value='' if not value['memo'] else (memo['text'] if memo and memo['text'] is not None else '[Memo unavailable or binary; original preserved]')
                if key=='SSN':
                    value=defendant_grid.masked_ssn(value)
                if key in date_fields:
                    value=date_format.display(value)
                text.insert('end',f'{key}: {value}\n\n')
            text.configure(state='disabled')
        ttk.Label(win,text='Dates are shown as MM-DD-YYYY. Blank dates remain blank. No balances have been recomputed.').pack(padx=12,pady=8)


def launch(path):
    root=tk.Tk()
    try:
        Viewer(root,path)
    except (sqlite3.Error,ValueError) as e:
        messagebox.showerror('Cannot open import',str(e))
        root.destroy()
        return
    root.mainloop()
