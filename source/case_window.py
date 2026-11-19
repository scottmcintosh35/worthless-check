"""Four-tab legacy case file using source-row identity and audited working records."""
import json
from decimal import Decimal,InvalidOperation
import tkinter as tk
from tkinter import ttk,messagebox,simpledialog
import legacy_work as lw
import main_legacy
import login
import user_audit
import date_format

CASE_DIRECTORIES = {
    'BANK_CODE': ('BANKCODE','CODE','BANK','BANK','bank'),
    'MERCH_ID': ('WC_MERCH','ME_ID','ME_NAME','MERCHANT','merchant'),
    'DEF_ID': ('WC_DEF','ID','NAME','DEFENDANT','defendant'),
}

MAIN=[('DEFENDANT','Defendant'),('DEF_ID','Defendant ID'),('CASE_NO','Case number'),('ENTER_DATE','Case entry date'),('COMPLAINT','Complainant'),('CK_NO','Check number'),('ISSUE_DATE','Presented date'),('CK_DATE','Check date'),('CK_AMT','Check amount'),('MERCHANT','Paid to / merchant'),('MERCH_ID','Merchant ID'),('ITEM_CODE','Written for code'),('ITEM','Written for'),('BANK_CODE','Bank code'),('BANK','Bank'),('ARRESTED','Surrender date'),('WARR_LOC','Warrant location'),('WARR_CODE','Warrant code'),('ACTIVATED','Warrant active date'),('ACT_WARR','Active warrant'),('VISIT','On visit list'),('RECALLED','Mark for recall'),('LTR_SENT','First letter printed'),('LTR_SIGNED','Certified letter signed by'),('SIGNED','Date signed'),('LTR_CLAIM','Letter was unclaimed'),('LTR_SENT2','Second letter printed'),('LTR_SENT3','Final letter printed'),('DISP_CODE','Disposition code'),('DISP_NARR','Disposition'),('DUE_DATE','Due date'),('COMMENT','Comments'),('DISP','Disposition details')]
DEF=[('NAME','Name'),('ID','ID'),('ADDRESS','Address'),('ADDRESS2','Address #2'),('CITY','City'),('STATE','State'),('ZIP','ZIP'),('TELEPHONE','Phone'),('DOB','Date of birth'),('SEX','Sex'),('RACE','Race'),('LICENSE',"Driver's license"),('SSN','SSN'),('HAIR','Hair'),('EYES','Eyes'),('WEIGHT','Weight'),('HEIGHT_FT','Height feet'),('HEIGHT_IN','Height inches'),('EMPLOYER','Employer'),('EMP_PHONE','Employer phone'),('HISTORY','Comments / address history')]
MERCH=[('ME_NAME','Merchant'),('ME_ID','ID'),('ME_ADDR','Address'),('ME_CITY','City'),('ME_STATE','State'),('ME_ZIP','ZIP'),('ME_PHONE','Telephone'),('ME_CONTACT','Contact')]
FINANCE=[('Check amount','CK_AMT','REST_PAID','CK_DUE'),('DA fee','FIRST_OFF','FO_PAID','DA_DUE'),('Merchant fee','MERCH_FEE','SFEE_PAID','FEE_DUE'),('Withdrawal fee','WITHDRAWAL','WD_PAID','WD_DUE')]

def id_value(value):
    value=str(value or '').strip()
    if not value:return None
    try:
        number=Decimal(value)
        if not number.is_finite() or number==0:return None
        return format(number.normalize(),'f')
    except InvalidOperation:return value

def linked_rows(db,table,id_field,value):
    key=id_value(value)
    if key is None:return []
    try:
        Decimal(key);sql="CAST(json_extract(data_json,?) AS NUMERIC)=CAST(? AS NUMERIC)";args=('$.'+id_field,key)
    except InvalidOperation:sql='trim(json_extract(data_json,?))=?';args=('$.'+id_field,key)
    return [r for r in db.execute('SELECT * FROM working_legacy WHERE table_name=? AND deleted=0 AND '+sql,(table,*args)) if id_value(json.loads(r['data_json']).get(id_field))==key]

class LogicalField(ttk.Frame):
    def __init__(self,parent,value):
        super().__init__(parent);self.value=tk.StringVar(master=self,value=value);self.button=ttk.Checkbutton(self,text='Yes',variable=self.value,onvalue='T',offvalue='F');self.button.pack(anchor='w')
    def get(self):return self.value.get()


class DirectoryPicker(ttk.Combobox):
    def __init__(self, parent, options, *, ignore_id_padding=False):
        super().__init__(parent, width=30, postcommand=self.open_native_list)
        self.options = options
        self.ignore_id_padding = ignore_id_padding
        self.popup = None
        self.bind('<KeyRelease>', self.on_key_release)
        self.bind('<Down>', lambda event: self.move_selection(1))
        self.bind('<Up>', lambda event: self.move_selection(-1))
        self.bind('<Return>', self.accept_selection)
        self.bind('<KP_Enter>', self.accept_selection)
        self.bind('<Shift-Return>', self.accept_on_backtab)
        self.bind('<Shift-KP_Enter>', self.accept_on_backtab)
        self.bind('<Tab>', self.accept_on_tab)
        self.bind('<Shift-Tab>', self.accept_on_backtab)
        self.bind('<ISO_Left_Tab>', self.accept_on_backtab)
        self.bind('<Escape>', self.cancel_suggestions)
        self.bind('<FocusOut>', lambda event: self.after_idle(self.hide_if_unfocused))
        self.bind('<FocusIn>', self.select_lookup_text)
        self.bind('<Unmap>', self.hide_suggestions)
        self.bind('<Configure>', self.hide_suggestions)
        self.configure(values=['', *options])

    def select_lookup_text(self, event):
        self.selection_range(0, 'end')
        self.icursor('end')

    def open_native_list(self):
        self.hide_suggestions()
        self.filter_choices()

    def filter_choices(self):
        term = self.get().strip().casefold()
        if self.get() in self.options or self.get() == getattr(self,'original_label',None):
            term = ''
        exact = []
        partial = []
        for label, (code, _) in self.options.items():
            if self.matches_id(term, code):
                exact.append(label)
            elif term in label.casefold():
                partial.append(label)
        self.configure(values=exact + partial)
        return len(exact)

    def matches_id(self, term, code):
        code = code.casefold()
        if term == code:
            return True
        return (self.ignore_id_padding and term.isascii() and term.isdecimal()
                and code.isascii() and code.isdecimal()
                and term.lstrip('0') == code.lstrip('0'))

    def on_key_release(self, event):
        if not event.char and event.keysym not in ('BackSpace','Delete'):
            return
        if event.keysym in ('Return','KP_Enter','Escape','Tab','BackTab','ISO_Left_Tab'):
            return
        exact_count = self.filter_choices()
        matches = self['values']
        if not self.get().strip() or self.get() in self.options or not matches:
            self.hide_suggestions()
            return
        if self.popup is None:
            self.popup = tk.Toplevel(self)
            self.popup.withdraw()
            self.popup.overrideredirect(True)
            self.popup.transient(self.winfo_toplevel())
            self.results = tk.Listbox(self.popup, exportselection=False, takefocus=False)
            scroll = ttk.Scrollbar(self.popup, command=self.results.yview)
            self.results.configure(yscrollcommand=scroll.set)
            scroll.pack(side='right', fill='y')
            self.results.pack(side='left', fill='both', expand=True)
            self.results.bind('<ButtonPress-1>', self.pick_with_mouse)
        self.results.delete(0, 'end')
        self.results.insert('end', *matches)
        self.results.configure(height=min(8,len(matches)))
        if exact_count <= 1:
            self.results.selection_set(0)
        self.popup.update_idletasks()
        height = self.popup.winfo_reqheight()
        top = self.winfo_rooty() + self.winfo_height()
        if top + height > self.winfo_vrooty() + self.winfo_vrootheight():
            top = self.winfo_rooty() - height
        self.popup.geometry(f'{max(self.winfo_width(),360)}x{height}+{self.winfo_rootx()}+{top}')
        self.popup.deiconify()
        self.popup.lift()

    def hide_suggestions(self, event=None):
        if self.popup is not None:
            popup, self.popup = self.popup, None
            popup.destroy()

    def hide_if_unfocused(self):
        if self.popup is None or not self.winfo_exists():
            return
        focused = self.focus_get()
        if focused is not self and (focused is None or focused.winfo_toplevel() is not self.popup):
            self.hide_suggestions()

    def cancel_suggestions(self, event):
        if self.popup is not None:
            self.hide_suggestions()
            return 'break'

    def move_selection(self, delta):
        if self.popup is None:
            return
        selected = self.results.curselection()
        index = selected[0] + delta if selected else (0 if delta > 0 else self.results.size()-1)
        index = min(max(index,0),self.results.size()-1)
        self.results.selection_clear(0,'end')
        self.results.selection_set(index)
        self.results.see(index)
        return 'break'

    def pick_with_mouse(self, event):
        self.choose_suggestion(self.results.nearest(event.y))
        return 'break'

    def accept_selection(self, event):
        if self.popup is not None:
            selected = self.results.curselection()
            if selected:
                self.choose_suggestion(selected[0])
                self.tk_focusNext().focus_set()
            return 'break'
        if self.get() in self.options:
            self.tk_focusNext().focus_set()
            return 'break'

    def accept_on_tab(self, event):
        if self.popup is not None and self.results.curselection():
            return self.accept_selection(event)

    def accept_on_backtab(self, event):
        if self.popup is not None:
            selected = self.results.curselection()
            if selected:
                self.choose_suggestion(selected[0])
                self.tk_focusPrev().focus_set()
                return 'break'

    def choose_suggestion(self, index):
        self.set(self.results.get(index))
        self.hide_suggestions()
        self.focus_set()
        self.icursor('end')
        self.event_generate('<<ComboboxSelected>>')

    def selected(self):
        if self.get() in self.options:
            return self.options[self.get()]
        value = self.get().strip().casefold()
        if not value:
            return None
        matches = [pair for label, pair in self.options.items()
                   if self.matches_id(value, pair[0])]
        if not matches:
            matches = [pair for label, pair in self.options.items()
                       if value in (label.casefold(), pair[1].casefold())]
        if not matches:
            matches = [pair for label, pair in self.options.items() if value in label.casefold()]
        return matches[0] if len(matches) == 1 else None

class CaseWindow:
    def __init__(self,app,record=None):
        self.app=app;self.db=app.store.db;self.record=record;self.entities={};self.editors={};self.initial={};self.frames={};self.canvases={}
        self.win=tk.Toplevel(app.root);self.win.geometry('1080x780');self.win.minsize(900,650)
        self.heading=tk.StringVar();ttk.Label(self.win,textvariable=self.heading,font=('Segoe UI',12,'bold')).pack(anchor='w',padx=12,pady=8)
        nav=ttk.Frame(self.win);nav.pack(fill='x',padx=12)
        for title,fn in [('Prior',lambda:self.move(-1)),('Next',lambda:self.move(1)),('Search / Browse',self.browse),('Add New Record',lambda:CaseWindow(app)),('All original fields',self.advanced),('Refresh',self.refresh)]:ttk.Button(nav,text=title,command=lambda f=fn:self.safe(f)).pack(side='left',padx=3)
        self.book=ttk.Notebook(self.win);self.book.pack(fill='both',expand=True,padx=12,pady=8)
        for title in ('Main Case','Defendant','Merchant','Restitution'):
            frame=ttk.Frame(self.book);self.book.add(frame,text=title);self.frames[title]=frame
        footer=ttk.Frame(self.win);footer.pack(side='bottom',fill='x',padx=12,pady=8,before=self.book);self.reason=ttk.Entry(footer,width=60)
        ttk.Label(footer,text='Change reason:').pack(side='left');self.reason.pack(side='left',fill='x',expand=True,padx=8)
        ttk.Button(footer,text='Save active tab (Ctrl+W)',command=lambda:self.safe(self.save_active)).pack(side='left')
        self.status=tk.StringVar();ttk.Label(self.win,textvariable=self.status,wraplength=1000).pack(side='bottom',fill='x',padx=12,pady=(0,8),before=self.book)
        self.win.bind('<Control-w>',lambda event:(self.safe(self.save_active),'break')[1])
        self.win.protocol('WM_DELETE_WINDOW',self.close)
        import legacy_navigation,legacy_functions
        menu=tk.Menu(self.win);database=tk.Menu(menu,tearoff=False);legacy_navigation.populate(database,app);menu.add_cascade(label='Database',menu=database)
        functions=tk.Menu(menu,tearoff=False);legacy_functions.populate_menu(functions,lambda action:self.safe(lambda:legacy_functions.Center(self.context(),action)),self.db);menu.add_cascade(label='Functions',menu=functions);self.win.configure(menu=menu)
        self.load(record)
        self.win.state('zoomed')
        self.book.bind('<<NotebookTabChanged>>',lambda event:self.safe(self.audit_tab))
    def audit_tab(self):
        if not self.row:
            return
        tab=self.book.tab(self.book.select(),'text')
        table={'Defendant':'WC_DEF','Merchant':'WC_MERCH'}.get(tab)
        if table and table in self.entities:
            user_audit.opened(self.db,tab.upper(),f"{table} / row {self.entities[table]['record_no']} / case row {self.record}")
        elif tab=='Restitution':
            user_audit.opened(self.db,'RESTITUTION',user_audit.case_ref(self.data.get('CASE_NO',''),self.record))
    def safe(self,fn):
        try:return fn()
        except Exception as error:messagebox.showerror('Case file',str(error),parent=self.win)
    def context(self,table='WC_CASE',record=None):
        context=main_legacy.Context(self.app,self.record if record is None else record);context.win=self.win;context.table.set(table)
        def changed():
            self.app.refresh()
            if self.win.winfo_exists():
                if not self.dirty():self.load(self.record)
                else:self.status.set('Working records updated. Save or discard your current edits, then Refresh.')
        context.refresh=changed;return context
    def dirty(self):return any(self.values(table)!=values for table,values in self.initial.items())
    def allow_discard(self):return not self.dirty() or messagebox.askyesno('Unsaved changes','Discard unsaved changes on these tabs?',parent=self.win)
    def close(self):
        if self.allow_discard():self.win.destroy()
    def refresh(self):
        if self.allow_discard():self.load(self.record)
    def values(self,table):
        values = {key:(w.get('1.0','end-1c') if isinstance(w,tk.Text) else w.get()) for key,w in self.editors.get(table,{}).items()}
        if table == 'WC_CASE':
            if self.row is None:
                values['CASE_NO'] = ''
            for key in self.case_choices:
                name = CASE_DIRECTORIES[key][3]
                picker = self.editors.get(table, {}).get(key)
                if not isinstance(picker, DirectoryPicker):
                    continue
                if picker.get() == picker.original_label:
                    values[key] = picker.original_id
                    continue
                choice = picker.selected()
                if choice:
                    values[key], values[name] = choice
        return values

    def directory_choices(self):
        choices = {}
        for field, (table, key, name, _, _) in CASE_DIRECTORIES.items():
            items = {}
            rows = self.db.execute('SELECT data_json FROM working_legacy WHERE table_name=? AND deleted=0',
                                   (table,))
            for (encoded,) in rows:
                data = json.loads(encoded)
                code, label = (str(data.get(k) or '').strip() for k in (key, name))
                if code and label:
                    items[f'{code} - {label}'] = (code, label)
            choices[field] = dict(sorted(items.items(), key=lambda item: item[0].casefold()))
        return choices

    def add_directory_entry(self, table, field):
        import legacy_navigation

        def saved(data):
            self.case_choices = self.directory_choices()
            picker = self.editors['WC_CASE'].get(field)
            if isinstance(picker, DirectoryPicker):
                picker.options = self.case_choices[field]
                _, key, name, _, _ = CASE_DIRECTORIES[field]
                picker.set(f'{str(data[key]).strip()} - {str(data[name]).strip()}')
                picker.event_generate('<<ComboboxSelected>>')

        legacy_navigation.add_directory_entry(self.app, table, parent=self.win, on_saved=saved)
    def load(self,record):
        self.record=record;self.entities={};self.editors={};self.initial={}
        for frame in self.frames.values():
            for child in frame.winfo_children():child.destroy()
        self.row=lw.get(self.db,'WC_CASE',record) if record is not None else None
        self.case_choices = self.directory_choices()
        if self.row:
            user_audit.opened(self.db,'CASE',user_audit.case_ref(json.loads(self.row['data_json']).get('CASE_NO',''),record))
        import case_defaults
        self.data=json.loads(self.row['data_json']) if self.row else case_defaults.legacy_defaults(self.db)
        self.win.title('Worthless Check File | WC_CASE / source row '+str(record));self.heading.set('Defendant: '+str(self.data.get('DEFENDANT',''))+'     Case No. '+str(self.data.get('CASE_NO','(new)'))+'     Source row '+str(record or '(new)'))
        if self.row is None:
            self.data.update(CK_AMT='0.00',CK_DUE='0.00')
        fields=MAIN+([('FIRST_OFF','Initial DA fee'),('MERCH_FEE','Initial merchant fee'),('WITHDRAWAL','Initial withdrawal fee')] if self.row is None else [])
        self.form(self.frames['Main Case'],'WC_CASE',self.data,fields)
        actions=ttk.Frame(self.frames['Main Case']);actions.pack(side='bottom',fill='x',pady=6,before=self.canvases['WC_CASE'])
        commands = [('Comment / disposition',self.comment),('Bank codes',lambda:self.codes('BANKCODE')),('WC / disposition codes',lambda:self.codes('WC_CODE')),('Recalculate due date',self.recalculate_due),('Print complaint',lambda:self.report('complaint.single')),('Delete / recover case',self.mark_case)]
        commands.extend([('Add Bank / Code',lambda:self.add_directory_entry('BANKCODE','BANK_CODE')),
                         ('Add Merchant / ID',lambda:self.add_directory_entry('WC_MERCH','MERCH_ID')),
                         ('Add Defendant',lambda:self.add_directory_entry('WC_DEF','DEF_ID'))])
        for i,(label,fn) in enumerate(commands):ttk.Button(actions,text=label,command=lambda f=fn:self.safe(f)).grid(row=i//3,column=i%3,sticky='ew',padx=3,pady=3)
        for column in range(3):actions.columnconfigure(column,weight=1)
        for title,table,field,foreign,fields in [('Defendant','WC_DEF','ID','DEF_ID',DEF),('Merchant','WC_MERCH','ME_ID','MERCH_ID',MERCH)]:
            frame=self.frames[title];bar=ttk.Frame(frame);bar.pack(fill='x',pady=6)
            for i,(label,fn) in enumerate([('Change '+title,lambda t=table:self.choose_party(t)),('Browse',lambda t=table:self.codes(t)),('View History',lambda t=table:self.party_history(t)),('Edit ZIP codes',lambda:self.codes('AZIPS'))]):ttk.Button(bar,text=label,command=lambda f=fn:self.safe(f)).grid(row=0,column=i,sticky='ew',padx=4,pady=3)
            if table=='WC_DEF':
                ttk.Button(bar,text='Aliases',command=lambda:self.safe(self.aliases)).grid(row=1,column=0,padx=4,pady=3)
                for i,(label,paid) in enumerate([('Pending cases',False),('Paid cases',True)],1):ttk.Button(bar,text=label,command=lambda p=paid:self.safe(lambda:self.related_cases(p))).grid(row=1,column=i,padx=4,pady=3)
            matches=linked_rows(self.db,table,field,self.data.get(foreign)) if self.row else []
            if len(matches)==1:
                row=matches[0];self.entities[table]=row;self.form(frame,table,json.loads(row['data_json']),fields,readonly=(field,))
                ttk.Label(frame,text='This is the shared '+title.lower()+' record. Saving changes updates this record for every linked case.',wraplength=950).pack(side='bottom',pady=6)
            else:ttk.Label(frame,text=('No matching active '+title.lower()+' record.' if not matches else 'Multiple source records share this ID; no record was selected automatically.')+' Use Change '+title+' / Browse, then save the case link on Main Case.',wraplength=900).pack(padx=20,pady=25)
        self.finance();self.status.set(('New cases require a signed-in user and a reason. ' if self.row is None else 'Existing-record changes require an Administrator and a reason. ')+'Each tab saves its own source record; the original backup stays unchanged.')
    def form(self,parent,table,data,fields,readonly=()):
        canvas=tk.Canvas(parent,highlightthickness=0);scroll=ttk.Scrollbar(parent,orient='vertical',command=canvas.yview);scroll.pack(side='right',fill='y');canvas.pack(side='top',fill='both',expand=True);canvas.configure(yscrollcommand=scroll.set)
        body=ttk.Frame(canvas);window=canvas.create_window(0,0,window=body,anchor='nw');body.bind('<Configure>',lambda event:canvas.configure(scrollregion=canvas.bbox('all')));canvas.bind('<Configure>',lambda event:canvas.itemconfigure(window,width=event.width))
        self.canvases[table]=canvas
        schema={f['name']:f for f in lw.schema(self.db,table)};entries={}
        for i,(key,label) in enumerate((pair for pair in fields if pair[0] in schema)):
            if table == 'WC_CASE' and key == 'DEF_ID':
                label = 'Defendant lookup'
            row=i//2;column=(i%2)*2;value=lw.memo_text(self.db,table,data.get(key,''))
            if table == 'WC_DEF' and key == 'SSN':
                label = f'SSN {lw.masked_ssn(value)}'.rstrip()
            ttk.Label(body,text=label).grid(row=row,column=column,sticky='w',padx=8,pady=6)
            if schema[key]['type']=='D':value=date_format.display(value)
            if table == 'WC_CASE' and self.row is None and key == 'CASE_NO':
                widget = ttk.Entry(body,width=30)
                widget.insert(0,'Assigned when saved')
                widget.configure(state='readonly')
            elif table == 'WC_CASE' and key in self.case_choices:
                widget = DirectoryPicker(body,self.case_choices[key],ignore_id_padding=True)
                name_key = CASE_DIRECTORIES[key][3]
                widget.original_id = value
                widget.original_label = f'{value} - {data[name_key]}' if value and data.get(name_key) else value
                widget.set(widget.original_label)
                def fill_name(event, code_key=key, picker=widget):
                    name_key = CASE_DIRECTORIES[code_key][3]
                    target = entries.get(name_key)
                    choice = picker.selected()
                    if target and choice:
                        target.delete(0,'end')
                        target.insert(0,choice[1])
                widget.bind('<<ComboboxSelected>>',fill_name)
            elif schema[key]['type']=='L':widget=LogicalField(body,value)
            elif schema[key]['type']=='M':widget=tk.Text(body,width=30,height=4,wrap='word');widget.insert('1.0',value)
            elif table == 'WC_DEF' and key == 'SSN':
                widget=ttk.Entry(body,width=30,show='*')
                widget.insert(0,value)
            else:widget=ttk.Entry(body,width=30);widget.insert(0,value)
            widget.grid(row=row,column=column+1,sticky='ew',padx=8,pady=6);entries[key]=widget
            if key in readonly:widget.configure(state='readonly')
        body.columnconfigure(1,weight=1);body.columnconfigure(3,weight=1);self.editors[table]=entries;self.initial[table]=self.values(table)
    def save_active(self):
        title=self.book.tab(self.book.select(),'text');table={'Main Case':'WC_CASE','Defendant':'WC_DEF','Merchant':'WC_MERCH'}.get(title)
        if not table:self.status.set('Use Manual Pay or Pay All on Restitution to review and post a payment.');return
        if table not in self.editors:raise ValueError('Select a unique linked record before editing this tab.')
        values=self.values(table);changes={k:v for k,v in values.items() if v!=self.initial[table][k]};reason=self.reason.get()
        if table=='WC_CASE':
            for field in self.case_choices:
                directory, id_field, _, _, label = CASE_DIRECTORIES[field]
                picker = self.editors[table].get(field)
                if not isinstance(picker, DirectoryPicker) or picker.get() == picker.original_label:
                    continue
                if picker.get().strip() and not picker.selected():
                    raise ValueError(f'Select a matching {label} from the dropdown.')
                if field != 'BANK_CODE' and values.get(field) and len(linked_rows(self.db,directory,id_field,values[field])) != 1:
                    raise ValueError(f'The selected {label} ID must identify one active {label}.')
            for link,party in [('DEF_ID','WC_DEF'),('MERCH_ID','WC_MERCH')]:
                if link in changes and party in self.initial and self.values(party)!=self.initial[party]:raise ValueError('Save or discard the linked party tab changes before changing its case link.')
            if self.row:lw.save(self.db,table,self.record,changes,self.row['deleted'],self.row['revision'],reason)
            else:
                if values.get('ENTER_DATE')!=self.initial[table].get('ENTER_DATE') and values.get('DUE_DATE')==self.initial[table].get('DUE_DATE'):
                    import case_defaults
                    values['DUE_DATE']=case_defaults.due_date(self.db,values['ENTER_DATE']).isoformat()
                values.update(CK_DUE=values.get('CK_AMT','0.00'),FEE_DUE=values.get('MERCH_FEE',self.data.get('MERCH_FEE','30.00')),DA_DUE=values.get('FIRST_OFF',self.data.get('FIRST_OFF','0.00')),WD_DUE=values.get('WITHDRAWAL',self.data.get('WITHDRAWAL','30.00')))
                allowed={f['name'] for f in lw.schema(self.db,table)};self.record=lw.create(self.db,table,{k:v for k,v in values.items() if k in allowed},reason)
            self.row=lw.get(self.db,table,self.record);self.data=json.loads(self.row['data_json']);self.initial[table]=values
            # Save other tab drafts before rebuilding the linked profile forms.
            if any(self.values(t)!=v for t,v in self.initial.items() if t!=table):self.status.set('Main Case saved. Other tab edits remain unsaved; save them before Refresh.')
            else:self.load(self.record)
        else:
            row=self.entities[table];lw.save(self.db,table,row['record_no'],changes,row['deleted'],row['revision'],reason);self.entities[table]=lw.get(self.db,table,row['record_no']);self.initial[table]=values;self.status.set(title+' changes saved with an audit record.')
        self.app.refresh()
    def require_saved(self):
        if self.record is None:raise ValueError('Save Main Case before using linked history, forms or payments.')
        if self.dirty():raise ValueError('Save or discard tab changes before continuing.')
    def finance(self):
        frame=self.frames['Restitution'];bar=ttk.Frame(frame);bar.pack(fill='x',pady=8)
        for label,fn in [('Manual Pay',lambda:self.pay(False)),('Paid All - review payment',lambda:self.pay(True)),('Payment History',self.history),('Adjustments / all fields',self.advanced),('Delete / correct payment',self.history)]:ttk.Button(bar,text=label,command=lambda f=fn:self.safe(f)).pack(side='left',padx=4)
        grid=ttk.Frame(frame);grid.pack(fill='x',padx=20,pady=20)
        for c,label in enumerate(('','Initial due','Paid','Balance due')):ttk.Label(grid,text=label,font=('Segoe UI',10,'bold')).grid(row=0,column=c,padx=20,pady=8)
        totals=[Decimal('0')]*3
        for r,(label,*keys) in enumerate(FINANCE,1):
            ttk.Label(grid,text=label).grid(row=r,column=0,sticky='w',padx=20,pady=8)
            for c,key in enumerate(keys,1):
                try:value=lw.money(self.data.get(key,''));text='$'+format(value,',.2f');totals[c-1]=totals[c-1]+value if totals[c-1] is not None else None
                except ValueError:text='REVIEW';totals[c-1]=None
                ttk.Label(grid,text=text).grid(row=r,column=c,padx=20,pady=8)
        for c,value in enumerate(totals,1):ttk.Label(grid,text='$'+format(value,',.2f') if value is not None else 'REVIEW',font=('Segoe UI',10,'bold')).grid(row=5,column=c,padx=20,pady=8)
        ttk.Label(grid,text='Totals').grid(row=5,column=0,sticky='w',padx=20)
        for r,(key,label) in enumerate([('OVERPAID','Overpaid'),('RECEIPT_NO','Last receipt #'),('INITIALS','Received by'),('DA_CK_NO','DA check # to merchant'),('DA_CK_DATE','DA check date')],6):
            value=lw.memo_text(self.db,'WC_CASE',self.data.get(key,''))
            if key=='DA_CK_DATE':value=date_format.display(value)
            ttk.Label(grid,text=label+': '+value).grid(row=r,column=0,columnspan=4,sticky='w',padx=20,pady=5)
        ttk.Label(frame,text='Recorded initial, paid and due values are shown separately. Legacy discrepancies are preserved for reconciliation; opening this screen does not recalculate balances.',wraplength=950).pack(padx=20,pady=10)
    def pay(self,all_due):
        self.require_saved();prefill=None
        if all_due:
            due=main_legacy.balances(self.data)
            if any(value<0 for value in due):raise ValueError('Reconcile negative balances before using Paid All.')
            prefill=dict(zip(('REST_PAID','SFEE_PAID','FO_PAID','WD_PAID'),[format(v,'.2f') for v in due]))
        self.context().payment(prefill=prefill)
    def history(self):self.require_saved();self.context().history()
    def advanced(self):
        if self.record is None:raise ValueError('Save Main Case first, then open additional original fields.')
        self.require_saved();lw.Workspace.details_all_fields(self.context())
    def codes(self,table):
        import legacy_navigation
        legacy_navigation.show_table(self.app,table)
    def report(self,action):
        self.require_saved();import legacy_functions;legacy_functions.Center(self.context(),action)
    def move(self,step):
        if not self.allow_discard():return
        if self.record is None:return
        op,order=('>','ASC') if step>0 else ('<','DESC')
        row=self.db.execute("SELECT record_no FROM working_legacy WHERE table_name='WC_CASE' AND deleted=0 AND record_no "+op+'? ORDER BY record_no '+order+' LIMIT 1',(self.record,)).fetchone()
        if row:self.load(row[0])
        else:self.status.set('No more active cases in this direction.')
    def browse(self):self.choose_record('WC_CASE',lambda row:self.load(row['record_no']) if self.allow_discard() else None)
    def choose_record(self,table,callback):
        win=tk.Toplevel(self.win);win.title('Select '+table+' source record');win.geometry('920x560');q=tk.StringVar();bar=ttk.Frame(win);bar.pack(fill='x',padx=10,pady=8);ttk.Entry(bar,textvariable=q,width=45).pack(side='left');tree=ttk.Treeview(win,columns=('row','id','name'),show='headings')
        for key in tree['columns']:tree.heading(key,text=key);tree.column(key,width=250)
        tree.pack(fill='both',expand=True,padx=10,pady=8)
        def search():
            tree.delete(*tree.get_children())
            for row in self.db.execute('SELECT * FROM working_legacy WHERE table_name=? AND deleted=0 AND data_json LIKE ? ORDER BY record_no LIMIT 200',(table,'%'+q.get()+'%')):
                data=json.loads(row['data_json']);tree.insert('','end',iid=str(row['record_no']),values=(row['record_no'],data.get('CASE_NO',data.get('ID',data.get('ME_ID',''))),data.get('DEFENDANT',data.get('NAME',data.get('ME_NAME','')))))
        def select():
            if not tree.selection():return
            callback(lw.get(self.db,table,int(tree.selection()[0])));win.destroy()
        ttk.Button(bar,text='Search all records (first 200 matches)',command=lambda:self.safe(search)).pack(side='left',padx=8);ttk.Button(win,text='Use selected source record',command=lambda:self.safe(select)).pack(pady=8);tree.bind('<Double-1>',lambda e:self.safe(select));search()
    def choose_party(self,table):
        def selected(row):
            data=json.loads(row['data_json']);pairs={'WC_DEF':('DEF_ID','DEFENDANT','ID','NAME'),'WC_MERCH':('MERCH_ID','MERCHANT','ME_ID','ME_NAME')}[table]
            for destination,source in zip(pairs[:2],pairs[2:]):
                widget=self.editors['WC_CASE'].get(destination)
                if isinstance(widget, DirectoryPicker):
                    _, id_field, name_field, _, label = CASE_DIRECTORIES[destination]
                    code, name = (str(data.get(k) or '').strip() for k in (id_field,name_field))
                    choice = f'{code} - {name}'
                    if choice not in widget.options:
                        raise ValueError(f'Choose an active {label} with an ID and name.')
                    widget.set(choice)
                elif widget:widget.delete(0,'end');widget.insert(0,str(data.get(source,'')))
            self.book.select(self.frames['Main Case']);self.status.set('Proposed linked party selected. Enter a reason and save Main Case to apply this change.')
        self.choose_record(table,selected)
    def party_history(self,table):
        row=self.entities.get(table)
        if not row:raise ValueError('Select a unique linked record first.')
        context=self.context(table,row['record_no']);lw.Workspace.details_all_fields(context)
    def aliases(self):
        self.require_saved();rows=linked_rows(self.db,'ALIAS','AL_ID',self.data.get('DEF_ID'));win=tk.Toplevel(self.win);win.title('Aliases for defendant '+str(self.data.get('DEF_ID','')))
        tree=ttk.Treeview(win,columns=('source','name','address'),show='headings');tree.pack(fill='both',expand=True)
        for key in tree['columns']:tree.heading(key,text=key)
        for row in rows:
            data=json.loads(row['data_json']);tree.insert('','end',iid=str(row['record_no']),values=(row['record_no'],data.get('AL_NAME',''),data.get('AL_ADDR','')))
        def edit():
            if tree.selection():lw.Workspace.details_all_fields(self.context('ALIAS',int(tree.selection()[0])))
        ttk.Button(win,text='View / edit selected alias',command=lambda:self.safe(edit)).pack(pady=8)

    def related_cases(self,paid):
        self.require_saved();win=tk.Toplevel(self.win);win.title('Paid cases' if paid else 'Pending cases');tree=ttk.Treeview(win,columns=('source','case','defendant','due'),show='headings');tree.pack(fill='both',expand=True)
        for key in tree['columns']:tree.heading(key,text=key)
        for row in linked_rows(self.db,'WC_CASE','DEF_ID',self.data.get('DEF_ID')):
            data=json.loads(row['data_json'])
            try:amount=sum(main_legacy.balances(data))
            except ValueError:continue
            if (amount==0)!=paid:continue
            tree.insert('','end',iid=str(row['record_no']),values=(row['record_no'],data.get('CASE_NO',''),data.get('DEFENDANT',''),format(amount,'.2f')))
        tree.bind('<Double-1>',lambda event:self.load(int(tree.selection()[0])) if tree.selection() and self.allow_discard() else None)
    def comment(self):
        self.book.select(self.frames['Main Case']);self.canvases['WC_CASE'].yview_moveto(1)
        widget=self.editors['WC_CASE'].get('COMMENT')
        if widget:widget.focus_set()
    def recalculate_due(self):
        import case_defaults
        entries=self.editors['WC_CASE'];due=date_format.display(case_defaults.due_date(self.db,entries['ENTER_DATE'].get()));entries['DUE_DATE'].delete(0,'end');entries['DUE_DATE'].insert(0,due);self.book.select(self.frames['Main Case']);self.status.set('Due date recalculated. Save Main Case with a reason to apply it.')
    def mark_case(self):
        self.require_saved();reason=self.reason.get()
        if not messagebox.askyesno('Case marker','Change the deleted / archived marker? The original backup is retained.',parent=self.win):return
        lw.save(self.db,'WC_CASE',self.record,{},not self.row['deleted'],self.row['revision'],reason);self.load(self.record);self.app.refresh()
