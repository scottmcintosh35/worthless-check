"""Defendant browse columns matching the legacy screen."""
from tkinter import ttk
import re
import date_format

COLUMNS = [
    ('NAME','Defendant',220),('ADDRESS','Address',300),('DOB','DOB',105),
    ('SSN','SSN (last 4)',110),('ID','ID',85),('RACE','Race',65),('SEX','Sex',55),
    ('LICENSE','License',130),('HISTORY','History',85),('HEIGHT_FT','Height_Ft',85),
    ('HEIGHT_IN','Height_in',85),('HAIR','Hair',65),('EYES','Eyes',65),
    ('WEIGHT','Weight',75),('TELEPHONE','Telephone',135),('EMPLOYER','Employer',220),
    ('EMP_PHONE','Emp. Phone',135),
]


def masked_ssn(value):
    text = str(value if value is not None else '').strip()
    if re.fullmatch(r'(?:[0-9]{9}|[0-9]{3}[- ][0-9]{2}[- ][0-9]{4})', text):
        return '***-**-' + text[-4:]
    return '***-**-****' if text else ''


def values(profile, record_id=''):
    result=[]
    for key,_,_ in COLUMNS:
        value=profile.get(key,'')
        if key=='ID':
            value=value or record_id
        elif key=='SSN':
            value=masked_ssn(value)
        elif key=='HISTORY':
            value='Memo' if (isinstance(value,dict) and value.get('memo')) or (isinstance(value,str) and value.strip()) else ''
        elif key=='DOB':
            value=date_format.display(value)
        result.append(value)
    return result


def make_grid(parent):
    frame=ttk.Frame(parent)
    frame.pack(fill='both',expand=True,padx=10,pady=8)
    tree=ttk.Treeview(frame,columns=[c[0] for c in COLUMNS],show='headings')
    for key,label,width in COLUMNS:
        tree.heading(key,text=label)
        tree.column(key,width=width,minwidth=45,stretch=False)
    vertical=ttk.Scrollbar(frame,orient='vertical',command=tree.yview)
    horizontal=ttk.Scrollbar(frame,orient='horizontal',command=tree.xview)
    tree.configure(yscrollcommand=vertical.set,xscrollcommand=horizontal.set)
    tree.grid(row=0,column=0,sticky='nsew')
    vertical.grid(row=0,column=1,sticky='ns')
    horizontal.grid(row=1,column=0,sticky='ew')
    frame.rowconfigure(0,weight=1)
    frame.columnconfigure(0,weight=1)
    return tree
