import date_format
"""Case editing, printable reports, month-end review and labels."""
import datetime as dt
from decimal import Decimal,InvalidOperation
import json
import sqlite3
import tkinter as tk
from tkinter import ttk,messagebox,filedialog,simpledialog
from pathlib import Path
import reporting
import login
import user_audit
import banks
import receipt_print


def amount_cents(value):
    number=Decimal(value)
    if not number.is_finite() or not 0<=number<=Decimal('99999999.99') or number!=number.quantize(Decimal('.01')):
        raise ValueError('Enter nonnegative dollar amounts with at most two decimal places.')
    return int(number*100)


class FunctionsUI:
    def __init__(self,app):
        self.app,self.store,self.db=app,app.store,app.store.db

    def commands(self):
        return [('Edit Case',self.edit_case),('Print Reports',self.reports),('Modify Reports',self.modify_reports),
            ('Daily Register Reports',lambda:self.reports('daily')),('Month-End Process',self.month_end),
            ('Check Analysis Report',lambda:self.reports('analysis')),('Monthly Activity Report',lambda:self.reports('monthly')),
            ('Print Defendant Labels',self.labels),('Modify Labels',self.modify_labels)]

    def error(self,error,parent=None):
        messagebox.showerror('Functions',str(error),parent=parent or self.app.root)

    def show_report(self,title,content):
        win=tk.Toplevel(self.app.root)
        user_audit.opened(self.db,'REPORT',title)
        win.title(title)
        win.geometry('950x650')
        frame=ttk.Frame(win)
        frame.pack(fill='both',expand=True,padx=12,pady=12)
        text=tk.Text(frame,wrap='word',font=('Consolas',11))
        scroll=ttk.Scrollbar(frame,command=text.yview)
        text.configure(yscrollcommand=scroll.set)
        scroll.pack(side='right',fill='y')
        text.pack(fill='both',expand=True)
        text.insert('1.0',content)
        text.configure(state='disabled')
        bar=ttk.Frame(win)
        bar.pack(fill='x',padx=12,pady=10)
        def export():
            path=filedialog.asksaveasfilename(parent=win,defaultextension='.txt',filetypes=[('Text report','*.txt')])
            if path:
                try:
                    Path(path).write_text(content,encoding='utf-8')
                except OSError as error:
                    self.error(error,win)
        def print_report():
            try:
                receipt_print.open_print_preview([content],self.store.path.parent/'report-previews')
            except (ValueError,OSError) as error:
                self.error(error,win)
        ttk.Button(bar,text='Print Report (Letter)',command=print_report).pack(side='left')
        ttk.Button(bar,text='Save text copy',command=export).pack(side='left',padx=8)
        return win

    def edit_case(self):
        if hasattr(self.app,'legacy_mode') and self.app.legacy_mode():self.app.edit_case();return
        try:
            row=self.store.case(self.app.selected())
        except ValueError as error:
            self.error(error)
            return
        user_audit.opened(self.db,'CASE',user_audit.case_ref(row['case_no'],row['id']))
        win,entries=self.app.form('Edit Case '+row['case_no'],['Defendant','Merchant','Check number','Entered date MM-DD-YYYY','Due date MM-DD-YYYY (optional)',
            'Original restitution','Original merchant fee','Original DA fee','Original withdrawal fee','Reason for edit'],
            [row['defendant'],row['merchant'],row['check_no'],date_format.display(row['entered']),date_format.display(row['due_date']),
                *[format(Decimal(row[k])/100,'.2f') for k in reporting.PAY_KEYS[:4]],''])
        profiles=self.db.execute('SELECT id,name FROM defendants ORDER BY name,id').fetchall()
        ttk.Label(win,text='Linked defendant profile').grid(row=10,column=0,padx=15,pady=5,sticky='w')
        profile_choice=ttk.Combobox(win,state='readonly',width=42,values=['Not linked']+[f'{p["id"]}: {p["name"]}' for p in profiles])
        profile_choice.current(next((i+1 for i,p in enumerate(profiles) if p['id']==row['defendant_id']),0))
        profile_choice.grid(row=10,column=1,padx=15,pady=5)
        bank_rows=banks.list_banks(self.db,include_inactive=True)
        ttk.Label(win,text='Bank').grid(row=11,column=0,padx=15,pady=5,sticky='w')
        bank_choice=ttk.Combobox(win,state='readonly',width=42,values=['Not selected']+[r['code']+' - '+r['name'] for r in bank_rows])
        bank_choice.current(next((i+1 for i,b in enumerate(bank_rows) if b['id']==row['bank_id']),0))
        bank_choice.grid(row=11,column=1,padx=15,pady=5)
        ttk.Label(win,text='Case number stays fixed. Use adjustments for charges after financial history exists.',wraplength=550).grid(row=12,column=0,columnspan=2,padx=15,pady=8)
        def save():
            try:
                data=dict(zip(('defendant','merchant','check_no','entered','due_date'),[e.get() for e in entries[:5]]))
                data['due_date']=data['due_date'] or None
                index=profile_choice.current()
                data['defendant_id']=profiles[index-1]['id'] if index>0 else None
                index=bank_choice.current()
                data['bank_id']=bank_rows[index-1]['id'] if index>0 else None
                reporting.edit_case(self.store,row['id'],data,[amount_cents(e.get()) for e in entries[5:9]],entries[9].get(),expected_revision=row['revision'])
                self.app.refresh()
                win.destroy()
            except (ValueError,InvalidOperation,sqlite3.Error) as error:
                self.error(error,win)
        ttk.Button(win,text='Save Case',command=save).grid(row=13,column=1,padx=15,pady=12)
        return win

    def reports(self,kind='cases'):
        if kind not in reporting.TITLES:
            kind='cases'
        today=dt.date.today()
        win,entries=self.app.form('Print Reports',['Start date MM-DD-YYYY','End date MM-DD-YYYY'],
            [date_format.display(today if kind=='daily' else today.replace(day=1)),date_format.display(today)])
        titles=list(reporting.TITLES.values())
        keys=list(reporting.TITLES)
        choice=ttk.Combobox(win,values=titles,state='readonly',width=42)
        choice.current(keys.index(kind))
        ttk.Label(win,text='Report').grid(row=2,column=0,padx=15,pady=10,sticky='w')
        choice.grid(row=2,column=1,padx=15,pady=10)
        ttk.Label(win,text='Case Detail uses the selected main-window case and shows its full history.\nDefendant Listing includes all profiles. Other reports use the date range.',wraplength=540).grid(row=3,column=0,columnspan=2,padx=15,pady=10)
        def preview():
            try:
                selected=keys[choice.current()]
                cid=self.app.selected() if selected=='case' else None
                content=reporting.build_report(self.store,selected,entries[0].get(),entries[1].get(),cid)
                self.show_report(reporting.TITLES[selected],content)
            except (ValueError,sqlite3.Error) as error:
                self.error(error,win)
        ttk.Button(win,text='Preview report',command=preview).grid(row=4,column=1,padx=15,pady=15)
        return win

    def modify_reports(self):
        win=tk.Toplevel(self.app.root)
        win.title('Modify Reports')
        win.geometry('800x650')
        keys=list(reporting.TITLES)
        choice=ttk.Combobox(win,values=list(reporting.TITLES.values()),state='readonly',width=45)
        choice.current(0)
        choice.pack(anchor='w',padx=15,pady=12)
        title=ttk.Entry(win,width=70)
        title.pack(fill='x',padx=15,pady=5)
        ttk.Label(win,text='Report template: {office_heading}, {office_contact}, {report_title}, {period}, {generated}, {body}, {footer}',wraplength=750).pack(padx=15,pady=8)
        text=tk.Text(win,wrap='word',height=16)
        text.pack(fill='both',expand=True,padx=15,pady=8)
        ttk.Label(win,text='Footer').pack(anchor='w',padx=15)
        footer=ttk.Entry(win,width=70)
        footer.pack(fill='x',padx=15,pady=8)
        def load(event=None):
            kind=keys[choice.current()]
            title.delete(0,'end')
            title.insert(0,reporting.get_setting(self.db,'title:'+kind,reporting.TITLES[kind]))
            text.delete('1.0','end')
            text.insert('1.0',reporting.get_setting(self.db,'wrapper:'+kind,reporting.DEFAULT_WRAPPER))
            footer.delete(0,'end')
            footer.insert(0,reporting.get_setting(self.db,'footer:'+kind,''))
        choice.bind('<<ComboboxSelected>>',load)
        def save():
            try:
                reporting.save_report_settings(self.db,keys[choice.current()],title.get(),text.get('1.0','end-1c'),footer.get())
                messagebox.showinfo('Saved','Report layout settings saved.',parent=win)
            except (ValueError,sqlite3.Error) as error:
                self.error(error,win)
        ttk.Button(win,text='Save report settings',command=save).pack(anchor='e',padx=15,pady=12)
        load()
        return win

    def month_end(self):
        win=tk.Toplevel(self.app.root)
        win.title('Month-End Process - prototype snapshots')
        win.geometry('900x550')
        bar=ttk.Frame(win)
        bar.pack(fill='x',padx=15,pady=15)
        ttk.Label(bar,text='Month YYYY-MM:').pack(side='left')
        month=tk.StringVar(value=dt.date.today().strftime('%Y-%m'))
        ttk.Entry(bar,textvariable=month,width=12).pack(side='left',padx=8)
        ttk.Label(win,text='Close saves a fixed review snapshot and locks dated financial changes for the month.\nIt does not distribute funds, create payouts or certify the legacy month-end calculations.',wraplength=850).pack(anchor='w',padx=15,pady=8)
        tree=ttk.Treeview(win,columns=('id','month','at','by','state'),show='headings',height=10)
        for key,label in [('id','Snapshot ID'),('month','Month'),('at','Closed at UTC'),('by','Closed by'),('state','Current state')]:
            tree.heading(key,text=label)
        tree.pack(fill='both',expand=True,padx=15,pady=10)
        def refresh():
            tree.delete(*tree.get_children())
            for r in self.db.execute('''SELECT s.id,s.month,s.closed_at,s.closed_by,p.closed,p.snapshot_id FROM period_snapshots s JOIN accounting_periods p ON p.month=s.month ORDER BY s.id DESC'''):
                state='Closed' if r['closed'] and r['snapshot_id']==r['id'] else 'Prior snapshot / reopened'
                tree.insert('','end',iid=str(r['id']),values=(r['id'],r['month'],r['closed_at'],r['closed_by'],state))
        def preview():
            try:
                start,end=reporting.month_range(month.get())
                self.show_report('Month-end preview',reporting.build_report(self.store,'monthly',start,end))
            except (ValueError,sqlite3.Error) as error:
                self.error(error,win)
        def close():
            try:
                reporting.month_range(month.get())
                if not messagebox.askyesno('Close prototype month',f'Save a snapshot and close {month.get()} to dated financial changes?\n\nAn Administrator can reopen it with a reason.',parent=win):
                    return
                sid,path=reporting.close_month(self.store,month.get())
                refresh()
                messagebox.showinfo('Month closed',f'Snapshot {sid} saved.\nBackup: {path}',parent=win)
            except (ValueError,OSError,sqlite3.Error) as error:
                self.error(error,win)
        def reopen():
            reason=simpledialog.askstring('Reopen month','Reason for reopening '+month.get()+':',parent=win)
            if reason is None:
                return
            try:
                reporting.reopen_month(self.db,month.get(),reason)
                refresh()
            except (ValueError,sqlite3.Error) as error:
                self.error(error,win)
        def saved():
            if not tree.selection():
                return
            row=self.db.execute('SELECT * FROM period_snapshots WHERE id=?',(int(tree.selection()[0]),)).fetchone()
            import hashlib
            if hashlib.sha256(row['snapshot_json'].encode('utf-8')).hexdigest()!=row['sha256']:
                self.error(ValueError('Snapshot checksum does not match.'),win)
                return
            data=json.loads(row['snapshot_json'])
            self.show_report('Saved month-end snapshot',f'SNAPSHOT {row["id"]} | {row["closed_at"]}\n\n'+data['report'])
        bottom=ttk.Frame(win)
        bottom.pack(fill='x',padx=15,pady=12)
        for label,fn in [('Preview month',preview),('Close month / save snapshot',close),('Reopen month',reopen),('View selected snapshot',saved)]:
            ttk.Button(bottom,text=label,command=fn).pack(side='left',padx=4)
        tree.bind('<Double-1>',lambda e:saved())
        refresh()
        return win

    def labels(self):
        win=tk.Toplevel(self.app.root)
        win.title('Print Defendant Labels')
        ttk.Label(win,text='Print postal address labels on letter-size paper. Use a plain-paper alignment test first.',wraplength=570).pack(padx=15,pady=15)
        selected=tk.BooleanVar(value=False)
        ttk.Checkbutton(win,text='Only the defendant linked to the selected case',variable=selected).pack(anchor='w',padx=15,pady=8)
        def print_labels():
            try:
                did=None
                if selected.get():
                    did=self.store.case(self.app.selected())['defendant_id']
                    if did is None:
                        raise ValueError('Link a defendant profile to the selected case first.')
                count,skipped,path=reporting.open_labels(self.db,self.store.path.parent/'label-previews',did)
                messagebox.showinfo('Label preview opened',f'Labels: {count}\nSkipped profiles missing name/address: {skipped}\n\nChoose Letter, portrait, actual size (100%) in the browser print dialog.',parent=win)
            except (ValueError,OSError,sqlite3.Error) as error:
                self.error(error,win)
        ttk.Button(win,text='Preview / Print Labels',command=print_labels).pack(padx=15,pady=15)
        return win

    def modify_labels(self):
        layout=json.loads(reporting.get_setting(self.db,'label_layout',json.dumps(reporting.DEFAULT_LAYOUT)))
        labels=['Columns','Rows per page','Label width (inches)','Label height (inches)','Left/right margin (inches)','Top/bottom margin (inches)','Column gap (inches)','Font size (points)']
        win,entries=self.app.form('Modify Labels',labels,[str(layout[k]) for k in reporting.DEFAULT_LAYOUT])
        ttk.Label(win,text='Address template: {name}, {address}, {address2}, {city}, {state}, {zip}').grid(row=8,column=0,columnspan=2,padx=15,pady=8)
        template=tk.Text(win,width=55,height=6)
        template.insert('1.0',reporting.get_setting(self.db,'label_template',reporting.DEFAULT_LABEL))
        template.grid(row=9,column=0,columnspan=2,padx=15,pady=10)
        def save():
            try:
                reporting.save_label_settings(self.db,template.get('1.0','end-1c'),dict(zip(reporting.DEFAULT_LAYOUT,[e.get() for e in entries])))
                messagebox.showinfo('Saved','Label settings saved.',parent=win)
            except (ValueError,sqlite3.Error) as error:
                self.error(error,win)
        ttk.Button(win,text='Save label settings',command=save).grid(row=10,column=1,padx=15,pady=12)
        return win
