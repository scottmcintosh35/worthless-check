"""Rehearsal previews for verifying division settings and cutoff reports."""
import webbrowser
from decimal import Decimal
from tkinter import messagebox

import divisions
import document_mode
import legacy_functions
import legacy_work
import login
import main_legacy
import users


BALANCE_COLUMNS = ('Restitution', 'Merchant fee', 'DA / warrant fee', 'Withdrawal fee', 'Total balance')


def outstanding_balances(db):
    login.require(db)
    totals = dict.fromkeys(BALANCE_COLUMNS, Decimal('0.00'))
    items = []
    zero = credits = invalid = 0
    net = Decimal('0.00')
    for record in legacy_functions.records(db, 'WC_CASE'):
        data = record['data']
        row = {'Case number': str(data.get('CASE_NO', '')).strip()}
        try:
            amounts = main_legacy.balances(data)
        except ValueError:
            invalid += 1
            row['Total balance'] = 'Review source fields'
        else:
            balance = sum(amounts)
            net += balance
            if balance == 0:
                zero += 1
                continue
            if balance < 0:
                credits += 1
                continue
            for label, amount in zip(BALANCE_COLUMNS, [*amounts, balance]):
                totals[label] += amount
                row[label] = f'{amount:.2f}'
        items.append({'row': record['row'], 'data': row})
    return {
        'kind': 'outstanding_balances', 'title': 'Outstanding Case Balances',
        'columns': ['Case number', *BALANCE_COLUMNS], 'items': items,
        'totals': {label: f'{amount:.2f}' for label, amount in totals.items()},
        'wrapper': (f'Positive-balance cases: {len(items) - invalid:,}. Zero balances: {zero:,}. '
                    f'Negative balances: {credits:,}. Cases requiring review: {invalid:,}.\n'
                    f'Net balance across non-deleted cases with valid amounts: ${net:,.2f}.\n'
                    'Totals below cover positive-balance cases.'),
    }


def settings_text(db):
    login.require(db, True)
    settings = users.get_settings(db)
    return '\n'.join([
        f"Division: {divisions.LABELS[divisions.database_division(db)]}",
        users.document_heading(db), users.document_contact(db), '',
        'New-case defaults',
        f"DA / warrant fee: ${settings['DA_FEE']}",
        f"Merchant fee: ${settings['MERCHANT_FEE']}",
        f"Withdrawal fee: ${settings['WITHDRAWAL_FEE']}",
        f"Business days to due date: {settings['DUE_BUSINESS_DAYS']}",
        f"Holiday exclusions: {settings['BUSINESS_HOLIDAYS'] or 'None entered'}", '',
        f"Configured starting numeric receipt: {settings['RECEIPT_START'] or 'Continue existing sequence'}",
        f'Next numeric receipt on this copy: {legacy_work.next_payment_receipt(db)}',
    ])


def show(app, *, balances=False):
    store = app.store
    try:
        if not app.legacy_mode():
            raise ValueError('Load the imported legacy workspace before reviewing release settings or balances.')
        if balances:
            payload = outstanding_balances(store.db)
            payload['document_mode'] = document_mode.for_store(store)
            path = legacy_functions.print_html(payload, store.path.parent/'legacy-print-previews',
                                               users.document_heading(store.db))
            if not webbrowser.open(path.resolve().as_uri()):
                raise OSError(f'Open this report in your browser: {path}')
        else:
            app.show_text('Production setup review', settings_text(store.db))
    except (ValueError, OSError) as error:
        messagebox.showerror('Production review', str(error), parent=app.root)
