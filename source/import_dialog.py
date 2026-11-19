"""Import and open commands shared by the sample and imported-record windows."""
from pathlib import Path
import queue
import sqlite3
import threading
import tkinter as tk
from tkinter import ttk, filedialog, messagebox


def open_database(parent, path=None):
    if path is None:
        path=filedialog.askopenfilename(parent=parent,title='Open imported database',
            filetypes=[('Imported SQLite database','*.sqlite *.db'),('All files','*.*')])
    if not path:
        return
    from legacy_viewer import Viewer
    win=tk.Toplevel(parent)
    win.withdraw()
    try:
        Viewer(win,Path(path))
    except (sqlite3.Error,ValueError,OSError,KeyError,TypeError) as error:
        win.destroy()
        messagebox.showerror('Cannot open database','Choose a database created by Import Database.\n\n'+str(error),parent=parent)
        return
    win.deiconify()


class ImportDialog:
    def __init__(self,parent):
        self.parent=parent
        self.win=tk.Toplevel(parent)
        self.win.title('Import Database - old FoxPro backup')
        self.win.geometry('740x390')
        self.win.transient(parent)
        self.win.grab_set()
        self.busy=False
        self.events=queue.Queue()
        self.source=tk.StringVar()
        self.destination=tk.StringVar()
        self.status=tk.StringVar(value='Choose the backup folder containing the old .DBF and .FPT files.')
        ttk.Label(self.win,text='Import the old database',font=('Segoe UI',16,'bold')).pack(anchor='w',padx=18,pady=15)
        ttk.Label(self.win,text='Use a backup made while everyone was out of the old program. Creates a separate read-only review database; original files and sample data are unchanged.',wraplength=690).pack(anchor='w',padx=18,pady=5)
        form=ttk.Frame(self.win)
        form.pack(fill='x',padx=18,pady=12)
        self.controls=[]
        for row,label,var,command in [(0,'Backup folder',self.source,self.choose_source),(1,'Save imported database',self.destination,self.choose_destination)]:
            ttk.Label(form,text=label).grid(row=row,column=0,sticky='w',pady=10)
            entry=ttk.Entry(form,textvariable=var,width=57)
            entry.grid(row=row,column=1,padx=8,pady=10,sticky='ew')
            button=ttk.Button(form,text='Browse...',command=command)
            button.grid(row=row,column=2)
            self.controls.extend([entry,button])
        form.columnconfigure(1,weight=1)
        ttk.Label(self.win,textvariable=self.status,wraplength=690).pack(anchor='w',padx=18,pady=8)
        self.progress=ttk.Progressbar(self.win,mode='indeterminate')
        self.progress.pack(fill='x',padx=18,pady=8)
        bar=ttk.Frame(self.win)
        bar.pack(fill='x',padx=18,pady=12)
        self.start=ttk.Button(bar,text='Import Database',command=self.begin)
        self.start.pack(side='right')
        self.controls.append(self.start)
        ttk.Button(bar,text='Close',command=self.close).pack(side='right',padx=8)
        self.win.protocol('WM_DELETE_WINDOW',self.close)

    def choose_source(self):
        path=filedialog.askdirectory(parent=self.win,title='Choose WC backup folder')
        if path:
            folder=Path(path)
            if not any(folder.glob('*.DBF')) and (folder/'WC').is_dir():
                folder=folder/'WC'
            self.source.set(str(folder))

    def choose_destination(self):
        path=filedialog.asksaveasfilename(parent=self.win,title='Save as a NEW database file',
            initialfile='WC-Imported.sqlite',defaultextension='.sqlite',
            filetypes=[('SQLite database','*.sqlite')])
        if path:
            self.destination.set(path)

    def begin(self):
        if self.busy:
            return
        source=Path(self.source.get()).expanduser()
        destination=Path(self.destination.get()).expanduser()
        if not self.source.get().strip() or not self.destination.get().strip():
            messagebox.showerror('Choose locations','Choose both the backup folder and a new destination filename.',parent=self.win)
            return
        if not source.is_dir() or not any(p.suffix.upper()=='.DBF' for p in source.iterdir() if p.is_file()):
            messagebox.showerror('No database files','Choose the extracted folder containing the .DBF files. It may be the WC folder inside WC_backup.',parent=self.win)
            return
        if destination.exists() or destination.resolve().is_relative_to(source.resolve()):
            messagebox.showerror('Choose a new destination','Choose a NEW file outside the backup folder. Existing databases are never overwritten.',parent=self.win)
            return
        self.busy=True
        for control in self.controls:
            control.configure(state='disabled')
        self.progress.start(12)
        self.status.set('Starting import...')
        def worker():
            from import_legacy import migrate
            try:
                report=migrate(source,destination,lambda text:self.events.put(('progress',text)))
                self.events.put(('done',(destination,report)))
            except Exception as error:
                self.events.put(('error',str(error)))
        threading.Thread(target=worker,daemon=False).start()
        self.win.after(100,self.poll)

    def poll(self):
        while True:
            try:
                kind,value=self.events.get_nowait()
            except queue.Empty:
                self.win.after(100,self.poll)
                return
            if kind=='progress':
                self.status.set(value)
                continue
            self.busy=False
            self.progress.stop()
            for control in self.controls:
                control.configure(state='normal')
            if kind=='error':
                self.status.set('Import failed. Original files were not changed.')
                messagebox.showerror('Import failed',value+'\n\nA partial destination may remain. Choose a new filename when retrying.',parent=self.win)
            else:
                path,report=value
                issues=sum(report['issues'].values())
                self.status.set(f'Imported {report["record_total"]:,} records from {len(report["tables"])} tables.')
                messagebox.showinfo('Import complete',
                    f'Imported {report["record_total"]:,} physical records from {len(report["tables"])} tables.\n'
                    f'Flagged source issues: {issues:,}.\n\nSaved to:\n{path}\n\nThe imported records will now open read-only. The adjacent .report.json contains the import inventory.',parent=self.win)
                self.win.grab_release()
                open_database(self.parent,path)
            return

    def close(self):
        if self.busy:
            messagebox.showinfo('Import in progress','Please let the import finish before closing this window.',parent=self.win)
            return
        self.win.destroy()
