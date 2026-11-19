from pathlib import Path
import sys,tempfile,json
from types import SimpleNamespace
from unittest.mock import patch
import tkinter as tk
from tkinter import ttk
src=Path(__file__).resolve().parents[1]/'source';sys.path.insert(0,str(src))
from app import Store
import users,login,office,divisions,legacy_functions,original_print
results={}
with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
 root=tk.Tk();root.withdraw()
 for sub in ('Data','EnterpriseData'):
  path=Path(tmp)/sub/'wc.sqlite';path.parent.mkdir()
  store=Store(path);db=store.db
  uid=users.save_user(db,'admin','Sample Admin','AD','Administrator')
  login.set_password(db,uid,'Fictional Test Passphrase',bootstrap=True);login.authenticate(db,'admin','Fictional Test Passphrase')
  old={**users.DEFAULTS,'DA':'OLD NAME','COUNTY':'Pike' if sub=='Data' else 'Coffee','CIRCUIT':'Twelfth','STATE':'AL','DA_FEE':'155.00','RECEIPT_START':'12345'}
  db.execute('INSERT INTO office_settings VALUES(1,?)',(json.dumps(old),));db.commit()
  original_json=db.execute('SELECT data FROM office_settings').fetchone()[0]
  assert users.document_heading(db)=='Worthless Check'
  assert db.execute('SELECT data FROM office_settings').fetchone()[0]==original_json
  assert users.workspace_label(db) in ('Office 1','Office 2')
  app=SimpleNamespace(store=store,root=root);app.office_heading=office.show_heading(root,users.document_heading(db).splitlines())
  parent=ttk.Frame(root);form=users.OfficeForm(app,parent)
  for key,value in {'ORGANIZATION':'Sample & Co.','HEADING2':'Community Collections','HEADING3':'North Region','HEADING4':'Accounts Office','OFFICE_LABEL':'North Desk','STATE':''}.items():
   form.entries[key].delete(0,'end');form.entries[key].insert(0,value)
  with patch('users.messagebox.showinfo'),patch('users.messagebox.showerror') as err:form.save();assert not err.called
  assert users.document_heading(db)=='Sample & Co.\nCommunity Collections\nNorth Region\nAccounts Office'
  assert [x.cget('text') for x in app.office_heading.winfo_children()]==users.document_heading(db).splitlines()
  assert 'North Desk | Worthless Check | 1.0.0-rc65' in root.title()
  saved=users.get_settings(db);assert saved['COUNTY']==old['COUNTY'] and saved['CIRCUIT']=='Twelfth' and saved['DA_FEE']=='155.00' and saved['RECEIPT_START']=='12345'
  payload={'kind':'receipts','title':'Register','columns':[],'items':[],'totals':{}}
  html=legacy_functions.print_html(payload,Path(tmp)/sub/'reports',users.document_heading(db)).read_text()
  assert 'Sample &amp; Co.' in html and 'Office of the District Attorney' not in html and 'State of Alabama' not in html
  fallback=legacy_functions.print_html(payload,Path(tmp)/sub/'reports').read_text();assert 'Worthless Check' in fallback and 'Pike County' not in fallback
  store.seed();receipt=store.receipt(store.post(1,'2026-11-19','AD','Cash',[100,0,0,0,0],'generic-test'))
  assert receipt.startswith(users.document_heading(db))
  try:users.save_settings(db,{'ORGANIZATION':'A\nB'})
  except ValueError:pass
  else:raise AssertionError('multiline heading accepted')
  sid=users.save_user(db,'staff','Sample Staff','ST','Staff');login.set_password(db,sid,'Fictional Staff Passphrase','Staff');login.authenticate(db,'staff','Fictional Staff Passphrase')
  try:users.save_settings(db,{'ORGANIZATION':'Unauthorized'})
  except ValueError:pass
  else:raise AssertionError('Staff changed identity')
  try:original_print.render_page(db,'letter1',{})
  except ValueError as e:assert 'archived original forms' in str(e)
  else:raise AssertionError('Old agency form rendered without review')
  login.logout(db);db.close();parent.destroy();app.office_heading.destroy()
  results[sub]={'generic_default_ignores_legacy_branding':'passed','read_does_not_rewrite_settings':'passed','custom_heading_all_four_lines_and_live_banner':'passed','custom_workspace_title':'passed','legacy_settings_fees_and_sequence_preserved':'passed','custom_and_fallback_report_html':'passed','receipt_custom_heading':'passed','staff_settings_restriction':'passed','archived_agency_forms_guard':'passed'}
 root.destroy()

print(json.dumps(results,indent=2))
