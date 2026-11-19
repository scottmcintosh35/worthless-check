import date_format
"""Division-local activity for signed-in users."""
import datetime as dt
from html import escape
from pathlib import Path
import sqlite3
from tempfile import NamedTemporaryFile
import tkinter as tk
from tkinter import messagebox, ttk
import webbrowser
from zoneinfo import ZoneInfo

import divisions
import login


PAGE_SIZE = 150
with Path(__file__).with_name('america-chicago.tzif').open('rb') as zone_file:
    CENTRAL = ZoneInfo.from_file(zone_file, key='America/Chicago')


def utc_midnight(day):
    return dt.datetime.combine(day, dt.time.min, CENTRAL).astimezone(dt.timezone.utc).isoformat()


def opened(db, item, reference):
    user = login.current(db)
    if user is None:
        login.require(db)  # Allow the unsigned review prototype only.
        return
    pending = db.in_transaction
    db.execute('INSERT INTO audit(at,operator,action,reference) VALUES(?,?,?,?)',
               (dt.datetime.now(dt.timezone.utc).isoformat(), user['username'],
                'OPEN_' + item, str(reference)))
    if not pending:
        db.commit()


def case_ref(number, row):
    return f'Case {number} · row {row}'


def administrator(db):
    user = login.current(db)
    if user is None or user['role'] != 'Administrator':
        raise ValueError('Sign in as an Administrator in this division to view user activity.')


def date_range(start, end):
    dates = []
    for value in (start, end):
        value = value.strip()
        if value:
            try:
                parsed = date_format.parse(value)
                if value not in (parsed.isoformat(), date_format.display(parsed)):
                    raise ValueError
            except ValueError:
                raise ValueError('Enter dates in MM-DD-YYYY format.') from None
        dates.append(parsed.isoformat() if value else "")
    start, end = dates
    if start and end and start > end:
        raise ValueError('The From date must be on or before the To date.')
    return start, end


def activity(db, username='', kind='All activity', offset=0, *,
             start='', end='', limit=PAGE_SIZE + 1):
    administrator(db)
    start, end = date_range(start, end)
    actor = ' AND operator=? COLLATE NOCASE' if username else ''
    legacy_actor = ' WHERE actor=? COLLATE NOCASE' if username else ''
    access = "substr(action,1,5)='OPEN_'"
    predicate = access if kind == 'Opened' else 'NOT (' + access + ')' if kind == 'Other recorded activity' else '1'
    args = [username] if username else []
    sql = f"""SELECT at,operator,action,
        CASE WHEN substr(ltrim(reference),1,1) IN ('{{','[')
             THEN 'Details in original audit log'
             WHEN action='RECONCILE_LEGACY_PAYMENT' THEN 'Reconciliation #' || reference
             ELSE reference END AS record_ref, id, 0 AS source
        FROM audit WHERE {predicate}{actor}"""
    if kind != 'Opened':
        sql += f""" UNION ALL SELECT at,actor,'SAVE_LEGACY_CHANGE',
            table_name || ' · row ' || record_no,id,1 FROM legacy_changes{legacy_actor}"""
        args += [username] if username else []
    date_filters = []
    if start:
        date_filters.append('at >= ?')
        args.append(utc_midnight(dt.date.fromisoformat(start)))
    if end and end != dt.date.max.isoformat():
        date_filters.append('at < ?')
        args.append(utc_midnight(dt.date.fromisoformat(end) + dt.timedelta(days=1)))
    if date_filters:
        sql = 'SELECT * FROM (' + sql + ') WHERE ' + ' AND '.join(date_filters)
    return db.execute(sql + ' ORDER BY at DESC,source,id DESC LIMIT ? OFFSET ?',
                      (*args, limit, offset)).fetchall()


def display_values(row):
    timestamp = dt.datetime.fromisoformat(row['at'])
    if timestamp.tzinfo is None:
        timestamp = timestamp.replace(tzinfo=dt.timezone.utc)
    local = timestamp.astimezone(CENTRAL)
    return (local.strftime('%m-%d-%Y %H:%M:%S %Z'), row['operator'],
            row['action'].replace('_', ' ').capitalize(), row['record_ref'])


def print_results(rows, division, username, kind, start, end):
    if not rows:
        raise ValueError('No matching activity to print.')
    with NamedTemporaryFile(mode='w', encoding='utf-8', prefix='wc-user-audit-',
                            suffix='.html', delete=False) as report:
        report.write('''<!doctype html><html lang="en"><meta charset="utf-8">
<title>User Activity Audit</title>
<style>
@page { size: letter portrait; margin: .65in; }
body { font: 11pt Arial, sans-serif; color: #111; }
table { width: 100%; border-collapse: collapse; }
thead { display: table-header-group; }
tr { break-inside: avoid; }
th, td { border: 1px solid #aaa; padding: 5px; text-align: left; overflow-wrap: anywhere; }
th { background: #eee; }
td:first-child { white-space: nowrap; }
@media print { button { display: none; } }
</style>
<button onclick="window.print()">Print results</button>
<h1>User Activity Audit</h1>''')
        report.write(f'<p>{escape(division)} · {escape(username or "All users")} · {escape(kind)}</p>')
        report.write(f'<p>From {escape(date_format.display(start) or "earliest")} to {escape(date_format.display(end) or "latest")} (Central time, inclusive) · {len(rows):,} events</p>')
        report.write('<table><thead><tr><th>Date and time (Central)</th><th>Staff account</th>'
                     '<th>Activity</th><th>Record or screen</th></tr></thead><tbody>')
        for row in rows:
            cells = ''.join(f'<td>{escape(str(value))}</td>' for value in display_values(row))
            report.write(f'<tr>{cells}</tr>')
        report.write('</tbody></table><script>window.addEventListener("load", () => window.print());</script></html>')
    if not webbrowser.open(Path(report.name).resolve().as_uri()):
        Path(report.name).unlink(missing_ok=True)
        raise OSError('The print preview could not open in the default browser.')


def show(app):
    db = app.store.db
    try:
        administrator(db)
        opened(db, 'USER_ACTIVITY_AUDIT', 'Activity viewer')
    except (ValueError, OSError, sqlite3.Error) as error:
        messagebox.showerror('User Activity Audit', str(error), parent=app.root)
        return
    win = tk.Toplevel(app.root)
    division = divisions.LABELS[divisions.database_division(db)]
    win.title('User Activity Audit | ' + division)
    win.geometry(f'{min(1050,win.winfo_screenwidth()-50)}x{min(630,win.winfo_screenheight()-100)}')
    bar = ttk.Frame(win, padding=10)
    bar.pack(fill='x')
    ttk.Label(bar, text='Staff account').pack(side='left')
    names = db.execute('''SELECT username AS name FROM staff_users
        UNION SELECT operator FROM audit UNION SELECT actor FROM legacy_changes
        ORDER BY name COLLATE NOCASE''').fetchall()
    user = ttk.Combobox(bar, values=['All users', *[r[0] for r in names]], state='readonly')
    user.current(0)
    user.pack(side='left', padx=(6, 16))
    ttk.Label(bar, text='Activity').pack(side='left')
    kind = ttk.Combobox(bar, values=['All activity', 'Opened', 'Other recorded activity'],
                        state='readonly', width=24)
    kind.current(0)
    kind.pack(side='left', padx=6)
    dates = ttk.Frame(win, padding=(10, 0, 10, 10))
    dates.pack(fill='x')
    ttk.Label(dates, text='From (MM-DD-YYYY)').pack(side='left')
    start = ttk.Entry(dates, width=12)
    start.pack(side='left', padx=(6, 14))
    ttk.Label(dates, text='To (MM-DD-YYYY)').pack(side='left')
    end = ttk.Entry(dates, width=12)
    end.pack(side='left', padx=6)
    ttk.Label(dates, text='Central time · Both dates included').pack(side='left', padx=6)
    table = ttk.Frame(win, padding=(10, 0, 10, 0))
    table.pack(fill='both', expand=True)
    tree = ttk.Treeview(table, columns=('at', 'user', 'action', 'ref'), show='headings')
    for col, label, width in [('at','Date and time (Central)',205), ('user','Staff account',130),
                              ('action','Activity',245), ('ref','Record or screen',340)]:
        tree.heading(col, text=label)
        tree.column(col, width=width, minwidth=80)
    scroll = ttk.Scrollbar(table, orient='vertical', command=tree.yview)
    tree.configure(yscrollcommand=scroll.set)
    scroll.pack(side='right', fill='y')
    tree.pack(fill='both', expand=True)
    footer = ttk.Frame(win, padding=10)
    footer.pack(fill='x')
    status = ttk.Label(footer)
    offset = 0
    applied = ('', kind.get(), '', '')

    def fetch(filters, position=0, limit=PAGE_SIZE + 1):
        username, category, first, last = filters
        return activity(db, username, category, position, start=first, end=last, limit=limit)

    def load(position=0):
        nonlocal offset
        try:
            rows = fetch(applied, position)
        except (ValueError, sqlite3.Error) as error:
            tree.delete(*tree.get_children())
            status.configure(text='Could not load activity')
            messagebox.showerror('User Activity Audit', str(error), parent=win)
            return False
        offset = position
        tree.delete(*tree.get_children())
        for row in rows[:PAGE_SIZE]:
            tree.insert('', 'end', values=display_values(row))
        status.configure(text=f'Events {offset+1}–{offset+min(PAGE_SIZE,len(rows))}' if rows else 'No matching activity')
        previous.configure(state='normal' if offset else 'disabled')
        following.configure(state='normal' if len(rows) > PAGE_SIZE else 'disabled')
        return True

    def apply():
        nonlocal applied
        try:
            first, last = date_range(start.get(), end.get())
        except ValueError as error:
            messagebox.showerror('User Activity Audit', str(error), parent=win)
            return False
        applied = ('' if user.current() == 0 else user.get(), kind.get(), first, last)
        return load()

    def print_activity():
        if not apply():
            return
        try:
            rows = fetch(applied, limit=-1)
            print_results(rows, division, *applied)
        except (ValueError, OSError, sqlite3.Error) as error:
            messagebox.showerror('Print audit results', str(error), parent=win)

    previous = ttk.Button(footer, text='Previous', command=lambda: load(max(0, offset-PAGE_SIZE)))
    following = ttk.Button(footer, text='Next', command=lambda: load(offset+PAGE_SIZE))
    previous.pack(side='left')
    following.pack(side='left', padx=6)
    status.pack(side='left', padx=8)
    ttk.Button(dates, text='Apply filters', command=apply).pack(side='left', padx=6)
    ttk.Button(footer, text='Print results', command=print_activity).pack(side='right')
    for choice in (user, kind):
        choice.bind('<<ComboboxSelected>>', lambda event: apply())
    for field in (start, end):
        field.bind('<Return>', lambda event: apply())
    load()
