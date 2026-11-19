import date_format
"""New-case defaults; never recalculate historical charges or dates."""
import datetime as dt
from decimal import Decimal,InvalidOperation
import re

MERCHANT_FEE='30.00'
WITHDRAWAL_FEE='30.00'
DUE_BUSINESS_DAYS=15

def holiday_dates(text):
    result=set()
    for value in re.split(r'[,;\s]+',str(text or '').strip()):
        if value:
            try:result.add(date_format.parse(value))
            except ValueError:raise ValueError('Enter holiday dates as MM-DD-YYYY, separated by commas.') from None
    return result

def entered_date(value):
    value=str(value).strip()
    try:return date_format.parse(value)
    except ValueError:raise ValueError('Enter the case entry date as MM-DD-YYYY.') from None

def add_business_days(value,days=15,holidays=()):
    date=entered_date(value) if not isinstance(value,dt.date) else value
    if type(days)is not int or not 1<=days<=365:raise ValueError('Due days must be an integer from 1 to 365.')
    exclusions=set(holidays);count=0
    while count<days:
        date+=dt.timedelta(days=1)
        if date.weekday()<5 and date not in exclusions:count+=1
    return date

def due_date(db,value):
    import users
    settings=users.get_settings(db)
    return add_business_days(value,int(settings['DUE_BUSINESS_DAYS']),holiday_dates(settings['BUSINESS_HOLIDAYS']))

def legacy_defaults(db,value=None,apply_withdrawal=True):
    import users
    settings=users.get_settings(db);date=entered_date(value) if value else dt.date.today()
    return {'ENTER_DATE':date.strftime('%Y%m%d'),'DUE_DATE':due_date(db,date.isoformat()).strftime('%Y%m%d'),
            'FIRST_OFF':settings['DA_FEE'],'DA_DUE':settings['DA_FEE'],
            'MERCH_FEE':settings['MERCHANT_FEE'],'FEE_DUE':settings['MERCHANT_FEE'],
            'WITHDRAWAL':settings['WITHDRAWAL_FEE'] if apply_withdrawal else '0.00','WD_DUE':settings['WITHDRAWAL_FEE'] if apply_withdrawal else '0.00'}

def apply_missing(db,values):
    result=dict(values)
    defaults=legacy_defaults(db,result.get('ENTER_DATE') or None)
    for key,value in defaults.items():
        if not str(result.get(key,'')).strip():result[key]=value
    return result
