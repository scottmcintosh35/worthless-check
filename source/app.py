import date_format
import login_activity
import legacy_navigation
import shortcuts
import main_legacy
import performance
"""Worthless Check review prototype. Standard library only. Sample data only."""
import argparse
import datetime as dt
from decimal import Decimal, InvalidOperation
import os
from pathlib import Path
import sqlite3
import tkinter as tk
from tkinter import ttk, messagebox, filedialog
import uuid
import json
import defendants
import import_dialog
import test_migration
import legacy_work
import legacy_functions
import case_defaults
from office import show_heading
import desktop_theme
import divisions
import users
import banks
import lookups
import database_tools
import database_ui
import login
import user_audit
import system_tools
import reporting
import functions_ui

ROOT = Path(__file__).resolve().parent
CATEGORIES = ('Restitution', 'Merchant fee', 'DA / warrant fee', 'Withdrawal fee', 'Overpayment')


def cents(value):
    try:
        amount = Decimal(str(value).strip())
        if not amount.is_finite() or amount < 0 or amount > Decimal('99999999.99'):
            raise ValueError('Enter a nonnegative amount below $100,000,000.')
        if amount != amount.quantize(Decimal('.01')):
            raise ValueError('Amounts must have at most two decimal places.')
        return int(amount * 100)
    except InvalidOperation:
        raise ValueError('Enter a valid dollar amount.') from None


def dollars(value):
    return f'${value / 100:,.2f}'


def valid_date(value):
    try:
        return date_format.parse(value).isoformat()
    except ValueError:
        raise ValueError('Dates must use MM-DD-YYYY.') from None


class Store:
    def __init__(self, path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(self.path, timeout=30)
        self.db.row_factory = sqlite3.Row
        self.db.execute('PRAGMA journal_mode=WAL')
        self.db.execute('PRAGMA synchronous=FULL')
        self.db.execute('PRAGMA busy_timeout=30000')
        self.db.execute('PRAGMA foreign_keys=ON')
        self.db.executescript('''
        CREATE TABLE IF NOT EXISTS cases (
          id INTEGER PRIMARY KEY, case_no TEXT NOT NULL UNIQUE,
          defendant TEXT NOT NULL, merchant TEXT NOT NULL, check_no TEXT NOT NULL,
          entered TEXT NOT NULL, due_date TEXT,
          restitution INTEGER NOT NULL CHECK(restitution>=0),
          merchant_fee INTEGER NOT NULL CHECK(merchant_fee>=0),
          da_fee INTEGER NOT NULL CHECK(da_fee>=0),
          withdrawal_fee INTEGER NOT NULL CHECK(withdrawal_fee>=0));
        CREATE TABLE IF NOT EXISTS payments (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          request_id TEXT NOT NULL UNIQUE,
          case_id INTEGER NOT NULL REFERENCES cases(id),
          paid_date TEXT NOT NULL, posted_at TEXT NOT NULL,
          operator TEXT NOT NULL, method TEXT NOT NULL,
          restitution INTEGER NOT NULL CHECK(restitution>=0),
          merchant_fee INTEGER NOT NULL CHECK(merchant_fee>=0),
          da_fee INTEGER NOT NULL CHECK(da_fee>=0),
          withdrawal_fee INTEGER NOT NULL CHECK(withdrawal_fee>=0),
          overpayment INTEGER NOT NULL CHECK(overpayment>=0),
          CHECK(restitution+merchant_fee+da_fee+withdrawal_fee+overpayment>0));
        CREATE TABLE IF NOT EXISTS audit (
          id INTEGER PRIMARY KEY, at TEXT NOT NULL, operator TEXT NOT NULL,
          action TEXT NOT NULL, reference TEXT NOT NULL);
        ''')
        defendants.setup(self.db)
        users.setup(self.db)
        banks.setup(self.db)
        lookups.setup(self.db)
        database_tools.setup(self.db)
        login.setup(self.db)
        reporting.setup(self.db)
        legacy_work.setup(self.db)
        performance.setup(self.db)

    def seed(self):
        if self.db.execute('SELECT COUNT(*) FROM cases').fetchone()[0]:
            return
        today = dt.date.today().isoformat()
        with self.db:
            self.db.executemany('''INSERT INTO cases
              (case_no,defendant,merchant,check_no,entered,due_date,restitution,merchant_fee,da_fee,withdrawal_fee)
              VALUES (?,?,?,?,?,?,?,?,?,?)''', [
                ('DEMO-001','SAMPLE PERSON A','SAMPLE MARKET','1001',today,today,12500,3000,4000,0),
                ('DEMO-002','SAMPLE PERSON B','SAMPLE HARDWARE','1002',today,today,27550,3000,4000,0),
                ('DEMO-003','SAMPLE PERSON A','SAMPLE MARKET','1003',today,today,8000,3000,4000,0)])

    def cases(self, search=''):
        pattern = '%' + search + '%'
        return self.db.execute('''SELECT * FROM cases WHERE archived=0 AND (case_no LIKE ? OR defendant LIKE ?
            OR merchant LIKE ?) ORDER BY case_no''', (pattern,pattern,pattern)).fetchall()

    def cases_with_balances(self,search=''):
        pattern='%'+search+'%'
        return self.db.execute('''WITH paid AS (
          SELECT case_id,SUM(restitution+merchant_fee+da_fee+withdrawal_fee) AS total
          FROM payments WHERE voided=0 GROUP BY case_id), adjusted AS (
          SELECT case_id,SUM(restitution+merchant_fee+da_fee+withdrawal_fee) AS total
          FROM adjustments GROUP BY case_id)
          SELECT c.*,c.restitution+c.merchant_fee+c.da_fee+c.withdrawal_fee
            +COALESCE(a.total,0)-COALESCE(p.total,0) AS balance_due
          FROM cases c LEFT JOIN paid p ON p.case_id=c.id LEFT JOIN adjusted a ON a.case_id=c.id
          WHERE c.archived=0 AND (c.case_no LIKE ? OR c.defendant LIKE ? OR c.merchant LIKE ?)
          ORDER BY c.case_no''',(pattern,pattern,pattern)).fetchall()

    def case(self, case_id):
        row = self.db.execute('SELECT * FROM cases WHERE id=?',(case_id,)).fetchone()
        if row is None:
            raise ValueError('Case not found.')
        return row

    def paid(self, case_id):
        return self.db.execute('''SELECT COALESCE(SUM(restitution),0),COALESCE(SUM(merchant_fee),0),
            COALESCE(SUM(da_fee),0),COALESCE(SUM(withdrawal_fee),0),COALESCE(SUM(overpayment),0)
            FROM payments WHERE case_id=? AND voided=0''',(case_id,)).fetchone()

    def balance(self, case_id):
        case, paid = self.case(case_id), self.paid(case_id)
        adjustments=self.db.execute('''SELECT COALESCE(SUM(restitution),0),COALESCE(SUM(merchant_fee),0),
            COALESCE(SUM(da_fee),0),COALESCE(SUM(withdrawal_fee),0) FROM adjustments WHERE case_id=?''',(case_id,)).fetchone()
        return [case[key]+adjustments[i]-paid[i] for i,key in enumerate(('restitution','merchant_fee','da_fee','withdrawal_fee'))]

    def create_case(self, number, defendant, merchant, check_no, date, amounts,bank_id=None):
        actor=login.require(self.db)
        if not all(x.strip() for x in (defendant,merchant,check_no)):
            raise ValueError('Complete all case identification fields.')
        date = valid_date(date)
        if len(amounts) != 4 or any(type(v) is not int or v < 0 for v in amounts):
            raise ValueError('Invalid charges.')
        with self.db:
            self.db.execute('BEGIN IMMEDIATE')
            reporting.assert_open(self.db,date)
            if not number.strip():
                number=database_tools.allocate(self.db,'case')
            if bank_id is not None and not self.db.execute('SELECT 1 FROM bank_codes WHERE id=? AND active=1',(bank_id,)).fetchone():
                raise ValueError('Choose an active bank from the bank list.')
            cur = self.db.execute('''INSERT INTO cases
                (case_no,defendant,merchant,check_no,entered,due_date,restitution,merchant_fee,da_fee,withdrawal_fee,bank_id)
                VALUES(?,?,?,?,?,?,?,?,?,?,?)''',(number.strip(),defendant.strip(),merchant.strip(),check_no.strip(),date,case_defaults.due_date(self.db,date).isoformat(),*amounts,bank_id))
            self.db.execute('INSERT INTO audit(at,operator,action,reference) VALUES(?,?,?,?)',
                (dt.datetime.now(dt.timezone.utc).isoformat(), actor, 'CREATE_CASE',str(cur.lastrowid)))

    def post(self, case_id, date, operator, method, amounts, request_id):
        actor=login.require(self.db)
        if login.enabled(self.db):
            operator=login.initials(self.db)
        date = valid_date(date)
        if not operator.strip() or method not in ('Cash','Money order','Other'):
            raise ValueError('Provide operator initials and a payment method.')
        if len(amounts) != 5 or any(type(v) is not int or v < 0 for v in amounts) or sum(amounts) <= 0:
            raise ValueError('Enter a positive payment with nonnegative allocations.')
        if not request_id:
            raise ValueError('Missing payment request identifier.')
        try:
            self.db.execute('BEGIN IMMEDIATE')
            old = self.db.execute('SELECT * FROM payments WHERE request_id=?',(request_id,)).fetchone()
            if old:
                expected = (case_id,date,operator.strip(),method,*amounts)
                actual = tuple(old[k] for k in ('case_id','paid_date','operator','method','restitution','merchant_fee','da_fee','withdrawal_fee','overpayment'))
                if expected != actual:
                    raise ValueError('This payment identifier already belongs to a different payment.')
                self.db.rollback()
                return old['id']
            if self.case(case_id)['archived']:
                raise ValueError('Restore this archived case before posting a payment.')
            reporting.assert_open(self.db,date)
            remaining = self.balance(case_id)
            for i in range(4):
                if amounts[i] > remaining[i]:
                    raise ValueError(f'{CATEGORIES[i]} exceeds the remaining balance. Use the separate overpayment field if appropriate.')
            now = dt.datetime.now(dt.timezone.utc).isoformat()
            cur = self.db.execute('''INSERT INTO payments
                (request_id,case_id,paid_date,posted_at,operator,method,restitution,merchant_fee,da_fee,withdrawal_fee,overpayment)
                VALUES(?,?,?,?,?,?,?,?,?,?,?)''',(request_id,case_id,date,now,operator.strip(),method,*amounts))
            receipt_code=database_tools.allocate(self.db,'receipt')
            case=self.case(case_id)
            party={k:case[k] for k in ('case_no','defendant','merchant','check_no')}
            party['remaining_amounts'] = self.balance(case_id)
            party['remaining_balance'] = sum(party['remaining_amounts'])
            self.db.execute('UPDATE payments SET receipt_code=?,party_snapshot=? WHERE id=?',(receipt_code,json.dumps(party),cur.lastrowid))
            self.db.execute('INSERT INTO audit(at,operator,action,reference) VALUES(?,?,?,?)',
                (now,actor if login.enabled(self.db) else operator.strip(),'POST_PAYMENT',str(cur.lastrowid)))
            self.db.commit()
            return cur.lastrowid
        except Exception:
            self.db.rollback()
            raise

    def receipt(self, payment_id):
        p = self.db.execute('SELECT * FROM payments WHERE id=?',(payment_id,)).fetchone()
        c = json.loads(p['party_snapshot']) if p['party_snapshot'] else self.case(p['case_id'])
        amounts = [p[k] for k in ('restitution','merchant_fee','da_fee','withdrawal_fee','overpayment')]
        balance_lines = {}
        if 'remaining_amounts' in c:
            balance_lines = legacy_work.receipt_balance_lines(c['remaining_amounts'], dollars)
        else:
            if 'remaining_balance' in c:
                balance_lines['Remaining balance after payment'] = dollars(c['remaining_balance'])
            balance_lines.update(legacy_work.receipt_balance_lines(self.balance(p['case_id']), dollars, current=True))
        return '\n'.join([users.document_heading(self.db),users.document_contact(self.db),'','DEMONSTRATION RECEIPT - NOT AN OFFICIAL RECEIPT',
            ('VOID - '+p['void_reason']) if p['voided'] else '',
            f'Receipt: {p["receipt_code"]}',f'Case: {c["case_no"]}',f'Defendant: {c["defendant"]}',
            f'Merchant: {c["merchant"]}',f'Check: {c["check_no"]}',f'Payment date: {date_format.display(p["paid_date"])}',
            f'Posted (UTC): {date_format.timestamp(p["posted_at"])}',f'Operator: {p["operator"]} | Method: {p["method"]}', '',
            *[f'{label}: {dollars(value)}' for label,value in zip(CATEGORIES,amounts)],
            f'Total received: {dollars(sum(amounts))}', '',
            *[f'{label}: {value}' for label,value in balance_lines.items()], '',
            'Sample workflow; no official fee schedule or fund distribution applied.'])

    def summary(self, start, end):
        start, end = valid_date(start), valid_date(end)
        if start > end:
            raise ValueError('The start date must precede the end date.')
        rows = self.db.execute('''SELECT p.*,c.case_no,c.defendant,c.merchant FROM payments p
            JOIN cases c ON c.id=p.case_id WHERE p.voided=0 AND paid_date BETWEEN ? AND ? ORDER BY paid_date,p.id''',(start,end)).fetchall()
        keys = ('restitution','merchant_fee','da_fee','withdrawal_fee','overpayment')
        totals = [sum(r[k] for r in rows) for k in keys]
        return '\n'.join([users.document_heading(self.db),users.document_contact(self.db),'','DEMONSTRATION COLLECTION SUMMARY',f'Payment dates: {date_format.display(start)} through {date_format.display(end)}',
            'This does not close an accounting period or distribute funds.', '',
            *[f'{label}: {dollars(value)}' for label,value in zip(CATEGORIES,totals)],
            f'Total: {dollars(sum(totals))}',f'Payment count: {len(rows)}','',
            *[f'{r["receipt_code"]} | {date_format.display(r["paid_date"])} | {r["case_no"]} | {dollars(sum(r[k] for k in keys))}' for r in rows]])


class App:
    def __init__(self, root, store):
        self.root, self.store = root, store
        self.database_tools=database_ui.DatabaseUI(self)
        self.system_tools=system_tools.SystemTools(self)
        self.functions_tools=functions_ui.FunctionsUI(self)
        root.title('Check Management | Review Prototype')
        root.geometry('1100x750')
        root.minsize(900,650)
        desktop_theme.apply(root)
        style = ttk.Style(root)
        self.division = getattr(store, 'division', None)
        choices = getattr(store, 'division_choices', ())
        if choices:
            selector = ttk.Notebook(root, height=1)
            selector.pack(fill='x', padx=18, pady=(8, 0))
            for key, label in divisions.LABELS.items():
                selector.add(ttk.Frame(selector), text=label,
                             state='normal' if key in choices else 'disabled')
            keys = list(divisions.LABELS)
            current = keys.index(self.division)
            selector.select(current)

            def choose_division(event):
                target = selector.index(selector.select())
                if target != current:
                    selector.select(current)
                    store.switch_division(keys[target])

            selector.bind('<<NotebookTabChanged>>', choose_division)
        self.office_heading = show_heading(root, users.document_heading(store.db).splitlines())
        self.mode_banner=ttk.Label(root,text='SERVER EVALUATION',foreground=desktop_theme.WARNING);self.mode_banner.pack(anchor='w',padx=20,pady=(0,12))
        database_actions=ttk.Frame(root)
        database_actions.pack(fill='x',padx=20,pady=(0,8))
        ttk.Button(database_actions,text='Complete Legacy Workspace',command=lambda:legacy_work.open_workspace(self)).pack(side='left',padx=8)
        ttk.Button(database_actions,text='Import Database...',command=lambda:import_dialog.ImportDialog(root)).pack(side='left')
        ttk.Button(database_actions,text='Open Imported Database...',command=lambda:import_dialog.open_database(root)).pack(side='left',padx=8)
        style.configure('Main.TNotebook.Tab', font=('Segoe UI', 10), padding=(10, 6))
        self.tabs = ttk.Notebook(root, style='Main.TNotebook')
        self.tabs.pack(fill='both',expand=True,padx=12,pady=8)
        cases_page = ttk.Frame(self.tabs)
        defendants_page = ttk.Frame(self.tabs)
        reconciliation_page = ttk.Frame(self.tabs)
        reports_page = ttk.Frame(self.tabs)
        for page,title in [(cases_page,'Cases / Payments'),(defendants_page,'Defendant Information'),(reconciliation_page,'Reconciliation'),(reports_page,'Reports / Month-End')]:
            self.tabs.add(page,text=title)
        users_page=ttk.Frame(self.tabs)
        office_page=ttk.Frame(self.tabs)
        self.tabs.add(users_page,text='Users')
        self.tabs.add(office_page,text='Office Information')
        self.staff_directory=users.StaffDirectory(self,users_page)
        self.office_form=users.OfficeForm(self,office_page)
        def refresh_tab(event=None):
            selected_tab = self.tabs.select()
            if selected_tab == str(defendants_page) and hasattr(self, 'directory'):
                self.directory.refresh()
            if selected_tab==str(office_page):
                names=[r[0] for r in self.store.db.execute('SELECT full_name FROM staff_users WHERE active=1 ORDER BY full_name')]
                for key,_ in users.COORDINATORS:
                    self.office_form.entries[key].configure(values=names)
        self.tabs.bind('<<NotebookTabChanged>>',refresh_tab)
        tools = ttk.Frame(cases_page)
        tools.pack(fill='x',padx=20)
        self.query = tk.StringVar()
        self.case_offset=0;self.case_has_next=False;self._case_query=None;self._case_mode=None
        ttk.Label(tools,text='Search cases, defendants, or merchants:').pack(side='left')
        entry = ttk.Entry(tools,textvariable=self.query,width=32)
        entry.pack(side='left',padx=8)
        entry.bind('<Return>',lambda e:self.refresh())
        self.case_search_entry=entry
        self.case_buttons={}
        for title,command in [('Search',self.refresh),('New sample case',self.new_case),('Collection summary',self.report)]:
            button=ttk.Button(tools,text=title,command=command);button.pack(side='left',padx=4);self.case_buttons[title]=button
        self.shortcut_strip=shortcuts.strip(cases_page,'Ctrl+Enter: Details   |   Ctrl+W: Payment history   |   Ctrl+F: Search   |   F5: Refresh   |   Esc: Clear selection   |   F1: Shortcuts')
        self.tree = ttk.Treeview(cases_page,columns=('number','defendant','merchant','due','source'),show='headings',height=9)
        for col,title,width in [('number','Case number',140),('defendant','Defendant',250),('merchant','Merchant',300),('due','Balance due',140),('source','Source row',90)]:
            self.tree.heading(col,text=title)
            self.tree.column(col,width=width)
        self.tree.pack(fill='both',expand=True,padx=20,pady=15)
        self.tree.bind('<<TreeviewSelect>>',lambda e:self.select())
        self.tree.bind('<Double-1>',lambda e:self.edit_case())
        self.shortcut_handlers=shortcuts.bind_list(self.tree,{'<Control-Return>':self.edit_case,'<Control-w>':self.history,'<Control-f>':lambda:shortcuts.focus_search(self.case_search_entry),'<F5>':self.refresh,'<Escape>':lambda:shortcuts.clear_selection(self.tree),'<F1>':self.show_shortcuts})
        pager=ttk.Frame(cases_page);pager.pack(fill='x',padx=20)
        self.case_previous=ttk.Button(pager,text='Previous 150',command=lambda:self.case_page(-1));self.case_previous.pack(side='left')
        self.case_next=ttk.Button(pager,text='Next 150',command=lambda:self.case_page(1));self.case_next.pack(side='left',padx=8)
        self.case_status=tk.StringVar();ttk.Label(pager,textvariable=self.case_status).pack(side='left')
        self.detail = tk.StringVar(value='Select a case.')
        self.detail_label=ttk.Label(cases_page,textvariable=self.detail,font=('Segoe UI',11),wraplength=1000)
        self.detail_label.pack(anchor='w',padx=20)
        bottom = ttk.Frame(cases_page)
        bottom.pack(side='bottom',fill='x',padx=20,pady=8,before=self.tree)
        self.detail_label.pack(side='bottom',fill='x',padx=20,pady=(2,4),before=self.tree)
        pager.pack(side='bottom',fill='x',padx=20,pady=3,before=self.tree)
        self.payment_button=ttk.Button(bottom,text='Record sample payment',command=self.payment);self.payment_button.pack(side='left')
        self.history_button=ttk.Button(bottom,text='Payment history / receipts',command=self.history);self.history_button.pack(side='left',padx=8)
        self.backup_button=ttk.Button(bottom,text='Back up database',command=self.backup);self.backup_button.pack(side='right')
        self.case_buttons['New sample case'].configure(style='Primary.TButton')
        ttk.Label(root,text=f'Data: {store.path}',foreground=desktop_theme.MUTED).pack(anchor='w',padx=20,pady=(0,12))
        self.refresh()
        self.directory = defendants.Directory(self,defendants_page)
        defendants.show_reconciliation(self,reconciliation_page)
        report_actions = ttk.Frame(reports_page, padding=16)
        report_actions.pack(fill='x')
        ttk.Label(report_actions, text='Reports and month-end', font=('Segoe UI', 16, 'bold')).grid(
            row=0, column=0, columnspan=3, sticky='w', pady=(0, 10))
        import release_review
        actions = [('Production setup review', lambda: release_review.show(self)),
                   ('Payment register by date', lambda: legacy_functions.open_for_app(self, 'receipts.range')),
                   ('Outstanding case balances', lambda: release_review.show(self, balances=True)),
                   ('Collection summary by date', self.report), *self.functions_tools.commands()[1:]]
        for column in range(3):
            report_actions.columnconfigure(column, weight=1, uniform='report')
        for index, (label, command) in enumerate(actions):
            row, column = divmod(index, 3)
            ttk.Button(report_actions, text=label, command=command).grid(
                row=row + 1, column=column, sticky='ew', padx=4, pady=4)

        navigation = tk.Menu(root)
        def menu(label):
            item=tk.Menu(navigation,tearoff=False)
            navigation.add_cascade(label=label,menu=item)
            return item
        def pending(item,labels):
            for label in labels:
                item.add_command(label=label+' (pending)',state='disabled')
        system=menu('System')
        system.add_command(label='User Information',command=lambda:self.tabs.select(office_page))
        system.add_command(label='Manage Users',command=lambda:self.tabs.select(users_page))
        system.add_command(label='Add User',command=lambda:self.staff_directory.edit())
        system.add_command(label='About',command=self.system_tools.about)
        system.add_command(label='Calculator',command=self.system_tools.calculator)
        system.add_command(label='Calendar/Diary',command=self.system_tools.diary)
        system.add_command(label='Reconciliation Browse',command=lambda:self.tabs.select(reconciliation_page))
        system.add_command(label='Login to System',command=self.system_tools.sign_in)
        system.add_command(label='User Activity Audit',command=lambda:user_audit.show(self))
        system.add_command(label='Edit Login/Password',command=self.system_tools.credentials)
        system.add_command(label='Sign out / Switch user',command=self.system_tools.sign_out)
        system.add_command(label='EXIT TO Windows',command=root.destroy)
        file_menu=menu('File')
        file_menu.add_command(label='Import Database...',command=lambda:import_dialog.ImportDialog(root))
        file_menu.add_command(label='Open Imported Database...',command=lambda:import_dialog.open_database(root))
        file_menu.add_separator()
        file_menu.add_command(label='New sample case',command=self.new_case)
        file_menu.add_command(label='Back up prototype database',command=self.backup)
        file_menu.add_command(label='Exit',command=root.destroy)
        edit=menu('Edit')
        def update_edit_menu():
            edit.delete(0,'end')
            edit.add_command(label='Defendant Information',command=lambda:self.tabs.select(defendants_page))
            edit.add_separator()
            directory=self.tabs.select()==str(defendants_page)
            actions=[('Defendant details' if directory else 'Case details','Ctrl+Enter',self.directory.edit_selected if directory else self.edit_case),
              ('Link to sample case' if directory else 'Payment history / receipts','Ctrl+W',self.directory.link if directory else self.history),
              ('Find defendants' if directory else 'Find cases','Ctrl+F',lambda:shortcuts.focus_search(self.directory.search_entry if directory else self.case_search_entry)),
              ('Refresh list','F5',self.directory.refresh if directory else self.refresh),
              ('Clear selection','Esc',lambda:shortcuts.clear_selection(self.directory.tree if directory else self.tree)),
              ('Keyboard shortcuts','F1',self.show_shortcuts)]
            for label,key,command in actions:
                if directory and key == 'Ctrl+W' and self.legacy_mode():
                    continue
                edit.add_command(label=label,accelerator=key,command=command)
        edit.configure(postcommand=update_edit_menu);update_edit_menu()

        program=menu('Program')
        program.add_command(label='Review prototype information',command=lambda:self.show_text('Prototype information',(ROOT/'VERSION-14.txt').read_text(encoding='utf-8')))
        database=menu('Database')
        database.add_command(label='Import Database...',command=lambda:import_dialog.ImportDialog(root))
        database.add_command(label='Complete Legacy Workspace...',command=lambda:legacy_work.open_workspace(self))
        database.add_command(label='Load Legacy Data for Testing...',command=lambda:test_migration.dialog(self))
        database.add_command(label='Review Original Legacy Records',command=lambda:import_dialog.open_database(root,self.store.path))
        database.add_command(label='Open Imported Database...',command=lambda:import_dialog.open_database(root))
        database.add_separator()
        database.add_command(label='Defendant Information',command=lambda:self.tabs.select(defendants_page))
        database.add_command(label='Bank Codes',command=lambda:banks.BankDirectory(self))
        database.add_command(label='WC Codes',command=lambda:lookups.Directory(root,self.store.db,'wc'))
        database.add_command(label='Zip Codes',command=lambda:lookups.Directory(root,self.store.db,'zip'))
        for label,kind in [('Case Number','case'),('Adjustment Number','adjustment'),('Receipt Number','receipt'),('Defendant ID','defendant'),('Merchant ID','merchant')]:
            database.add_command(label=label,command=lambda kind=kind:self.database_tools.numbering(kind))
        database.add_command(label='Merchant directory',command=self.database_tools.merchants)
        database.add_command(label='Modify table structures',command=self.database_tools.schema)
        database.add_command(label='Reindex',command=self.database_tools.reindex)
        database.add_command(label='View Deleted Records',command=self.database_tools.deleted)
        database.add_command(label='View Deleted Payments',command=lambda:self.database_tools.deleted(True))
        database.add_command(label='Index Adjustment Table',command=lambda:self.database_tools.reindex(True))
        database.add_command(label='View Adjustment Records',command=self.database_tools.adjustments)
        database.add_command(label='Supervisor Actions',command=self.database_tools.supervisor)
        def legacy_database_menu():
            if self.legacy_mode():legacy_navigation.populate(database,self)
        database.configure(postcommand=legacy_database_menu);legacy_database_menu()
        functions=menu('Functions')
        legacy_functions.populate_menu(functions,lambda action:legacy_functions.open_for_app(self,action),self.store.db)
        sample=tk.Menu(functions,tearoff=False)
        sample.add_command(label='New sample case',command=self.new_case)
        sample.add_command(label='Record sample payment',command=self.payment)
        for label,command in self.functions_tools.commands():sample.add_command(label=label,command=command)
        functions.add_separator();functions.add_cascade(label='Earlier sample data tools',menu=sample)
        help_menu=menu('Help');help_menu.add_command(label='Keyboard Shortcuts',accelerator='F1',command=self.show_shortcuts)
        root.bind('<F1>',lambda event:(self.show_shortcuts(),'break')[1])
        navigation.add_command(label='Quit',command=root.destroy)
        root.configure(menu=navigation)
        def refresh_shared_cases():
            nonlocal refresh_timer
            try:
                if root.winfo_exists():
                    self.refresh_if_changed()
                    refresh_timer = root.after(5000, refresh_shared_cases)
            except (tk.TclError,sqlite3.Error):
                pass
        refresh_timer = root.after(5000, refresh_shared_cases)

        def cancel_shared_refresh(event):
            if event.widget is root:
                root.after_cancel(refresh_timer)

        root.bind('<Destroy>', cancel_shared_refresh, add='+')
        login_activity.install(self)

    def show_shortcuts(self):
        if self.tabs.tab(self.tabs.select(),'text')=='Defendant Information':return shortcuts.show_help(self.root,'Defendant Information',shortcuts.DIRECTORY)
        return shortcuts.show_help(self.root,'Cases / Payments',shortcuts.MAIN)

    def legacy_mode(self):return main_legacy.enabled(self.store.db)

    def legacy_record(self):
        selection=self.tree.selection()
        if not selection or not selection[0].startswith('legacy:'):raise ValueError('Select an imported legacy case first.')
        return int(selection[0].split(':',1)[1])

    def legacy_context(self,required=True):
        record=self.legacy_record() if required else (self.legacy_record() if self.tree.selection() and self.tree.selection()[0].startswith('legacy:') else None)
        return main_legacy.Context(self,record)

    def edit_case(self):
        if self.legacy_mode():
            try:self.legacy_context().details()
            except ValueError as error:messagebox.showinfo('Select case',str(error),parent=self.root)
        else:self.functions_tools.edit_case()

    def case_page(self,direction):
        if direction>0 and not self.case_has_next:return
        self.case_offset=max(0,self.case_offset+150*direction);self.refresh()

    def selected(self):
        if self.legacy_mode():raise ValueError('The selected case is an imported legacy record. Use its main-screen legacy actions, not sample-data tools.')
        selection = self.tree.selection()
        if not selection:
            raise ValueError('Select a case first.')
        return int(selection[0])

    def refresh_if_changed(self):
        if performance.change_marker(self.store.db)!=getattr(self,'_last_shared_marker',None):
            self.refresh();return True
        return False

    def refresh(self):
        import document_mode
        self._last_shared_marker=performance.change_marker(self.store.db)
        mode=self.legacy_mode();query=self.query.get()
        output_mode = document_mode.for_store(self.store)
        evaluation = 'SERVER EVALUATION - '+('Imported legacy working records' if mode else 'Fictional sample data')+' - Shared on this server - Not for official transactions'
        self.mode_banner.configure(text={document_mode.OFFICIAL:'PRODUCTION - Official receipts and accounting reports',
                                        document_mode.REHEARSAL:'OFFICIAL OUTPUT REHEARSAL - VOID'}.get(output_mode,evaluation))
        if query!=self._case_query or mode!=self._case_mode:self.case_offset=0
        self._case_query=query;self._case_mode=mode
        selected=self.tree.selection();self.tree.delete(*self.tree.get_children())
        if mode:
            rows,self.case_has_next=main_legacy.list_cases(self.store.db,query,self.case_offset)
            for record,data in rows:
                try:due='$'+format(sum(main_legacy.balances(data)),',.2f')
                except ValueError:due='Review balances'
                self.tree.insert('','end',iid='legacy:'+str(record),values=(data.get('CASE_NO',''),data.get('DEFENDANT',''),data.get('MERCHANT',''),due,record))
            first=self.case_offset+1 if rows else 0
            self.case_status.set(f'Imported legacy cases - rows {first}-{self.case_offset+len(rows)}'+(' - more available' if self.case_has_next else ''))
        else:
            self.case_has_next=False
            for row in self.store.cases_with_balances(query):self.tree.insert('','end',iid=str(row['id']),values=(row['case_no'],row['defendant'],row['merchant'],dollars(row['balance_due']),'Sample'))
            self.case_status.set('Sample cases - no complete legacy working database has been loaded')
        self.case_previous.configure(state='normal' if mode and self.case_offset else 'disabled');self.case_next.configure(state='normal' if mode and self.case_has_next else 'disabled')
        self.case_buttons['New sample case'].configure(text='New legacy case' if mode else 'New sample case')
        self.case_buttons['Collection summary'].configure(text='Legacy receipt summary' if mode else 'Collection summary')
        legacy_payment = {document_mode.OFFICIAL:'Record payment', document_mode.REHEARSAL:'Record rehearsal payment'}.get(output_mode,'Record payment (test)')
        self.payment_button.configure(text=legacy_payment if mode else 'Record sample payment')
        if selected and self.tree.exists(selected[0]):self.tree.selection_set(selected[0]);self.select()
        else:self.detail.set('Select a case to review balances and payments.')

    def select(self):
        if not self.tree.selection():self.detail.set('Select a case to review balances and payments.');return
        if self.legacy_mode():
            try:
                record=self.legacy_record();row=legacy_work.get(self.store.db,'WC_CASE',record);data=json.loads(row['data_json'])
                self.detail.set('Source row '+str(record)+' | Remaining: '+' | '.join(k+': $'+format(v,',.2f') for k,v in zip(CATEGORIES,main_legacy.balances(data))))
            except ValueError as error:self.detail.set(str(error))
            return
        self.detail.set('Remaining:  '+'   |   '.join(f'{k}: {dollars(v)}' for k,v in zip(CATEGORIES,self.store.balance(self.selected()))))

    def form(self,title,labels,defaults):
        win = tk.Toplevel(self.root)
        win.title(title)
        win.transient(self.root)
        entries = []
        for i,(label,default) in enumerate(zip(labels,defaults)):
            ttk.Label(win,text=label).grid(row=i,column=0,sticky='w',padx=15,pady=6)
            entry = ttk.Entry(win,width=42)
            entry.insert(0,default)
            entry.grid(row=i,column=1,padx=15,pady=6)
            entries.append(entry)
        return win,entries

    def new_case(self):
        if self.legacy_mode():self.legacy_context(False).safe(lambda:self.legacy_context(False).details(new=True));return
        labels = ['Case number (blank = automatic)','Defendant (sample name)','Merchant (sample name)','Check number','Entered date',*CATEGORIES[:4]]
        win,entries = self.form('New sample case',labels,['','','','',date_format.display(dt.date.today()),'0.00',users.get_settings(self.store.db)['MERCHANT_FEE'],users.get_settings(self.store.db)['DA_FEE'],users.get_settings(self.store.db)['WITHDRAWAL_FEE']])
        bank_rows=banks.list_banks(self.store.db)
        ttk.Label(win,text='Bank (optional)').grid(row=len(labels),column=0,padx=15,pady=6,sticky='w')
        bank_choice=ttk.Combobox(win,state='readonly',width=48,values=['']+[r['code']+' - '+r['name'] for r in bank_rows])
        bank_choice.current(0)
        bank_choice.grid(row=len(labels),column=1,padx=15,pady=6)
        def save():
            try:
                values = [e.get() for e in entries]
                selected=bank_choice.current()
                self.store.create_case(*values[:5],[cents(v) for v in values[5:]],bank_id=bank_rows[selected-1]['id'] if selected>0 else None)
                win.destroy()
                self.refresh()
            except (ValueError,sqlite3.Error) as e:
                messagebox.showerror('Cannot save case',str(e),parent=win)
        def apply_withdrawal():
            entries[8].delete(0,'end');entries[8].insert(0,users.get_settings(self.store.db)['WITHDRAWAL_FEE'])
        ttk.Button(win,text='Apply configured withdrawal fee',command=apply_withdrawal).grid(row=len(labels)+1,column=0,padx=15,pady=15)
        ttk.Button(win,text='Save sample case',command=save).grid(row=len(labels)+1,column=1,pady=15)

    def payment(self):
        if self.legacy_mode():
            try:self.legacy_context().payment()
            except ValueError as error:messagebox.showinfo('Select case',str(error),parent=self.root)
            return
        try:
            cid = self.selected()
        except ValueError as e:
            messagebox.showinfo('Select case',str(e))
            return
        user_audit.opened(self.store.db,'PAYMENT_ENTRY',user_audit.case_ref(self.store.case(cid)['case_no'],cid))
        win,entries = self.form('Record sample payment', ['Payment date','Operator initials','Method: Cash / Money order / Other',*CATEGORIES],
            [date_format.display(dt.date.today()),login.initials(self.store.db),'Cash',*['0.00']*5])
        token = str(uuid.uuid4())
        balances = self.store.balance(cid)
        ttk.Label(win,text=f'Remaining before payment: {dollars(sum(balances))}').grid(row=10,column=0,columnspan=2,pady=8)
        preview = legacy_work.payment_balance_preview(win,entries[3:7],balances,cents,dollars)
        preview.grid(row=11,column=0,columnspan=3,pady=8)
        ttk.Label(win,text='Allocate each amount explicitly. No automatic fee priority is assumed.').grid(row=8,column=0,columnspan=2,padx=15,pady=8)
        def save():
            try:
                values = [e.get() for e in entries]
                amounts = [cents(v) for v in values[3:]]
                if not messagebox.askyesno('Confirm sample payment',f'Record {dollars(sum(amounts))} for {self.store.case(cid)["case_no"]}?',parent=win):
                    return
                pid = self.store.post(cid,*values[:3],amounts,token)
                win.destroy()
                self.refresh()
                receipt=self.store.receipt(pid)
                self.show_text('Sample receipt',receipt,receipts=[receipt])
            except (ValueError,sqlite3.Error) as e:
                messagebox.showerror('Cannot post payment',str(e),parent=win)
        ttk.Button(win,text='Post sample payment',command=save).grid(row=9,column=1,pady=15)

    def show_text(self,title,content,receipts=None):
        win = tk.Toplevel(self.root)
        win.title(title)
        text = tk.Text(win,width=100,height=30,wrap='word',font=('Consolas',11))
        text.insert('1.0',content)
        text.configure(state='disabled')
        text.pack(fill='both',expand=True,padx=12,pady=12)
        def export():
            path = filedialog.asksaveasfilename(parent=win,defaultextension='.txt',filetypes=[('Text','*.txt')])
            if path:
                try:
                    Path(path).write_text(content,encoding='utf-8')
                except OSError as e:
                    messagebox.showerror('Cannot export',str(e),parent=win)
        ttk.Button(win,text='Save text copy',command=export).pack(pady=8)
        if receipts:
            def print_receipt():
                from receipt_print import open_print_preview
                try:
                    open_print_preview(receipts,self.store.path.parent/'receipt-previews')
                except (OSError,ValueError) as error:
                    messagebox.showerror('Cannot open print preview',str(error),parent=win)
            ttk.Button(win,text='Print Receipt' if len(receipts)==1 else 'Print receipts (one per page)',command=print_receipt).pack(pady=(0,10))

    def history(self):
        if self.legacy_mode():
            try:self.legacy_context().history()
            except ValueError as error:messagebox.showinfo('Select case',str(error),parent=self.root)
            return
        try:
            cid = self.selected()
            rows = self.store.db.execute('SELECT id FROM payments WHERE case_id=? ORDER BY id',(cid,)).fetchall()
            receipts=[self.store.receipt(r['id']) for r in rows]
            user_audit.opened(self.store.db,'PAYMENT_HISTORY',user_audit.case_ref(self.store.case(cid)['case_no'],cid))
            self.show_text('Payment history','\n\n'.join(receipts) or 'No payments recorded.',receipts=receipts)
        except ValueError as e:
            messagebox.showinfo('Select case',str(e))

    def report(self):
        if self.legacy_mode():legacy_functions.Center(self.legacy_context(False),'receipts.create');return
        today = dt.date.today()
        win,entries = self.form('Collection summary',['Start date (inclusive)','End date (inclusive)'],[date_format.display(today.replace(day=1)),date_format.display(today)])
        def run():
            try:
                content = self.store.summary(*[e.get() for e in entries])
                user_audit.opened(self.store.db,'REPORT','Collection summary')
                self.show_text('Collection summary',content)
            except ValueError as e:
                messagebox.showerror('Invalid dates',str(e),parent=win)
        ttk.Button(win,text='View totals',command=run).grid(row=2,column=1,pady=15)

    def backup(self):
        folder=users.get_settings(self.store.db)['BACKUP_FOLDER']
        options={'initialdir':folder} if folder and Path(folder).is_dir() else {}
        path = filedialog.asksaveasfilename(defaultextension='.sqlite',filetypes=[('SQLite backup','*.sqlite')],**options)
        if path:
            try:
                if Path(path).resolve() == self.store.path.resolve():
                    raise ValueError('Choose a different file from the active database.')
                target = sqlite3.connect(path)
                try:
                    self.store.db.backup(target)
                finally:
                    target.close()
                messagebox.showinfo('Backup saved',path)
            except (ValueError,OSError,sqlite3.Error) as e:
                messagebox.showerror('Backup failed',str(e))


def main():
    from deployment import run
    return run(Store, App)


if __name__ == '__main__':
    raise SystemExit(main())
