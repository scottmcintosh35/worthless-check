"""Standalone Windows deployment entry point and bundled-runtime checks."""
import argparse
import datetime as dt
import json
import os
from pathlib import Path
import platform
import sqlite3
import sys
import traceback
import time
import uuid
import tkinter as tk
from tkinter import ttk,messagebox
import login
import users
import errno
import divisions
import desktop_theme
import document_mode

RELEASE='1.0.0-rc66'


def first_administrator(root,store,division=None,*,choices=(),on_select=None):
    from system_tools import login_dialog, division_picker
    if store.db.execute('SELECT 1 FROM staff_users WHERE active=1').fetchone():
        return login_dialog(root,store.db,division=division,choices=choices,on_select=on_select,maximized=True)
    win=tk.Toplevel(root)
    win.title((divisions.LABELS.get(division) or 'Worthless Check') + ' - First Run')
    if root.winfo_viewable():
        win.transient(root)
    win.grab_set()
    ttk.Label(win,text='Create the first Administrator',font=('Segoe UI',16,'bold')).grid(row=0,column=0,columnspan=2,padx=20,pady=18)
    ttk.Label(win,text='Create your own Administrator account. This workspace starts with no users, cases or payments. Sample cases are optional.',wraplength=550).grid(row=1,column=0,columnspan=2,padx=20,pady=8)
    fields={}
    for i,(key,label) in enumerate([('name','Staff name'),('username','Username'),('initials','Initials'),('password','Password / passphrase (12+ characters)'),('confirm','Confirm password')],2):
        ttk.Label(win,text=label).grid(row=i,column=0,padx=15,pady=9,sticky='w')
        entry=ttk.Entry(win,width=36,show='*' if key in ('password','confirm') else '')
        entry.grid(row=i,column=1,padx=15,pady=9)
        fields[key]=entry
    sample=tk.BooleanVar(value=False)
    ttk.Checkbutton(win,text='Add fictional sample cases for evaluation',variable=sample).grid(row=7,column=0,columnspan=2,padx=15,pady=12,sticky='w')
    if choices:
        division_picker(win, 9, division, choices, on_select)
    result=[]
    def create():
        try:
            if fields['password'].get()!=fields['confirm'].get():
                raise ValueError('Passwords do not match.')
            # Validate the password before creating any staff record.
            login.password_data(fields['password'].get())
            uid=users.save_user(store.db,fields['username'].get(),fields['name'].get(),fields['initials'].get(),'Administrator')
            login.set_password(store.db,uid,fields['password'].get(),bootstrap=True)
            login.authenticate(store.db,fields['username'].get(),fields['password'].get())
            if sample.get():
                store.seed()
            result.append(True)
            win.destroy()
        except (ValueError,sqlite3.Error) as error:
            messagebox.showerror('Cannot complete first run',str(error),parent=win)
    ttk.Button(win,text='Create Administrator and Open',command=create).grid(row=8,column=1,padx=15,pady=18)
    win.update_idletasks()
    win.deiconify()
    win.lift()
    fields['name'].focus_set()
    root.wait_window(win)
    return bool(result)


class DatabaseLock:
    def __init__(self,path,timeout=30):
        import msvcrt
        self.path=Path(str(path)+'.lock')
        self.path.parent.mkdir(parents=True,exist_ok=True)
        self.file=self.path.open('a+b')
        if self.file.tell()==0:
            self.file.write(b'0')
            self.file.flush()
        self.file.seek(0)
        deadline=time.monotonic()+timeout
        while True:
            try:
                msvcrt.locking(self.file.fileno(),msvcrt.LK_NBLCK,1)
                break
            except OSError as error:
                if error.errno not in (errno.EACCES,errno.EAGAIN,errno.EDEADLK):
                    self.file.close()
                    raise OSError('Could not acquire the database startup lock: '+str(error)) from error
                if time.monotonic()>=deadline:
                    self.file.close()
                    raise ValueError('Another application instance still holds the database startup lock. Check for an open first-run setup window in another RDP session, or a PikeCountyWC.exe process left by an earlier launch. Close that instance and try again. Lock error: '+str(error)) from error
                time.sleep(.1)

    def close(self):
        import msvcrt
        self.file.seek(0)
        msvcrt.locking(self.file.fileno(),msvcrt.LK_UNLCK,1)
        self.file.close()


def runtime_details():
    return {'release':RELEASE,'platform':platform.platform(),'architecture':platform.machine(),
        'python':sys.version,'sqlite':sqlite3.sqlite_version,'frozen':bool(getattr(sys,'frozen',False))}


def self_test(Store,App,result_file):
    import defendants
    import reporting
    import system_tools
    result_file=Path(result_file).resolve()
    result_file.parent.mkdir(parents=True,exist_ok=True)
    folder=result_file.parent/('self-test-'+uuid.uuid4().hex)
    folder.mkdir()
    store=None
    root=None
    checks=[]
    report=runtime_details()
    try:
        store=Store(folder/'evaluation.sqlite')
        store.seed()
        assert store.db.execute('SELECT COUNT(*) FROM bank_codes').fetchone()[0]==446
        assert store.db.execute('SELECT COUNT(*) FROM wc_codes').fetchone()[0]==16
        assert store.db.execute('SELECT COUNT(*) FROM zip_codes').fetchone()[0]==41870
        checks.append('Bundled reference assets and schema initialization')
        root=tk.Tk()
        root.withdraw()
        ui_errors=[]
        def create_visible_admin():
            window=next(w for w in root.winfo_children() if isinstance(w,tk.Toplevel))
            try:
                assert window.winfo_viewable(),'First-run setup window was hidden'
                for row,value in [(2,'SAMPLE SELF TEST'),(3,'selftest'),(4,'ST'),(5,'Fictional self-test passphrase'),(6,'Fictional self-test passphrase')]:
                    window.grid_slaves(row=row,column=1)[0].insert(0,value)
                window.grid_slaves(row=8,column=1)[0].invoke()
            except Exception as error:
                ui_errors.append(str(error))
                window.destroy()
        root.after(300,create_visible_admin)
        assert first_administrator(root,store) and not ui_errors,ui_errors
        checks.append('First-run Administrator window is actually visible with a hidden owner')
        login.logout(store.db)
        def sign_in_visible():
            window=next(w for w in root.winfo_children() if isinstance(w,tk.Toplevel))
            try:
                assert window.winfo_viewable() and window.state() == 'zoomed'
                form = window.children['login_form']
                assert form.place_info()['anchor'] == 'center'
                form.grid_slaves(row=0,column=1)[0].insert(0,'selftest')
                form.grid_slaves(row=1,column=1)[0].insert(0,'Fictional self-test passphrase')
                form.grid_slaves(row=3,column=1)[0].invoke()
            except Exception as error:
                ui_errors.append(str(error))
                window.destroy()
        root.after(300,sign_in_visible)
        assert system_tools.login_dialog(root,store.db,True,maximized=True) and not ui_errors,ui_errors
        checks.append('Startup login window is actually visible and completes sign-in')
        first_lock=DatabaseLock(folder/'lock-check.sqlite')
        try:
            try:
                unexpected=DatabaseLock(folder/'lock-check.sqlite',timeout=0)
            except ValueError:
                pass
            else:
                unexpected.close()
                raise AssertionError('Startup lock allowed overlapping initialization')
        finally:
            first_lock.close()
        recovered=DatabaseLock(folder/'lock-check.sqlite',timeout=0)
        recovered.close()
        checks.append('Startup lock blocks overlap and is reusable after release')
        pid=store.post(1,'2026-01-03','ST','Cash',[2500,0,0,0,0],'self-test-payment')
        assert sum(store.balance(1))==17000
        assert 'Total received: $25.00' in store.receipt(pid)
        assert store.post(1,'2026-01-03','ST','Cash',[2500,0,0,0,0],'self-test-payment')==pid
        checks.append('Atomic payment, receipt, balance and duplicate-request protection')
        content=reporting.build_report(store,'daily','2026-01-01','2026-01-31')
        assert 'TOTAL RECEIVED: $25.00' in content
        defendants.save_profile(store.db,{'NAME':'SAMPLE PERSON','ADDRESS':'SAMPLE ADDRESS','CITY':'SAMPLE CITY','STATE':'AL','ZIP':'36081'})
        labels,skipped=reporting.label_documents(store.db)
        assert len(labels)==1 and not skipped
        (folder/'labels.html').write_text(reporting.labels_html(labels,reporting.DEFAULT_LAYOUT),encoding='utf-8')
        checks.append('Daily report and printable address-label generation')
        from concurrent.futures import ThreadPoolExecutor
        for name in ('staffone','stafftwo'):
            staff=users.save_user(store.db,name,'SAMPLE '+name.upper(),name[-3:].upper(),'Staff')
            login.set_password(store.db,staff,'Fictional staff passphrase','Staff')
        def post_as_staff(name):
            gate=DatabaseLock(folder/'evaluation.sqlite')
            try:
                other=Store(folder/'evaluation.sqlite')
            finally:
                gate.close()
            try:
                login.authenticate(other.db,name,'Fictional staff passphrase')
                other.post(2,'2026-01-04','ignored','Cash',[10000,0,0,0,0],name)
            finally:
                login.logout(other.db)
                other.db.close()
        with ThreadPoolExecutor(2) as pool:
            list(pool.map(post_as_staff,('staffone','stafftwo')))
        assert sum(store.balance(2))==14550
        checks.append('Two authenticated staff connections posting to one local shared WAL database')
        revision=store.case(3)['revision']
        case=store.case(3)
        charges=[case[k] for k in reporting.PAY_KEYS[:4]]
        reporting.edit_case(store,3,{'merchant':'SAMPLE UPDATED MERCHANT'},charges,'Self-test first edit',expected_revision=revision)
        try:
            reporting.edit_case(store,3,{'merchant':'STALE SAMPLE EDIT'},charges,'Self-test stale editor',expected_revision=revision)
            raise AssertionError('A stale case edit was accepted')
        except ValueError:
            pass
        checks.append('Stale case edits rejected instead of overwriting another user')
        assert system_tools.calculate('0.1 + 0.2')=='0.3'
        app=App(root,store)
        root.update_idletasks()
        checks.append('Bundled Tcl/Tk and main application windows')
        sid,backup=reporting.close_month(store,'2026-01')
        assert sid and backup.exists()
        reporting.reopen_month(store.db,'2026-01','Self-test reopen')
        assert store.db.execute('PRAGMA integrity_check').fetchone()[0]=='ok'
        checks.append('Month snapshot, backup, reopen and database integrity')
        report.update(status='passed',checks=checks,test_data_folder=str(folder))
        return_code=0
    except Exception:
        report.update(status='failed',checks=checks,error=traceback.format_exc(),test_data_folder=str(folder))
        return_code=1
    finally:
        if root is not None:
            root.destroy()
        if store is not None:
            login.logout(store.db)
            store.db.close()
        result_file.write_text(json.dumps(report,indent=2),encoding='utf-8')
    return return_code


def validate_output_workspace(db, division, mode):
    if mode != document_mode.OFFICIAL and db.execute(
        "SELECT 1 FROM legacy_work_meta WHERE key='official_payments_started'"
    ).fetchone():
        raise ValueError('Official payments have started in this workspace. Open it using the official production launcher.')
    if mode == document_mode.TEST:
        return
    import legacy_work
    import main_legacy
    if not main_legacy.enabled(db) or legacy_work.source_division(db) != division:
        raise ValueError('Official output requires the full imported history for the selected division.')
    if mode == document_mode.OFFICIAL and legacy_work.has_unofficial_payments(db):
        raise ValueError('This workspace contains test or rehearsal payments. Use the verified final cutoff import for official output.')


def open_store(Store, root, data, division, *, choices=(), on_select=None, output_mode=document_mode.TEST):
    lock = DatabaseLock(data)
    store = None
    success = False
    try:
        store = Store(data)
        validate_output_workspace(store.db, division, output_mode)
        store.document_mode = output_mode
        from system_tools import login_dialog
        if login.enabled(store.db):
            lock.close()
            lock = None
            if choices:
                success = login_dialog(root, store.db, True, division, choices=choices, on_select=on_select, maximized=True)
            else:
                success = login_dialog(root, store.db, True, division, maximized=True)
        else:
            if division == 'enterprise' and not divisions.is_windows_admin():
                raise ValueError('A Windows administrator must set up Office 2 before staff can sign in.')
            success = first_administrator(root, store, division, choices=choices, on_select=on_select)
        if success:
            return store
    finally:
        if lock is not None:
            lock.close()
        if store is not None and not success:
            close_store(store)


def close_store(store):
    try:
        login.logout(store.db)
    finally:
        store.db.close()


def resolve_workspace(explicit_data=None, division=None, output_mode=document_mode.TEST):
    """Choose storage without opening or changing any database.

    A normal shortcut is personal. Only an explicit division or an exact shared
    database path enters the Windows-group-protected shared workspace flow.
    """
    if explicit_data is not None:
        explicit_data = Path(explicit_data).resolve()
        for key in divisions.LABELS:
            if explicit_data == divisions.data_path(key).resolve():
                division, explicit_data = key, None
                break
    if division is not None:
        allowed = divisions.allowed_divisions()
        if division not in allowed:
            raise ValueError('Ask your administrator for Windows group access to the selected shared office.')
        return divisions.data_path(division).resolve(), division, allowed
    if output_mode != document_mode.TEST:
        raise ValueError('Official output requires an explicitly selected, configured shared office.')
    if explicit_data is not None:
        return explicit_data, None, ()
    local = os.environ.get('LOCALAPPDATA')
    if not local:
        raise ValueError('Windows Local AppData is unavailable. Select a local workspace with --data.')
    return (Path(local) / 'WorthlessCheck' / 'Data' / 'wc.sqlite').resolve(), None, ()


def run(Store, App):
    parser = argparse.ArgumentParser()
    parser.add_argument('--data', type=Path)
    parser.add_argument('--division', choices=divisions.LABELS)
    parser.add_argument('--imported-db', type=Path)
    parser.add_argument('--output-mode', choices=(document_mode.OFFICIAL, document_mode.REHEARSAL), default=document_mode.TEST)
    parser.add_argument('--self-test', type=Path, metavar='RESULT_JSON')
    args = parser.parse_args()
    if args.self_test:
        return self_test(Store, App, args.self_test)
    if args.imported_db:
        import legacy_viewer
        legacy_viewer.launch(args.imported_db)
        return 0
    if args.data and args.division:
        parser.error('--data and --division cannot be combined')
    if args.data and args.output_mode != document_mode.TEST:
        parser.error('Official output requires a configured division workspace.')
    data, division, allowed = resolve_workspace(args.data, args.division, args.output_mode)
    if str(data).startswith(chr(92)*2):
        raise ValueError('Use a local disk for this desktop evaluation database.')
    data = data.resolve()
    if args.output_mode == document_mode.OFFICIAL:
        shared_profile = Path(os.environ['ALLUSERSPROFILE']).resolve()
        configured_profile = Path(os.environ['PROGRAMDATA']).resolve()
        if configured_profile != shared_profile:
            raise ValueError('Use the official-output rehearsal mode for a copied workspace.')
        if not data.is_file():
            raise ValueError('Load the verified final cutoff import before starting official output.')
    if args.output_mode == document_mode.REHEARSAL:
        profile = Path(os.environ['PROGRAMDATA']).resolve()
        local = Path(os.environ['LOCALAPPDATA']).resolve()
        label = {'office1':'Office1','enterprise':'Office2'}.get(args.division)
        expected = divisions.data_path(args.division).absolute() if label else None
        if (not label or profile.parent != local or
                not profile.name.startswith(f'WorthlessCheck-{label}-Rehearsal-') or
                expected != data or not data.is_file()):
            raise ValueError('Run the official-output rehearsal from its isolated launcher and verified backup copy.')

    startup_choices = allowed if args.division is None and len(allowed) > 1 else ()
    store = None
    while True:
        root = tk.Tk()
        desktop_theme.apply(root)
        root.withdraw()
        next_session = None
        login_target = None

        def select_login_division(target):
            nonlocal login_target
            if target in divisions.allowed_divisions():
                login_target = target

        def callback_error(kind, error, tb):
            log_folder = data.parent / 'logs'
            log_folder.mkdir(parents=True, exist_ok=True)
            path = log_folder / ('error-' + dt.datetime.now().strftime('%Y%m%d-%H%M%S') + '.txt')
            path.write_text(''.join(traceback.format_exception(kind,error,tb)), encoding='utf-8')
            messagebox.showerror('Application error', 'The action could not be completed. Details saved to ' + str(path), parent=root)

        def switch(target):
            nonlocal next_session
            if target == division or target not in divisions.allowed_divisions():
                return
            if any(isinstance(child, tk.Toplevel) and child.winfo_viewable() for child in root.winfo_children()):
                messagebox.showinfo('Switch division', 'Close open application dialogs before switching divisions.', parent=root)
                return
            if not messagebox.askokcancel('Switch division',
                    'Sign in to ' + divisions.LABELS[target] + '? Save any changes in the current division before switching.',
                    parent=root):
                return
            destination = divisions.data_path(target).resolve()
            try:
                other = open_store(Store, root, destination, target, output_mode=args.output_mode)
            except (OSError, ValueError, sqlite3.Error) as error:
                messagebox.showerror('Switch division', str(error), parent=root)
                return
            if other is not None:
                next_session = (target, destination, other)
                root.quit()

        root.report_callback_exception = callback_error
        try:
            if store is None:
                store = open_store(Store, root, data, division,
                                   choices=startup_choices, on_select=select_login_division, output_mode=args.output_mode)
            if store is None:
                if login_target is not None:
                    division = login_target
                    data = divisions.data_path(division).resolve()
                    continue
                return 0
            store.division = division
            store.division_choices = () if args.output_mode == document_mode.REHEARSAL else allowed
            store.switch_division = switch
            App(root, store)
            label = users.workspace_label(store.db)
            root.title(label + ' | Worthless Check | ' + RELEASE + ' | ' + login.current(store.db)['username'])
            root.state('zoomed')
            root.deiconify()
            root.mainloop()
        finally:
            try:
                root.destroy()
            except tk.TclError:
                pass
            if store is not None:
                close_store(store)
        if next_session is None:
            return 0
        division, data, store = next_session
