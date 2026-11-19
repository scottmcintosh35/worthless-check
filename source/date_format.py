"""User-facing dates with compatibility for stored ISO and FoxPro dates."""
import datetime as dt
import re


def parse(value):
    value = str(value).strip()
    try:
        if re.fullmatch(r'[0-9]{2}-[0-9]{2}-[0-9]{4}', value):
            return dt.datetime.strptime(value, '%m-%d-%Y').date()
        return dt.date.fromisoformat(value)
    except ValueError:
        raise ValueError('Enter a valid date in MM-DD-YYYY format.') from None


def display(value):
    if isinstance(value, dt.date):
        return value.strftime('%m-%d-%Y')
    if not value:
        return ''
    try:
        return display(parse(value))
    except ValueError:
        return value


def timestamp(value):
    if not value:
        return ''
    try:
        parsed = dt.datetime.fromisoformat(value)
    except ValueError:
        return value
    return parsed.strftime('%m-%d-%Y %H:%M:%S') + (parsed.strftime(' %z') if parsed.tzinfo else '')
