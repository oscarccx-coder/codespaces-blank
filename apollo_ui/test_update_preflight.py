"""Fast offline checks for installer preflight; no model or GUI required."""
import hashlib
import tempfile
import unittest
from pathlib import Path

from apollo_updater import safe_relative, ensure_inside, preflight_manifest


class UpdatePreflightTests(unittest.TestCase):
    def test_rejects_traversal_and_windows_device_paths(self):
        unsafe = [
            "", "../secrets.txt", "main/../../escape", "/abs/file",
            "C:/Windows/temp", "C:relative", "\\\\server\\share",
            "storage/memory.db", "Audio/example.wav", ".git/config",
            "venv/Lib/site.py", "CON", "LPT1.log", "a//b", "foo/.", "foo/",
            "foo/hello:stream", "foo/trailing. ", "\x00evil",
        ]
        for path in unsafe:
            with self.subTest(path=path), self.assertRaises(ValueError):
                safe_relative(path)
        self.assertEqual(safe_relative("modules/example/module.py"), Path("modules/example/module.py"))

    def test_rejects_symlinks_outside_root(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder) / "install"
            other = Path(folder) / "outside"
            root.mkdir()
            other.mkdir()
            try:
                (root / "escape").symlink_to(other, target_is_directory=True)
            except (OSError, NotImplementedError):
                self.skipTest("Symlink privileges not available")
            with self.assertRaises(ValueError):
                ensure_inside(root, Path("escape") / "do_not_write.py")

    def test_preflight_verifies_all_hashes_before_writing(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            target = root / "target"
            stage = root / "stage"
            target.mkdir()
            (stage / "payload").mkdir(parents=True)
            (target / "main.py").write_text("old")
            payload = stage / "payload" / "main.py"
            payload.write_text("new")
            manifest = {"files": [{"path": "main.py", "sha256": hashlib.sha256(b"new").hexdigest()}]}
            files, removed = preflight_manifest(stage, target, manifest)
            self.assertEqual(len(files), 1)
            self.assertEqual(removed, [])
            self.assertEqual((target / "main.py").read_text(), "old")

            manifest["files"].append({"path": "broken.py", "sha256": "0" * 64})
            with self.assertRaises(ValueError):
                preflight_manifest(stage, target, manifest)
            self.assertEqual((target / "main.py").read_text(), "old")

    def test_conflicts_and_duplicates(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            target, stage = root / "target", root / "stage"
            target.mkdir()
            (stage / "payload").mkdir(parents=True)
            for name in ("main.py", "MAIN.py"):
                (stage / "payload" / name).write_text("X")
            files = [{"path": name, "sha256": hashlib.sha256(b"X").hexdigest()}
                     for name in ("main.py", "MAIN.py")]
            with self.assertRaises(ValueError):
                preflight_manifest(stage, target, {"files": files})
            with self.assertRaises(ValueError):
                preflight_manifest(stage, target, {"files": files[:1], "remove": ["main.py"]})


if __name__ == "__main__":
    unittest.main()
