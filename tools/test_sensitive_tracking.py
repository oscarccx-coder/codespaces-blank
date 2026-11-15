import pathlib
import subprocess
import tempfile
import unittest
from check_sensitive_tracking import check, sensitive

class TrackingTests(unittest.TestCase):
    def test_nested_paths_and_future_ledger(self):
        for path in ('apollo_ui/storage/databases/apollo_missions.db', 'apollo_ui/modules/task_engine/storage/task_engine.db', 'voice/recordings/a.wav', 'x/.env.local', 'x/signing.pem'):
            self.assertTrue(sensitive(path), path)
        self.assertFalse(sensitive('apollo_ui/apollo_learning_missions.py'))

    def test_force_added_data_and_indexed_secret_are_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            root = pathlib.Path(temp)
            def git(*args): subprocess.run(['git', '-C', temp, *args], check=True, capture_output=True)
            git('init')
            (root / '.gitignore').write_text('storage/\n')
            (root / 'storage').mkdir(); (root / 'storage/state.db').write_bytes(b'fixture')
            git('add', '-f', 'storage/state.db')
            self.assertEqual(check(root), [('storage/state.db', 'sensitive-path')])
            # Synthetic token assembled in memory; no real credential used.
            (root / 'config.json').write_text('{"auth_token":"' + 'Q' * 43 + '"}')
            git('add', 'config.json')
            (root / 'config.json').write_text('{}')
            self.assertIn(('config.json', 'device-auth-token'), check(root, secrets=True))

if __name__ == '__main__': unittest.main()
