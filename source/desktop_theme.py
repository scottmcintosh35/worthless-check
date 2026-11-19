"""Charcoal and teal-blue palette for the desktop windows and controls."""
from tkinter import ttk

BACKGROUND = '#212121'
PANEL = '#3b3f41'
BORDER = '#606467'
TEXT = '#f5f7f8'
MUTED = '#c3d2d9'
BLUE = '#327a9e'
HEADER = '#3d87ab'
ACCENT = '#8ed7f5'
BUTTON = '#4a5053'
WARNING = '#ffcb70'


def apply(root):
    root.configure(background=BACKGROUND)
    for widget in ('Toplevel', 'Frame', 'Text', 'Listbox', 'Menu'):
        root.option_add(f'*{widget}.background', BACKGROUND)
    for widget in ('Text', 'Listbox', 'Menu'):
        root.option_add(f'*{widget}.foreground', TEXT)
        root.option_add(f'*{widget}.selectBackground', BLUE)
        root.option_add(f'*{widget}.selectForeground', 'white')
    root.option_add('*Text.insertBackground', TEXT)
    root.option_add('*Menu.activeBackground', BLUE)
    root.option_add('*Menu.activeForeground', 'white')

    style = ttk.Style(root)
    style.theme_use('clam')
    style.configure('.', background=PANEL, foreground=TEXT, bordercolor=BORDER,
                    lightcolor=PANEL, darkcolor=PANEL, troughcolor=BACKGROUND,
                    arrowcolor=MUTED, selectbackground=BLUE, selectforeground='white',
                    insertcolor=TEXT)
    style.map('.', foreground=[('disabled', '#a3abad')])
    style.configure('Office.TLabel', background=HEADER, foreground='white')
    style.configure('Shortcut.TLabel', background='#26363d', foreground=ACCENT)
    for name in ('TEntry', 'TCombobox', 'TSpinbox'):
        style.configure(name, fieldbackground=BACKGROUND)
        style.map(name, fieldbackground=[('readonly', BACKGROUND), ('disabled', PANEL)])
    style.configure('TButton', background=BUTTON, padding=(10, 5))
    style.map('TButton', background=[('disabled', PANEL), ('active', '#5c6569')])
    style.configure('Primary.TButton', background=BLUE, foreground='white')
    style.map('Primary.TButton', background=[('disabled', PANEL), ('active', '#3880a4')])
    style.configure('TNotebook', background=BACKGROUND)
    style.configure('TNotebook.Tab', padding=(12, 6), foreground=MUTED)
    style.map('TNotebook.Tab', background=[('selected', BLUE), ('active', BUTTON)],
              foreground=[('disabled', '#a3abad'), ('selected', 'white')])
    style.configure('Treeview', background=PANEL, fieldbackground=PANEL, rowheight=29)
    style.map('Treeview', background=[('selected', BLUE)], foreground=[('selected', 'white')])
    style.configure('Treeview.Heading', background=BUTTON, foreground=TEXT)
    style.map('Treeview.Heading', background=[('active', '#5c6569')])
