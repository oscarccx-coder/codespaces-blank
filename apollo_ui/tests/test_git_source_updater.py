"""Offline tests for Apollo's guarded Git source updater."""
from __future__ import annotations

from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

from apollo_git_source_update import protected, run_update


@unittest.skipUnless(shutil.which("git"), "Git CLI required")
class SourceUpdateTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="Apollo update fixtures (spaces) ")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.remote = self.root / "origin.git"
        self.author = self.root / "author"
        self.install = self.root / "Apollo clone (working)"
        self.git(None, "init", "--bare", "--initial-branch=main", str(self.remote))
        self.git(None, "clone", str(self.remote), str(self.author))
        (self.author / "apollo_ui" / "storage" / "databases").mkdir(parents=True)
        (self.author / "apollo_ui" / "storage" / "databases" / "apollo_memory.db").write_bytes(b"initial")
        (self.author / "apollo_ui" / "module.py").write_text("version = 1\n")
        self.git(self.author, "add", ".")
        self.git(self.author, "-c", "user.name=Apollo Tests", "-c",
                 "user.email=test@example.invalid", "commit", "-m", "initial")
        self.git(self.author, "push", "origin", "main")
        self.git(None, "clone", str(self.remote), str(self.install))

    def git(self, at, *args):
        return subprocess.run(["git", *(['-C', str(at)] if at else []), *args],
                              capture_output=True, text=True, check=True)

    def remote_edit(self, relative, data):
        path = self.author / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(data)
        self.git(self.author, "add", ".")
        self.git(self.author, "-c", "user.name=Apollo Tests", "-c",
                 "user.email=test@example.invalid", "commit", "-m", "remote update")
        self.git(self.author, "push", "origin", "main")

    def update(self, check=False):
        messages = []
        code = run_update(self.install, check_only=check, emit=messages.append)
        return code, "\n".join(messages)

    def test_runtime_data_can_be_dirty_without_blocking_code_update(self):
        private = self.install / "apollo_ui/storage/databases/apollo_memory.db"
        private.write_bytes(b"PRIVATE DATA - DO NOT DISCARD")
        self.remote_edit("apollo_ui/module.py", "version = 2\n")
        code, trace = self.update()
        self.assertEqual(code, 0, trace)
        self.assertIn("[UPDATED]", trace)
        self.assertEqual(private.read_bytes(), b"PRIVATE DATA - DO NOT DISCARD")
        self.assertEqual((self.install / "apollo_ui/module.py").read_text(), "version = 2\n")

    def test_read_only_check(self):
        self.remote_edit("apollo_ui/module.py", "version = 2\n")
        code, trace = self.update(check=True)
        self.assertEqual(code, 0, trace)
        self.assertIn("[CHECK]", trace)
        self.assertEqual((self.install / "apollo_ui/module.py").read_text(), "version = 1\n")

    def test_dirty_code_blocks_update(self):
        (self.install / "apollo_ui/module.py").write_text("local edit\n")
        self.remote_edit("apollo_ui/module.py", "version = 2\n")
        code, trace = self.update()
        self.assertEqual(code, 2, trace)
        self.assertIn("[STOPPED]", trace)
        self.assertEqual((self.install / "apollo_ui/module.py").read_text(), "local edit\n")

    def test_remote_data_update_blocks_without_merging(self):
        private = self.install / "apollo_ui/storage/databases/apollo_memory.db"
        private.write_bytes(b"LOCAL PRIVATE DATA")
        self.remote_edit("apollo_ui/storage/databases/apollo_memory.db", "REMOTE CONTENT")
        code, trace = self.update()
        self.assertEqual(code, 3, trace)
        self.assertIn("[PRIVATE]", trace)
        self.assertEqual(private.read_bytes(), b"LOCAL PRIVATE DATA")

    def test_untracked_private_data_is_preserved(self):
        new = self.install / "apollo_ui/storage/database-new.sqlite"
        new.write_text("owner data")
        self.remote_edit("apollo_ui/module.py", "version = 2\n")
        code, trace = self.update()
        self.assertEqual(code, 0, trace)
        self.assertEqual(new.read_text(), "owner data")

    def test_untracked_code_is_refused(self):
        new = self.install / "apollo_ui/research.py"
        new.write_text("user code")
        code, trace = self.update()
        self.assertEqual(code, 2, trace)
        self.assertEqual(new.read_text(), "user code")

    def test_up_to_date_does_not_claim_updated(self):
        code, trace = self.update()
        self.assertEqual(code, 0, trace)
        self.assertIn("[UP-TO-DATE]", trace)
        self.assertNotIn("[UPDATED]", trace)

    def test_feature_branch_is_refused(self):
        self.git(self.install, "checkout", "-b", "feature")
        code, trace = self.update()
        self.assertEqual(code, 1, trace)
        self.assertIn("not main", trace)

    def test_protected_paths(self):
        self.assertTrue(protected("apollo_ui/storage/databases/foo.db"))
        self.assertTrue(protected("apollo_ui/Audio/output.wav"))
        self.assertTrue(protected("apollo_ui/config.local.json"))
        self.assertFalse(protected("apollo_ui/main.py"))
        self.assertFalse(protected("apollo_ui/modules/update_manager/module.py"))


if __name__ == "__main__":
    unittest.main()
