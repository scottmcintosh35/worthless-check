"""Visible keyboard guidance scoped to lists, never global save/delete bindings."""
import tkinter as tk
from tkinter import ttk

MAIN=[('Ctrl+Enter','Open details for the selected case'),('Ctrl+W','Open payment history for the selected case'),('Ctrl+F','Focus the case search box'),('F5','Refresh the current case list'),('Esc','Clear the list selection'),('F1','Show keyboard shortcuts')]
DIRECTORY=[('Ctrl+Enter','Open selected defendant details'),('Ctrl+W','Link selected profile to the selected sample case (sample mode only)'),('Ctrl+F','Focus defendant search'),('F5','Refresh defendant list'),('Esc','Clear the list selection'),('F1','Show keyboard shortcuts')]
LEGACY=[('Ctrl+Enter','View/correct all fields for the selected source row'),('Ctrl+W','Open case payment history (WC_CASE only)'),('Ctrl+F','Focus search for the current table'),('F5','Refresh the current table/page'),('Esc','Clear the list selection'),('F1','Show keyboard shortcuts')]

def strip(parent,text):
    label=ttk.Label(parent,text=text,style='Shortcut.TLabel',padding=(8,5),wraplength=1000,relief='solid',borderwidth=1)
    label.pack(fill='x',padx=12,pady=(4,2));return label

def clear_selection(tree):
    selected=tree.selection()
    if selected:tree.selection_remove(*selected)

def focus_search(entry):entry.focus_set();entry.selection_range(0,'end')

def bind_list(tree,actions):
    handlers={}
    for sequence,action in actions.items():
        def handle(event=None,fn=action):fn();return 'break'
        tree.bind(sequence,handle);handlers[sequence]=handle
    return handlers

def show_help(parent,title,rows):
    existing=getattr(parent,'_shortcut_help',None)
    if existing is not None and existing.winfo_exists():existing.destroy()
    win=tk.Toplevel(parent);parent._shortcut_help=win;win.title(title+' - Keyboard shortcuts');win.transient(parent)
    ttk.Label(win,text=title,font=('Segoe UI',12,'bold')).grid(row=0,column=0,columnspan=2,sticky='w',padx=16,pady=12)
    for i,(key,description) in enumerate(rows,1):
        ttk.Label(win,text=key,font=('Segoe UI',10,'bold')).grid(row=i,column=0,sticky='nw',padx=16,pady=5)
        ttk.Label(win,text=description,wraplength=480).grid(row=i,column=1,sticky='w',padx=16,pady=5)
    ttk.Label(win,text='List shortcuts apply when the list has focus. Enter in a search box runs the search. Use the arrow keys to move between rows.').grid(row=len(rows)+1,column=0,columnspan=2,padx=16,pady=12)
    ttk.Button(win,text='Close',command=win.destroy).grid(row=len(rows)+2,column=1,sticky='e',padx=16,pady=12)
    win.bind('<Escape>',lambda event:win.destroy());return win
