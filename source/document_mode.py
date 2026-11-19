"""Output modes shared by payment receipts and the production reports."""

TEST = 'test'
REHEARSAL = 'official-rehearsal'
OFFICIAL = 'official'
REHEARSAL_MARK = 'REHEARSAL — VOID'


def for_store(store):
    return getattr(store, 'document_mode', TEST)


def report_mark(payload):
    return {
        OFFICIAL: 'OFFICIAL REPORT',
        REHEARSAL: REHEARSAL_MARK,
    }.get(payload.get('document_mode'), 'DRAFT / TEST COPY — NOT FOR OFFICIAL TRANSACTIONS')
