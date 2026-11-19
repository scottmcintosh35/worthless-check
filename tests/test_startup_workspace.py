"""Fresh shortcut startup must isolate personal data and preserve shared access checks."""
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'source'))
from app import Store
import deployment
import divisions
import document_mode

class StartupWorkspaceTests(unittest.TestCase):
    def test_fresh_personal_no_group_check_and_preserved_on_reopen(self):
        with tempfile.TemporaryDirectory() as tmp:
            with patch.dict(os.environ, {'LOCALAPPDATA': tmp}), patch('divisions.allowed_divisions', side_effect=AssertionError('personal startup queried server groups')):
                path, division, allowed = deployment.resolve_workspace()
                self.assertEqual(path, Path(tmp) / 'WorthlessCheck' / 'Data' / 'wc.sqlite')
                self.assertIsNone(division)
                self.assertEqual(allowed, ())
                self.assertFalse(path.exists())
                path.parent.mkdir(parents=True)
                store = Store(path)
                for table in ('staff_users', 'cases', 'payments', 'working_legacy', 'office_settings'):
                    self.assertEqual(store.db.execute('SELECT COUNT(*) FROM ' + table).fetchone()[0], 0, table)
                store.db.execute("INSERT INTO office_settings VALUES (1, ?)", ('{"ORGANIZATION":"My Custom Organization"}',))
                store.db.commit()
                store.db.close()
                again, _, _ = deployment.resolve_workspace()
                self.assertEqual(again, path)
                reopened = Store(again)
                self.assertIn('My Custom Organization', reopened.db.execute('SELECT data FROM office_settings').fetchone()[0])
                reopened.db.close()

    def test_explicit_shared_division_still_checks_membership(self):
        with patch('divisions.allowed_divisions', return_value=()):
            with self.assertRaisesRegex(ValueError, 'Windows group access'):
                deployment.resolve_workspace(division='office1')
        with patch('divisions.allowed_divisions', return_value=('office1',)):
            path, division, allowed = deployment.resolve_workspace(division='office1')
            self.assertEqual(path, divisions.data_path('office1').resolve())
            self.assertEqual(division, 'office1')
            self.assertEqual(allowed, ('office1',))

    def test_exact_shared_data_path_cannot_bypass_membership(self):
        for key in divisions.LABELS:
            with patch('divisions.allowed_divisions', return_value=()):
                with self.assertRaisesRegex(ValueError, 'Windows group access'):
                    deployment.resolve_workspace(divisions.data_path(key))

    def test_official_output_cannot_silently_open_personal_data(self):
        with self.assertRaisesRegex(ValueError, 'explicitly selected'):
            deployment.resolve_workspace(output_mode=document_mode.OFFICIAL)

    def test_installer_does_not_provision_shared_access(self):
        text = (Path(__file__).resolve().parents[1] / 'source' / 'installer.iss').read_text()
        self.assertNotIn('ProtectDivision', text)
        self.assertNotIn('EnsureGroup', text)
        self.assertNotIn('[Dirs]', text)
        self.assertIn('Worthless Check', text)

if __name__ == '__main__':
    unittest.main()
