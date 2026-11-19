"""Office heading shared by the application and printable documents."""
HEADING = (
    'Office of the District Attorney',
    'Twelfth Judicial Circuit',
    'State of Alabama',
    'Worthless Check Unit - Pike County',
)
HEADING_TEXT = '\n'.join(HEADING)


def show_heading(parent, lines=None):
    from tkinter import ttk
    frame=ttk.Frame(parent)
    frame.pack(fill='x',padx=18,pady=(12,8))
    update_heading(frame, lines)
    return frame


def update_heading(frame, lines=None):
    from tkinter import ttk
    for child in frame.winfo_children():
        child.destroy()
    for index,line in enumerate(lines or HEADING):
        ttk.Label(frame,text=line,font=('Segoe UI',16 if index==0 else 11,'bold'),
            anchor='w',padding=(16, 3),style='Office.TLabel').pack(fill='x')
