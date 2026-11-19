"""Prevent release-kit sidecars and accidental reuse of populated workspaces."""
import importlib.util
from pathlib import Path
import sqlite3
import tempfile
import unittest
import zipfile

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('kit_builder', ROOT / 'scripts/build_empty_workspace_kit.py')
builder = importlib.util.module_from_spec(spec)
spec.loader.exec_module(builder)


class EmptyWorkspaceTests(unittest.TestCase):
    def test_standalone_baseline_and_preserve_existing(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / 'empty.sqlite'
            result = builder.create_baseline(target)
            self.assertFalse(any(result['EmptyTableCounts'].values()))
            before = target.read_bytes()
            with self.assertRaises(FileExistsError):
                builder.create_baseline(target)
            self.assertEqual(before, target.read_bytes())
            db = sqlite3.connect(target.as_uri() + '?mode=ro&immutable=1', uri=True)
            try:
                self.assertEqual(db.execute('PRAGMA journal_mode').fetchone()[0], 'delete')
            finally:
                db.close()
            self.assertFalse(any(Path(str(target) + suffix).exists()
                                 for suffix in ('-wal', '-shm', '-journal')))

    def test_package_allowlist_and_hashes(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            installer = tmp / 'fixture.exe'
            installer.write_bytes(b'Fictional packaging fixture; never executed')
            archive = builder.build_kit(installer, tmp / 'new-kit')
            with zipfile.ZipFile(archive) as bundle:
                self.assertEqual(len(bundle.namelist()), 5)
                self.assertFalse(any(n.endswith(('-wal', '-shm', '-journal'))
                                     for n in bundle.namelist()))
                launcher = bundle.read('Start-rc64-Empty-Workspace.ps1').decode('utf-8-sig')
                self.assertNotIn('__EMPTY_SHA256__', launcher)
                self.assertNotIn('__INSTALLER_SHA256__', launcher)
                self.assertIn(builder.sha256(installer), launcher)
            with self.assertRaises(FileExistsError):
                builder.build_kit(installer, tmp / 'new-kit')


if __name__ == '__main__':
    unittest.main()
