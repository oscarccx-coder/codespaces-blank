"""Disposable local fixture tests; never inspect the user's Apollo installation."""
import json
from pathlib import Path
import subprocess
import tempfile
import unittest

from backup_runtime_before_merge import backup, inventory


class RuntimeCleanupBackupTests(unittest.TestCase):
    def setup_repo(self, root):
        subprocess.run(["git", "init", str(root)], check=True, capture_output=True)
        private = root / "apollo_ui/modules/task_engine/storage/task_engine.db"
        private.parent.mkdir(parents=True)
        private.write_bytes(b"PRIVATE FIXTURE ONLY")
        (root / "apollo_ui/Audio").mkdir()
        (root / "apollo_ui/Audio/sample.wav").write_bytes(b"VOICE FIXTURE")
        (root / "apollo_ui/main.py").write_text("code", encoding="utf-8")
        return private

    def test_verified_backup_includes_untracked_module_data_and_audio(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "source"
            root.mkdir()
            private = self.setup_repo(root)
            dest = Path(directory) / "verified-backup"
            report = backup(root, dest, confirmed_stopped=True)
            self.assertTrue(report["verified"])
            self.assertEqual(
                (dest / "files" / private.relative_to(root)).read_bytes(),
                b"PRIVATE FIXTURE ONLY",
            )
            self.assertEqual(len(json.loads((dest / "manifest.json").read_text())["entries"]), 2)
            self.assertFalse((dest / "INCOMPLETE-BACKUP.txt").exists())
            self.assertEqual(private.read_bytes(), b"PRIVATE FIXTURE ONLY")

    def test_requires_confirmed_shutdown_and_external_destination(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "source"
            root.mkdir()
            self.setup_repo(root)
            with self.assertRaises(PermissionError):
                backup(root, Path(directory) / "new-backup")
            with self.assertRaises(ValueError):
                backup(root, root / "storage/backups/new", confirmed_stopped=True)

    def test_private_symlink_blocks_incomplete_backup(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "source"
            root.mkdir()
            self.setup_repo(root)
            (root / "apollo_ui/storage").symlink_to(Path(directory), target_is_directory=True)
            with self.assertRaises(ValueError):
                inventory(root)


if __name__ == "__main__":
    unittest.main()
