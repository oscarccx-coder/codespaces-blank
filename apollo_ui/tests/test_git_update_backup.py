"""Offline verified Git-update backup and recovery tests.

All files are disposable. Nothing connects to GitHub or touches Apollo data.
"""
from __future__ import annotations

import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

from apollo_git_backup import preview_backup, snapshot, restore_missing


@unittest.skipUnless(shutil.which("git"), "Git CLI required")
class UpdateBackupTests(unittest.TestCase):
    def setUp(self):
        from tests.test_git_source_updater import SourceUpdateTests
        self.fixture = SourceUpdateTests("test_up_to_date_does_not_claim_updated")
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.root = self.fixture.install
        self.backups = self.fixture.root / "External private backups"
        self.private = self.root / "apollo_ui" / "storage" / "databases" / "apollo_memory.db"

    def test_preview_is_read_only_and_outside_git(self):
        plan = preview_backup(self.root, self.backups)
        self.assertGreater(plan["private_files"], 0)
        self.assertEqual(plan["backup_parent"], str(self.backups.resolve()))
        self.assertFalse(self.backups.exists())

    def test_snapshot_verifies_files_and_restore_never_overwrites(self):
        self.private.write_bytes(b"MY CURRENT DATA")
        secret = self.root / "apollo_ui" / "key.pem"
        secret.write_bytes(b"PRIVATE SIGNING KEY")
        outcome = snapshot(self.root, self.backups, emit=lambda _: None)
        dest = Path(outcome["path"])
        manifest = json.loads((dest / "apollo-backup-manifest.json").read_text())
        self.assertIn("apollo_ui/key.pem", manifest["private_files"])
        self.assertEqual((dest / "files" / "apollo_ui" / "key.pem").read_bytes(),
                         b"PRIVATE SIGNING KEY")
        self.assertEqual((dest / "files" / "apollo_ui" / "storage" / "databases" /
                          "apollo_memory.db").read_bytes(), b"MY CURRENT DATA")
        self.assertFalse((self.root / "apollo-backup-manifest.json").exists())

        self.private.write_bytes(b"NEW LIVE DATA")
        initial = restore_missing(self.root, dest, emit=lambda _: None)
        self.assertEqual(initial["restored"], 0)
        self.assertEqual(self.private.read_bytes(), b"NEW LIVE DATA")

        self.private.unlink()
        secret.unlink()
        recovered = restore_missing(self.root, dest, emit=lambda _: None)
        self.assertEqual(recovered["restored"], 2)
        self.assertEqual(self.private.read_bytes(), b"MY CURRENT DATA")
        self.assertEqual(secret.read_bytes(), b"PRIVATE SIGNING KEY")
        self.assertEqual(restore_missing(self.root, dest, emit=lambda _: None)["restored"], 0)

    def test_quarantine_only_known_untracked_recovery_files(self):
        old = self.root / "apollo_ui" / "Setup"
        old.mkdir(exist_ok=True)
        known = old / "RUN_APOLLO_UPDATER_RECOVERY.bat"
        known.write_bytes(b"@echo off\nlegacy")
        duplicate = old / "apollo_git_source_update.py"
        duplicate.write_text("legacy helper")
        other = old / "MY_OWN_REPAIR.bat"
        other.write_text("@echo off\nkeep me")
        plan = preview_backup(self.root, self.backups)
        self.assertEqual(len(plan["recovery_files"]), 2)
        outcome = snapshot(self.root, self.backups,
                           relocate_recovery=True, emit=lambda _: None)
        dest = Path(outcome["path"])
        self.assertFalse(known.exists())
        self.assertFalse(duplicate.exists())
        self.assertTrue(other.is_file())
        self.assertEqual(
            (dest / "relocated" / "apollo_ui" / "Setup" /
             "RUN_APOLLO_UPDATER_RECOVERY.bat").read_bytes(), b"@echo off\nlegacy")
        self.assertEqual(restore_missing(self.root, dest, emit=lambda _: None)["restored"], 0)
        self.assertFalse(known.exists(), "Quarantined obsolete helpers must not reappear")

    def test_fails_closed_on_corrupt_private_backup(self):
        dest = Path(snapshot(self.root, self.backups, emit=lambda _: None)["path"])
        self.private.unlink()
        (dest / "files" / "apollo_ui" / "storage" / "databases" /
         "apollo_memory.db").write_bytes(b"corrupt")
        with self.assertRaisesRegex(RuntimeError, "SHA256"):
            restore_missing(self.root, dest, emit=lambda _: None)
        self.assertFalse(self.private.exists())

    def test_rejects_backup_directory_inside_repository(self):
        with self.assertRaises(ValueError):
            preview_backup(self.root, self.root / "backup")
        with self.assertRaises(ValueError):
            snapshot(self.root, self.root / "backup", emit=lambda _: None)

    def test_automatic_update_archive_then_restore_missing(self):
        from apollo_git_source_update import run_update
        old = self.root / "apollo_ui" / "Setup"
        old.mkdir(exist_ok=True)
        helper = old / "apollo_git_source_update.py"
        helper.write_text("untracked old copy")
        original = self.private.read_bytes()
        self.fixture.remote_edit("apollo_ui/module.py", "version = 2\n")
        messages = []
        code = run_update(self.root, backup_parent=self.backups,
                          repair_recovery=True, emit=messages.append)
        self.assertEqual(code, 0, "\n".join(messages))
        self.assertFalse(helper.exists())
        self.assertEqual(self.private.read_bytes(), original)
        self.assertIn("[BACKUP VERIFIED]", "\n".join(messages))
        self.assertIn("[RESTORE CHECK]", "\n".join(messages))
        self.assertEqual((self.root / "apollo_ui/module.py").read_text(), "version = 2\n")

    def test_unrelated_user_code_blocks_even_in_repair_mode(self):
        from apollo_git_source_update import run_update
        (self.root / "apollo_ui" / "homebrew_patch.py").write_text("my patch")
        trace = []
        code = run_update(self.root, backup_parent=self.backups,
                          repair_recovery=True, emit=trace.append)
        self.assertEqual(code, 2, "\n".join(trace))
        self.assertIn("apollo_ui/homebrew_patch.py", "\n".join(trace))
        self.assertFalse(self.backups.exists())
        self.assertTrue((self.root / "apollo_ui" / "homebrew_patch.py").exists())


if __name__ == "__main__":
    unittest.main()
