"""Snapshot regression: include new core helpers and no private audio/storage."""
import tempfile
import unittest
import zipfile
from pathlib import Path

from apollo_runtime import ApolloRuntime


class RecoverySnapshotTests(unittest.TestCase):
    def test_snapshot_includes_code_but_excludes_private_runtime_data(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / "main.py").write_text("print('hello')", encoding="utf-8")
            (root / "apollo_sidebar.py").write_text("# UI state", encoding="utf-8")
            (root / "apollo_personality.py").write_text("# tone", encoding="utf-8")
            (root / "Audio").mkdir()
            (root / "Audio" / "private.wav").write_bytes(b"DO NOT BACK UP")
            (root / "modules" / "example").mkdir(parents=True)
            (root / "modules" / "example" / "module.py").write_text("# hi")
            (root / "pending_modules" / "candidate").mkdir(parents=True)
            (root / "pending_modules" / "candidate" / "module.py").write_text("# candidate")
            runtime = ApolloRuntime(root)
            try:
                (root / "storage" / "private.txt").write_text("PRIVATE")
                path = Path(runtime.create_snapshot("test"))
                with zipfile.ZipFile(path) as zf:
                    names = set(zf.namelist())
                self.assertIn("main.py", names)
                self.assertIn("apollo_sidebar.py", names)
                self.assertIn("apollo_personality.py", names)
                self.assertIn("modules/example/module.py", names)
                self.assertIn("pending_modules/candidate/module.py", names)
                self.assertNotIn("storage/private.txt", names)
                self.assertNotIn("Audio/private.wav", names)
            finally:
                runtime.mark_clean_shutdown()


if __name__ == "__main__":
    unittest.main()
