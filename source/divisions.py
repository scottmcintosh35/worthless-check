"""Windows access and local storage for the two DA divisions."""
import ctypes
from ctypes import wintypes
import os
from pathlib import Path

LABELS = {'troy': 'Office 1', 'enterprise': 'Office 2'}
GROUPS = {'troy': 'PikeCountyWCUsers', 'enterprise': 'EnterpriseWCUsers'}
DIRECTORIES = {'troy': 'Data', 'enterprise': 'EnterpriseData'}


def data_path(division):
    return (Path(os.environ.get('PROGRAMDATA', r'C:\ProgramData')) /
            'PikeCountyWC-ServerEvaluation' / DIRECTORIES[division] / 'wc.sqlite')


def database_division(db):
    path = Path(db.execute('PRAGMA database_list').fetchone()[2])
    if path.parent.name.casefold() == DIRECTORIES['enterprise'].casefold():
        return 'enterprise'
    return 'troy'


def is_windows_admin():
    return bool(ctypes.windll.shell32.IsUserAnAdmin())


def in_local_group(group):
    windows = ctypes.WinDLL('advapi32', use_last_error=True)
    computer = ctypes.create_unicode_buffer(256)
    size = wintypes.DWORD(len(computer))
    if not ctypes.windll.kernel32.GetComputerNameW(computer, ctypes.byref(size)):
        raise ctypes.WinError()
    account = computer.value + chr(92) + group
    sid_size, domain_size, use = wintypes.DWORD(), wintypes.DWORD(), wintypes.DWORD()
    windows.LookupAccountNameW(None, account, None, ctypes.byref(sid_size),
                               None, ctypes.byref(domain_size), ctypes.byref(use))
    if ctypes.get_last_error() == 1332:  # ERROR_NONE_MAPPED
        return False
    if not sid_size.value:
        raise ctypes.WinError(ctypes.get_last_error())
    sid = ctypes.create_string_buffer(sid_size.value)
    domain = ctypes.create_unicode_buffer(domain_size.value)
    if not windows.LookupAccountNameW(None, account, sid, ctypes.byref(sid_size),
                                      domain, ctypes.byref(domain_size), ctypes.byref(use)):
        raise ctypes.WinError(ctypes.get_last_error())
    member = wintypes.BOOL()
    if not windows.CheckTokenMembership(None, sid, ctypes.byref(member)):
        raise ctypes.WinError(ctypes.get_last_error())
    return bool(member.value)


def allowed_divisions():
    if is_windows_admin():
        return tuple(LABELS)
    return tuple(division for division, group in GROUPS.items() if in_local_group(group))
