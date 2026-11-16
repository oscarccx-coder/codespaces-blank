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


    def test_future_ledger_is_ignored_and_force_add_is_rejected(self):
        # The real repo ignore policy must protect the planned Claude
        # Mission Director database, not just pass an in-memory path rule.
        repository = pathlib.Path(__file__).resolve().parents[1]
        ignore = (repository / '.gitignore').read_text(encoding='utf-8')
        ledger = 'apollo_ui/storage/databases/apollo_missions.db'
        with tempfile.TemporaryDirectory() as temp:
            root = pathlib.Path(temp)
            def git(*args):
                return subprocess.run(
                    ['git', '-C', temp, *args],
                    check=True, capture_output=True, text=True,
                )
            git('init')
            (root / '.gitignore').write_text(ignore, encoding='utf-8')
            target = root / ledger
            target.parent.mkdir(parents=True)
            target.write_bytes(b'private fixture only')
            git('check-ignore', '-q', ledger)
            self.assertEqual(git('ls-files', '--', ledger).stdout.strip(), '')
            git('add', '-f', ledger)
            self.assertIn((ledger, 'sensitive-path'), check(root))

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
