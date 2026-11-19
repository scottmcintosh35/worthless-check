"""Read-only references from Troy payments to the verified December 2004 archive."""
import hashlib
import json
from datetime import datetime
from decimal import Decimal, InvalidOperation
from tkinter import ttk

import date_format
import login
import user_audit

FILENAME = 'troy-historical-case-links.json'
FILE_SHA256 = {
    '40d8a500884bb4078d43a0fc411b4a64f1590d100dd1bf119f19f5e80cc1d572',  # 2,341 links
    'b3e14e36adef8412e2c4a41a30b1c35527d702df0638e7884717ddfa89a52802',  # 2,352 links
    '1c316ec8bf0da96b31d4039c471b2c99597e69a1f9a3c9ab82d78bda15322fee',  # 2,355 links
}
IDENTITY = ('CASE_NO', 'RECEIPT_NO', 'DATE', 'DEFENDANT', 'MERCHANT')
AMOUNTS = ('REST_PAID', 'SFEE_PAID', 'FO_PAID', 'WD_PAID', 'CC_PAID',
           'COURT_REST', 'MISCL', 'OVERPAID')


def payment_fingerprint(payment):
    identity = [' '.join(str(payment[key]).upper().split()) for key in IDENTITY]
    raw_date = identity[2]
    if len(raw_date) == 8 and raw_date.isascii() and raw_date.isdigit():
        identity[2] = datetime.strptime(raw_date, '%Y%m%d').date().isoformat()
    else:
        identity[2] = date_format.parse(raw_date).isoformat()
    amounts = [Decimal(str(payment[key]).strip() or '0') for key in AMOUNTS]
    if any(not amount.is_finite() for amount in amounts):
        raise ValueError('Invalid payment allocation.')
    values = identity + [format(amount.normalize() if amount else Decimal(0), 'f')
                         for amount in amounts]
    return hashlib.sha256(json.dumps(values, ensure_ascii=False).encode('utf-8')).hexdigest()


def load(store):
    login.require(store.db)
    if getattr(store, 'division', None) != 'troy':
        return []
    payload = store.path.with_name(FILENAME).read_bytes()
    if hashlib.sha256(payload).hexdigest() not in FILE_SHA256:
        raise ValueError('The historical case link file differs from the verified Troy release files.')
    links = {link['payment_source_row']: link for link in json.loads(payload)}
    confirmed = []
    for row, data in store.db.execute(
        "SELECT record_no,data_json FROM working_legacy "
        "WHERE table_name='PAYMENTS' AND deleted=0 ORDER BY record_no"
    ):
        link = links.get(row)
        if link is None:
            continue
        try:
            matches = payment_fingerprint(json.loads(data)) == link['payment_fingerprint']
        except (KeyError, TypeError, ValueError, InvalidOperation):
            continue
        if matches:
            confirmed.append(link)
    return confirmed


class Panel:
    COLUMNS = ('Payment source row', 'Receipt number', 'Payment date', 'Historical case')

    def __init__(self, screen, page):
        self.screen = screen
        self.store = screen.workspace.app.store
        self.links = {}
        self.status = ttk.Label(page, wraplength=900)
        self.status.pack(anchor='w', pady=8)
        bar = ttk.Frame(page)
        bar.pack(fill='x', pady=4)
        ttk.Label(bar, text='Payment row, receipt, or historical case number').pack(side='left')
        self.query = ttk.Entry(bar, width=24)
        self.query.pack(side='left', padx=8)
        self.query.bind('<Return>', lambda event: self.search())
        ttk.Button(bar, text='Search', command=self.search).pack(side='left')
        ttk.Button(bar, text='Use selected payment', command=self.use_selected).pack(side='left', padx=8)
        self.tree = screen.tree(page, self.COLUMNS, height=9)
        for column in self.COLUMNS:
            self.tree.column(column, width=160)
        self.tree.bind('<<TreeviewSelect>>', self.show_link)
        self.details = ttk.Label(page, wraplength=900, justify='left')
        self.details.pack(anchor='w', pady=10)
        if screen.payment is not None:
            self.query.insert(0, str(screen.payment))
        screen.book.bind('<<NotebookTabChanged>>', self.opened, add='+')
        self.page = page

    def opened(self, event):
        if event.widget.select() == str(self.page):
            self.search()

    def use_selected(self):
        self.query.delete(0, 'end')
        if self.screen.payment is not None:
            self.query.insert(0, str(self.screen.payment))
        self.search()

    def search(self):
        self.tree.delete(*self.tree.get_children())
        self.details.configure(text='')
        self.links = {}
        try:
            links = load(self.store)
        except FileNotFoundError:
            self.status.configure(text='The verified historical case link file has not been installed in the Troy data folder.')
            return
        except (OSError, ValueError) as error:
            self.status.configure(text=str(error))
            return
        query = self.query.get().strip().upper()
        for link in links:
            row = str(link['payment_source_row'])
            matches = (row, link['receipt_number'].upper(), link['case_number'].upper())
            if query and query != matches[0] and not any(query in value for value in matches[1:]):
                continue
            self.links[row] = link
            self.tree.insert('', 'end', iid=row,
                             values=(row, link['receipt_number'], link['payment_date'], link['case_number']))
        self.status.configure(text=f'{len(self.links):,} results · {len(links):,} verified links in this Troy workspace')
        if len(self.links) == 1:
            self.tree.selection_set(next(iter(self.links)))

    def show_link(self, event):
        self.details.configure(text='')
        selection = self.tree.selection()
        if not selection:
            return
        link = self.links[selection[0]]
        user_audit.opened(self.store.db, 'HISTORICAL_CASE_LINK',
                          f"Payment row {selection[0]}, archived case {link['case_number']}")
        self.details.configure(text=(
            f"Historical case {link['case_number']} · December 2004 Troy backup (1222.ZIP)\n"
            f"Archive WC_CASE row {link['historical_case_row']} · "
            f"Archive PAYMENTS row {link['historical_payment_row']}\n"
            "Read-only reference. The archive confirmed the case, defendant, merchant, receipt, date, and payment amounts."
        ))
