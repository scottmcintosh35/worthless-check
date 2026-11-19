"""Positioned original FRX layouts. Safe expression interpretation, never FoxPro execution."""
import calendar
import datetime as dt
from decimal import Decimal,InvalidOperation
import hashlib
import html
import json
from pathlib import Path
import re
import tkinter as tk
from tkinter import ttk,messagebox
import login

DEFAULT_REPORTS={'letter1':'DEF_LTR1.FRX','letter2':'SEC_LTR.FRX','letter3':'DEF_LTR3.FRX','postal':'POSTMAN.FRX',
 'restitution_agreement':'REST_WC.FRX','restitution_form':'AGR_REST.FRX','forgery':'FORGERY.FRX','complaint':'COMPLT.FRX',
 'check_merchant':'MCHECK.FRX','check_fund':'EDA_CHK.FRX','check_refund':'DCHECK.FRX'}
_LIBRARY=None

def library():
 global _LIBRARY
 if _LIBRARY is None:_LIBRARY=json.loads((Path(__file__).parent/'original-report-layouts.json').read_text(encoding='utf-8'))
 return _LIBRARY

def setup(db):
 db.execute('CREATE TABLE IF NOT EXISTS legacy_original_print_settings(kind TEXT PRIMARY KEY,data TEXT NOT NULL,revision INTEGER NOT NULL DEFAULT 0)')

def config(db,kind):
 row=db.execute('SELECT data FROM legacy_original_print_settings WHERE kind=?',(kind,)).fetchone()
 return {'mode':'original','report':DEFAULT_REPORTS[kind],'x':0,'y':0,'scale':100,'watermark':kind.startswith('check_'),'office_source':'original','field_overrides':{},'image_aliases':{},**(json.loads(row[0]) if row else {})}

def save_config(db,kind,values,revision,reason):
 actor=login.require(db,True)
 if kind not in DEFAULT_REPORTS:raise ValueError('Unknown original print section.')
 if not reason.strip():raise ValueError('A print-setting change reason is required.')
 data=dict(values)
 if data['report'] not in library()['reports']:raise ValueError('Select an included original FRX report.')
 for key,minimum,maximum in [('x',-2,2),('y',-2,2),('scale',50,150)]:
  try:value=Decimal(str(data[key]))
  except InvalidOperation:raise ValueError('Invalid alignment setting.')
  if not value.is_finite() or not minimum<=value<=maximum:raise ValueError('Alignment setting is outside its allowed range.')
  data[key]=float(value)
 if data['mode'] not in ('original','edited'):raise ValueError('Choose original layout or edited text.')
 if data['office_source'] not in ('original','current'):raise ValueError('Choose the original USER record or current Office Information.')
 if not isinstance(data['field_overrides'],dict) or not isinstance(data['image_aliases'],dict):raise ValueError('Overrides must be JSON objects.')
 for key,value in data['field_overrides'].items():
  if not str(key).isdigit() or not isinstance(value,str):raise ValueError('Field overrides map original record numbers to expression strings.')
 for key,value in data['image_aliases'].items():
  if str(value).lower() not in library()['assets']:raise ValueError('Image aliases must select an included original bitmap filename.')
 data['watermark']=bool(data['watermark'])
 try:
  db.execute('BEGIN IMMEDIATE');old=db.execute('SELECT * FROM legacy_original_print_settings WHERE kind=?',(kind,)).fetchone()
  if (old['revision'] if old else -1)!=revision:raise ValueError('Print settings changed in another session. Reopen the editor.')
  db.execute('INSERT INTO legacy_original_print_settings(kind,data) VALUES(?,?) ON CONFLICT(kind) DO UPDATE SET data=excluded.data,revision=legacy_original_print_settings.revision+1',(kind,json.dumps(data)))
  db.execute('INSERT INTO audit(at,operator,action,reference) VALUES(?,?,?,?)',(dt.datetime.now(dt.timezone.utc).isoformat(),actor,'ORIGINAL_PRINT_SETTINGS',json.dumps({'kind':kind,'before':dict(old) if old else None,'after':data,'reason':reason})))
  db.commit()
 except Exception:db.rollback();raise


def update_notice(text):
 def replace(match):
  old=match.group(0);value='15 business days'
  return value.upper() if old.isupper() else value
 # Only notice-day phrases change; currency, dates, formulas and other numbers do not.
 return re.sub(r'\b(?:ten\s*\(\s*10\s*\)|ten|10)\s+(?:(?:business|working)\s+)?days\b',replace,text,flags=re.I)


def reverse_name(value):
 value=str(value).strip()
 if ',' not in value:return value
 last,first=value.split(',',1);return (first.strip()+' '+last.strip()).strip()

def amount_words(value):
 value=Decimal(str(value)).quantize(Decimal('.01'))
 if not value.is_finite() or not 0<=value<Decimal('1000000000'):raise ValueError('Amount in words is outside the supported range.')
 ones=('ZERO ONE TWO THREE FOUR FIVE SIX SEVEN EIGHT NINE TEN ELEVEN TWELVE THIRTEEN FOURTEEN FIFTEEN SIXTEEN SEVENTEEN EIGHTEEN NINETEEN').split();tens='ZERO TEN TWENTY THIRTY FORTY FIFTY SIXTY SEVENTY EIGHTY NINETY'.split()
 def say(n):
  if n<20:return ones[n]
  if n<100:return tens[n//10]+(' '+ones[n%10] if n%10 else '')
  if n<1000:return ones[n//100]+' HUNDRED'+(' '+say(n%100) if n%100 else '')
  for size,name in ((1000000,'MILLION'),(1000,'THOUSAND')):
   if n>=size:return say(n//size)+' '+name+(' '+say(n%size) if n%size else '')
 return say(int(value))+' AND '+str(int((value-int(value))*100)).zfill(2)+'/100 DOLLARS'


TOKEN=re.compile(r"\s*(?:(?P<string>'(?:[^']|'')*'|\"(?:[^\"]|\"\")*\")|(?P<number>\d+(?:\.\d*)?|\.\d+)|(?P<name>[A-Za-z_]\w*(?:\.[A-Za-z_]\w*)?)|(?P<op><>|<=|>=|[+*/(),=<>-]))",re.S)
class Expression:
 def __init__(self,text,context):
  self.context=context;self.tokens=[];self.index=0;pos=0
  text=text.strip()
  if len(text)>30000:raise ValueError('Expression exceeds the supported size.')
  while pos<len(text):
   m=TOKEN.match(text,pos)
   if not m:raise ValueError('Unsupported expression syntax: '+text[pos:pos+40])
   self.tokens.append((m.lastgroup,m.group(m.lastgroup)));pos=m.end()
  if len(self.tokens)>1500:raise ValueError('Expression has too many tokens.')
 def peek(self,value=None):
  if self.index>=len(self.tokens):return False
  return self.tokens[self.index][1].upper()==value if value is not None else self.tokens[self.index]
 def take(self,value=None):
  if value is not None and not self.peek(value):raise ValueError('Expected '+value)
  token=self.tokens[self.index];self.index+=1;return token
 def run(self):
  value=self.compare()
  if self.index!=len(self.tokens):raise ValueError('Unsupported expression suffix.')
  return value
 def compare(self):
  value=self.sum()
  while self.peek() and self.peek()[1] in ('=','<>','<','>','<=','>='):
   op=self.take()[1];right=self.sum();value={'=':lambda:value==right,'<>':lambda:value!=right,'<':lambda:value<right,'>':lambda:value>right,'<=':lambda:value<=right,'>=':lambda:value>=right}[op]()
  return value
 def sum(self):
  value=self.product()
  while self.peek('+') or self.peek('-'):
   op=self.take()[1];right=self.product()
   if isinstance(value,dt.date) and isinstance(right,(Decimal,int)):value=value+dt.timedelta(days=int(right)*(1 if op=='+' else -1))
   elif isinstance(value,str) and isinstance(right,str):value=value+right if op=='+' else value.rstrip()+right
   else:value=value+right if op=='+' else value-right
  return value
 def product(self):
  value=self.atom()
  while self.peek('*') or self.peek('/'):
   op=self.take()[1];right=self.atom();value=value*right if op=='*' else value/right
  return value
 def atom(self):
  if self.peek('+'):self.take();return self.atom()
  if self.peek('-'):self.take();return -self.atom()
  if self.peek('('):
   self.take();value=self.compare();self.take(')');return value
  if not self.peek():raise ValueError('Expression ended unexpectedly.')
  kind,value=self.take()
  if kind=='string':return value[1:-1].replace(value[0]*2,value[0])
  if kind=='number':return Decimal(value)
  if kind!='name':raise ValueError('Unsupported expression token.')
  name=value.upper()
  if self.peek('('):
   self.take();args=[]
   if not self.peek(')'):
    args.append(self.compare())
    while self.peek(','):self.take();args.append(self.compare())
   self.take(')');return self.call(name,args)
  if name not in self.context:raise ValueError('Unresolved field '+name)
  return self.context[name]
 def call(self,name,args):
  if name=='DATE' and not args:return self.context['_PRINT_DATE']
  if name in ('ALLTRIM','LTRIM','RTRIM','UPPER','LOWER','REVNAME'):
   if len(args)!=1:raise ValueError('Invalid '+name+' arguments.')
   value=str(args[0]);return {'ALLTRIM':str.strip,'LTRIM':str.lstrip,'RTRIM':str.rstrip,'UPPER':str.upper,'LOWER':str.lower,'REVNAME':reverse_name}[name](value)
  if name in ('DAY','MONTH','YEAR','CMONTH','DTOC'):
   value=args[0]
   if value is None:return ''
   if not isinstance(value,dt.date):raise ValueError(name+' needs a valid date.')
   return {'DAY':lambda:Decimal(value.day),'MONTH':lambda:Decimal(value.month),'YEAR':lambda:Decimal(value.year),'CMONTH':lambda:calendar.month_name[value.month],'DTOC':lambda:value.strftime('%m-%d-%Y')}[name]()
  if name=='STR':
   value=Decimal(args[0]);width=int(args[1]) if len(args)>1 else 10;places=int(args[2]) if len(args)>2 else 0
   if not 0<=places<=8 or not 1<=width<=200:raise ValueError('Unsupported STR width/precision.')
   result=format(value,f'.{places}f');return result.rjust(width) if len(result)<=width else '*'*width
  if name=='CHR' and len(args)==1 and 0<=int(args[0])<256:return chr(int(args[0]))
  if name=='EMPTY' and len(args)==1:return args[0] in ('',None,0,False)
  if name=='IIF' and len(args)==3:return args[1] if args[0] else args[2]
  if name=='TRANSFORM' and len(args)==2:
   value,mask=args
   if str(mask).upper().startswith('@R'):
    digits=iter(re.sub(r'\D','',str(value)));return ''.join(next(digits,' ') if ch=='9' else ch for ch in str(mask)[2:].lstrip())
   return display(value,mask)
  if name=='CK_WORDS' and len(args)==1:
   if not self.context.get('_AMOUNT_WORDS'):raise ValueError('Enter and verify the check amount in words in Print fields.')
   return self.context['_AMOUNT_WORDS']
  if name=='CK_DEFS' and not args:
   if not self.context.get('GCDEFS'):raise ValueError('Enter the original check detail/definition text in Print fields.')
   return self.context['GCDEFS']
  raise ValueError('Unsupported function '+name)

def evaluate(text,context):return Expression(text,context).run()

def display(value,picture=''):
 if value is None:return ''
 if isinstance(value,dt.date):return value.strftime('%m-%d-%Y')
 if isinstance(value,(Decimal,int)) and not isinstance(value,bool):
  mask=str(picture).strip('"\'');places=len(mask.rsplit('.',1)[1]) if '.' in mask and any(x in mask for x in '9#') else 2
  result=format(value,(',' if ',' in mask else '')+'.'+str(min(places,8))+'f')
  return ('$' if '$' in mask else '')+result
 return str(value)


def context_for(db,data,settings,check=None):
 import legacy_work as lw
 import users
 context={};schema_cache={}
 def add(alias,values,table,bare=False):
  if table not in schema_cache:
   try:schema_cache[table]={f['name']:f for f in lw.schema(db,table)}
   except ValueError:schema_cache[table]={}
  for key in set(values)|set(schema_cache[table]):
   value=values.get(key,'');field=schema_cache[table].get(key,{})
   if field.get('type') in ('N','F'):
    try:value=Decimal(str(value).strip() or '0')
    except InvalidOperation:pass
   elif field.get('type')=='D':
    try:value=dt.datetime.strptime(str(value),'%Y%m%d').date() if str(value).strip() else None
    except ValueError:value=None
   if alias:context[alias+'.'+key.upper()]=value
   if bare:context[key.upper()]=value
 add('WC_CASE',data,'WC_CASE',True)
 add('WC_WRITER',data,'WC_DEF')
 for key in ('ADDRESS','ADDRESS2','CITY','STATE','ZIP','TELEPHONE','DOB','NAME'):context[key]=context.get('WC_WRITER.'+key,data.get(key,''))
 merchant_id=str(data.get('MERCH_ID','')).strip()
 merchant_rows=db.execute("SELECT data_json FROM working_legacy WHERE table_name='WC_MERCH' AND deleted=0 AND trim(json_extract(data_json,'$.ME_ID'))=?",(merchant_id,)).fetchall() if merchant_id else []
 if len(merchant_rows)==1:add('MERCHANT',json.loads(merchant_rows[0][0]),'WC_MERCH',True)
 office={}
 if settings['office_source']=='original':
  rows=db.execute("SELECT data_json FROM working_legacy WHERE table_name='USER' AND deleted=0").fetchall()
  if len(rows)==1:office=json.loads(rows[0][0])
 else:office=users.get_settings(db)
 for key in users.DEFAULTS:office.setdefault(key,'')
 add('USER',office,'USER')
 context['_PRINT_DATE']=dt.date.today()
 if check:
  # The entered draft-check date/amount are the reviewed source for printing.
  context.update(GNAMT=Decimal(check['amount']),OVERPAID=Decimal(check['amount']),DA_CK_NO=check['check_no'],MERCHANT=check['payee'],DEFENDANT=check['payee'],GCDEFS=check.get('definition_text',''))
  context['_PRINT_DATE']=dt.date.fromisoformat(check['check_date']);context['_AMOUNT_WORDS']=check.get('amount_words','')
  for key in ('address','city','state','zip'):
   value=check.get('print_'+key,'');context[key.upper()]=value;context['ME_'+('ADDR' if key=='address' else key.upper())]=value
 return context


def render_page(db,kind,data,check=None):
 settings=config(db,kind);source=library()['reports'][settings['report']];context=context_for(db,data,settings,check);objects=[];errors=[];warnings=[]
 for item in source['objects']:
  typ=item['OBJTYPE'];number=str(item['record'])
  if typ=='9':continue
  output=dict(item)
  if typ in ('5','8'):
   expr=settings['field_overrides'].get(number,item.get('EXPR',''))
   repaired_total=(number=={'DEF_LTR1.FRX':'20','SEC_LTR.FRX':'9','DEF_LTR3.FRX':'65'}.get(settings['report']) and number not in settings['field_overrides'])
   if repaired_total:
    output['source_expression']=expr
    expr='LETTER_TOTAL_DUE'
    output['repair']='Remaining restitution + merchant fee + DA/warrant fee + withdrawal fee'
   expr=update_notice(expr)
   output['resolved_expression']=expr
   if re.search(r'\bck_amt\s*\+\s*20\b',expr,re.I):errors.append('Record '+number+' contains an obsolete hard-coded +20 total; select the verified report variant or field override.')
   try:
    if item.get('SUPEXPR') and not evaluate(item['SUPEXPR'],context):continue
    if repaired_total:
     import legacy_work as lw
     keys=('CK_DUE','FEE_DUE','DA_DUE','WD_DUE')
     if any(key not in data for key in keys):raise ValueError('Case is missing a balance component; reopen the complete case before printing.')
     context['LETTER_TOTAL_DUE']=sum((lw.money(data[key]) for key in keys),Decimal('0'))
    value=evaluate(expr,context) if expr else ''
    output['text']=display(value,item.get('PICTURE','')).replace('\r\n','\n').replace('\r','\n')
   except Exception as error:
    errors.append('Record '+number+': '+str(error));output['text']='[UNRESOLVED: '+expr+']'
  elif typ=='17':
   name=item.get('PICTURE','').strip('"\'').replace('\\','/').split('/')[-1].lower();original_name=name;name=settings['image_aliases'].get(name,{'tomsig~1.bmp':'tomsign.bmp'}.get(name,name)).lower()
   output['source_image']=original_name;output['resolved_image']=name
   asset=library()['assets'].get(name)
   if not asset:errors.append('Missing image '+name+' at record '+number+'; select the correct original bitmap alias.');output['missing_image']=name
   else:output['image']=asset['data_url'];output['asset_sha256']=asset['sha256']
  elif typ not in ('6','7'):continue
  try:
   for key in ('HPOS','VPOS','WIDTH','HEIGHT'):output[key]=float(item.get(key) or 0)
  except ValueError:errors.append('Invalid geometry at original record '+number);continue
  if output['HPOS']+output['WIDTH']>85010 or output['VPOS']+output['HEIGHT']>110010:warnings.append('Original object '+number+' extends outside Letter page bounds; verify the original printer origin/alignment.')
  objects.append(output)
 if check:
  if not check.get('print_address','').strip():errors.append('Check recipient print address is blank. Enter Print fields before printing.')
 return {'kind':kind,'report':settings['report'],'frx_sha256':source['frx_sha256'],'frt_sha256':source['frt_sha256'],'settings':settings,'objects':objects,'errors':errors,'warnings':warnings,'print_date':context['_PRINT_DATE'].isoformat()}


def page_text(page):
 return '\n'.join(o['text'] for o in sorted(page['objects'],key=lambda o:(o['VPOS'],o['HPOS'])) if 'text' in o)

def html_document(pages):
 def esc(value):return html.escape(str(value),quote=True)
 result=[];all_errors=[e for p in pages for e in p['errors']];all_warnings=[w for p in pages for w in p['warnings']]
 for page in pages:
  content=[];settings=page['settings']
  for o in page['objects']:
   x=o['HPOS']/10000;y=o['VPOS']/10000;w=o['WIDTH']/10000;h=o['HEIGHT']/10000;typ=o['OBJTYPE']
   location=f'position:absolute;left:{x:.7f}in;top:{y:.7f}in;width:{max(w,0):.7f}in;height:{max(h,0):.7f}in;'
   if 'text' in o:
    font=o.get('FONTFACE') or 'Courier New';size=float(o.get('FONTSIZE') or 10);style=int(o.get('FONTSTYLE') or 0);align={'0':'left','1':'right','2':'center'}.get(o.get('OFFSET'),'left') if typ=='8' else 'left'
    lines=max(1,o['text'].count('\n')+1);line_height=h/lines if h else size/72*1.2
    css=location+f'font-family:"{font}",monospace;font-size:{size:g}pt;line-height:{line_height:.7f}in;text-align:{align};white-space:pre-wrap;overflow:hidden;'
    if style&1:css+='font-weight:bold;'
    if style&2:css+='font-style:italic;'
    if style&4:css+='text-decoration:underline;'
    if style&8:css+='text-decoration:line-through;'
    content.append('<div data-frx-record="'+str(o['record'])+'" style="'+esc(css)+'">'+esc(o['text'])+'</div>')
   elif typ=='17':
    if 'image' in o:content.append('<img alt="Original report image" style="'+esc(location)+'object-fit:fill" src="'+esc(o['image'])+'">')
    else:content.append('<div style="'+esc(location)+'border:1px solid red;color:red">'+esc(o.get('missing_image','Missing image'))+'</div>')
   elif typ in ('6','7'):
    pen=float(o.get('PENSIZE') or 1);pen=max(pen,0.25);pattern=o.get('PENPAT');dash='stroke-dasharray="250 200"' if pattern in ('1','2','3','4') else ''
    if typ=='6':shape=f'<line x1="0" y1="0" x2="{max(w,0)*10000}" y2="{max(h,0)*10000}" stroke="black" stroke-width="{pen*10000/72}" {dash}/>'
    else:
     radius=float(o.get('OFFSET') or 0)/200*min(w,h)*10000;fill='none' if o.get('FILLPAT') in ('','0') else 'white';shape=f'<rect x="0" y="0" width="{max(w,0)*10000}" height="{max(h,0)*10000}" rx="{radius}" fill="{fill}" stroke="black" stroke-width="{pen*10000/72}" {dash}/>'
    content.append('<svg style="'+esc(location)+'overflow:visible" viewBox="0 0 '+str(max(w,0.0001)*10000)+' '+str(max(h,0.0001)*10000)+'" preserveAspectRatio="none">'+shape+'</svg>')
  transform=f'translate({settings["x"]}in,{settings["y"]}in) scale({settings["scale"]/100})'
  watermark='<div class="watermark">TEST / NON-NEGOTIABLE</div>' if settings['watermark'] else ''
  result.append('<section class="paper"><div class="content" style="transform:'+esc(transform)+'">'+''.join(content)+watermark+'</div></section>')
 notices=''.join('<p>'+esc(x)+'</p>' for x in dict.fromkeys(all_errors+all_warnings))
 button='<button onclick="window.print()">Print at actual size / Save PDF</button>' if not all_errors else '<strong>Printing blocked: resolve the listed original-layout fields/assets first.</strong>'
 return '<!doctype html><html><head><meta charset="utf-8"><title>Original report layout comparison</title><style>@page{size:letter portrait;margin:0}*{box-sizing:border-box}body{margin:0;background:#ddd}.toolbar{padding:12px;font:14px Arial;background:#fff}.paper{position:relative;width:8.5in;height:11in;margin:12px auto;background:white;overflow:hidden;break-after:page}.paper:last-child{break-after:auto}.content{position:absolute;width:8.5in;height:11in;transform-origin:0 0}.watermark{position:absolute;top:5in;left:1in;font:30pt Arial;color:#aaa;opacity:.4;transform:rotate(-25deg)}@media print{body{background:white}.toolbar{display:none}.paper{margin:0}}</style></head><body><div class="toolbar">'+button+'<p>Original saved geometry, fonts and text; notices updated to 15 business days. Letter, portrait, 100% / actual size, browser headers/footers off. Verify against an old-program print before use.</p>'+notices+'</div>'+''.join(result)+'</body></html>'


def editor(db,parent,kind='letter1'):
 login.require(db,True);win=tk.Toplevel(parent);win.title('Original FRX layout / Letter printing');win.geometry('970x760');choice=tk.StringVar(value=kind);state={};entries={}
 ttk.Combobox(win,textvariable=choice,values=list(DEFAULT_REPORTS),state='readonly').pack(anchor='w',padx=12,pady=8)
 ttk.Label(win,text='Compare with an old-program print. Select the active original variant, office-data source, and measured page origin. Preserved originals and earlier saved batches do not change.',wraplength=920).pack(anchor='w',padx=12)
 grid=ttk.Frame(win);grid.pack(fill='x',padx=12,pady=8)
 for i,(key,title,options) in enumerate([('mode','Mode',['original','edited']),('report','Original report file',sorted(library()['reports'])),('office_source','Office fields',['original','current']),('x','Horizontal shift (inches)',None),('y','Vertical shift (inches)',None),('scale','Scale percent (100 = original)',None)]):
  ttk.Label(grid,text=title).grid(row=i,column=0,sticky='w',pady=4);entry=ttk.Combobox(grid,values=options,state='readonly',width=65) if options else ttk.Entry(grid,width=65);entry.grid(row=i,column=1,sticky='ew');entries[key]=entry
 watermark=tk.BooleanVar();ttk.Checkbutton(win,text='Include test/non-negotiable watermark on the positioned page',variable=watermark).pack(anchor='w',padx=12)
 ttk.Label(win,text='Field overrides: JSON mapping original object record numbers to supported field expressions. No FoxPro/Python code executes. Example: {"12":"CK_DUE+FEE_DUE+DA_DUE+WD_DUE"}').pack(anchor='w',padx=12)
 overrides=tk.Text(win,height=5,wrap='word');overrides.pack(fill='both',expand=True,padx=12,pady=6)
 ttk.Label(win,text='Image aliases: JSON mapping missing basenames to a verified included bitmap. Available: '+', '.join(library()['assets'])).pack(anchor='w',padx=12)
 images=tk.Text(win,height=3,wrap='word');images.pack(fill='x',padx=12,pady=6)
 reason=ttk.Entry(win);reason.pack(fill='x',padx=12);ttk.Label(win,text='Change reason required. Missing images and unresolved expressions block printing.').pack(anchor='w',padx=12)
 def load(e=None):
  data=config(db,choice.get());row=db.execute('SELECT revision FROM legacy_original_print_settings WHERE kind=?',(choice.get(),)).fetchone();state['revision']=row[0] if row else -1
  for key,entry in entries.items():
   if isinstance(entry,ttk.Combobox):entry.set(str(data[key]))
   else:entry.delete(0,'end');entry.insert(0,str(data[key]))
  watermark.set(data['watermark']);overrides.delete('1.0','end');overrides.insert('end',json.dumps(data['field_overrides'],indent=2));images.delete('1.0','end');images.insert('end',json.dumps(data['image_aliases'],indent=2))
 def save():
  try:
   data={k:e.get() for k,e in entries.items()};data.update(watermark=watermark.get(),field_overrides=json.loads(overrides.get('1.0','end-1c')),image_aliases=json.loads(images.get('1.0','end-1c')));save_config(db,choice.get(),data,state['revision'],reason.get());win.destroy()
  except Exception as error:messagebox.showerror('Original print settings',str(error),parent=win)
 selector=win.winfo_children()[0];selector.bind('<<ComboboxSelected>>',load);load();ttk.Button(win,text='Save original-layout settings',command=save).pack(pady=10)
 return win
