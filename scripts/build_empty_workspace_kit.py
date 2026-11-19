"""Build a new isolated kit from schema/reference data, never an office database."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import sqlite3
import sys
import zipfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'source'))
from app import Store

EMPTY_TABLES = ('cases', 'payments', 'defendants', 'merchants', 'staff_users',
                'credentials', 'audit', 'working_legacy', 'office_settings',
                'legacy_reconciliations', 'legacy_test_payments', 'legacy_changes')


def sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest().upper()


def create_baseline(path):
    path = Path(path)
    if path.exists():
        raise FileExistsError('Refusing to replace an existing database.')
    store = Store(path)
    store.db.close()
    with sqlite3.connect(path) as db:
        if db.execute('PRAGMA journal_mode=DELETE').fetchone()[0] != 'delete':
            raise ValueError('Could not make a standalone baseline.')
    db.close()
    # A plain mode=ro open of a WAL database can create sidecars. Immutable
    # validation and DELETE mode keep the release baseline self-contained.
    db = sqlite3.connect(path.resolve().as_uri() + '?mode=ro&immutable=1', uri=True)
    try:
        if db.execute('PRAGMA integrity_check').fetchone()[0] != 'ok':
            raise ValueError('Empty baseline integrity check failed.')
        counts = {name: db.execute('SELECT COUNT(*) FROM "' + name + '"').fetchone()[0]
                  for name in EMPTY_TABLES}
        if any(counts.values()):
            raise ValueError('Baseline contains business or user data.')
    finally:
        db.close()
    for suffix in ('-wal', '-shm', '-journal'):
        if Path(str(path) + suffix).exists():
            raise ValueError('Unexpected baseline sidecar: ' + suffix)
    return {'Build': '1.0.0-rc64', 'Packaging': 'v2', 'SHA256': sha256(path),
            'EmptyTableCounts': counts,
            'ReferenceData': 'Bundled bank, WC and ZIP reference lists remain.'}


def build_kit(installer, output):
    installer, output = Path(installer).resolve(), Path(output).resolve()
    if not installer.is_file():
        raise FileNotFoundError(installer)
    # Never merge with an old extraction containing sidecars or user records.
    output.mkdir(parents=True, exist_ok=False)
    baseline = output / 'Empty-rc64.sqlite'
    evidence = create_baseline(baseline)
    installer_name = 'Check-Management-Setup-rc64.exe'
    shutil.copy2(installer, output / installer_name)
    evidence['InstallerSHA256'] = sha256(installer)
    template = (ROOT / 'scripts/Start-rc64-Empty-Workspace.ps1').read_text(encoding='utf-8-sig')
    launcher = template.replace('__EMPTY_SHA256__', evidence['SHA256']).replace(
        '__INSTALLER_SHA256__', evidence['InstallerSHA256'])
    (output / 'Start-rc64-Empty-Workspace.ps1').write_text(launcher, encoding='utf-8-sig')
    (output / 'Empty-Workspace-Verification.json').write_text(json.dumps(evidence, indent=2))
    shutil.copy2(ROOT / 'docs/empty-workspace.md', output / 'README-Empty-Workspace.md')
    allowed = ('Empty-rc64.sqlite', installer_name, 'Start-rc64-Empty-Workspace.ps1',
               'Empty-Workspace-Verification.json', 'README-Empty-Workspace.md')
    archive = output / 'Check-Management-rc64-Empty-Workspace-v2.zip'
    with zipfile.ZipFile(archive, 'w', zipfile.ZIP_DEFLATED) as bundle:
        for name in allowed:
            bundle.write(output / name, name)
    with zipfile.ZipFile(archive) as bundle:
        if set(bundle.namelist()) != set(allowed) or bundle.testzip() is not None:
            raise ValueError('Kit verification failed.')
    return archive


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--installer', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    print(build_kit(args.installer, args.output))
