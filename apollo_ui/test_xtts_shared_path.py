"""XTTS folder discovery and saved-path regression tests, no model download."""
import tempfile
import unittest
from pathlib import Path

from apollo_xtts_paths import (
    XTTS_FILES, bundled_xtts_folder, shared_xtts_folder, chosen_xtts_folder,
    save_xtts_folder, pointer_path, valid_xtts_folder,
)


def complete(folder):
    folder.mkdir(parents=True)
    for name in XTTS_FILES:
        (folder / name).write_bytes(b"test fixture")


class XTTSFolderTests(unittest.TestCase):
    def test_auto_detect_drop_in_model(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            drop_in = bundled_xtts_folder(root)
            self.assertFalse(valid_xtts_folder(drop_in))
            self.assertEqual(chosen_xtts_folder(root), shared_xtts_folder(root))
            complete(drop_in)
            self.assertTrue(valid_xtts_folder(drop_in))
            self.assertEqual(chosen_xtts_folder(root), drop_in.resolve())

    def test_explicit_saved_path_wins_and_persists(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            complete(bundled_xtts_folder(root))
            alternative = root / "external" / "xtts_v2"
            complete(alternative)
            self.assertEqual(save_xtts_folder(root, alternative), str(alternative.resolve()))
            self.assertTrue(pointer_path(root).exists())
            self.assertEqual(chosen_xtts_folder(root), alternative.resolve())
            self.assertNotIn("model.pth", pointer_path(root).read_text(encoding="utf-8"))

    def test_reject_partial_model(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            folder = root / "missing"
            folder.mkdir()
            (folder / "config.json").write_text("{}")
            with self.assertRaises(ValueError):
                save_xtts_folder(root, folder)
            self.assertFalse(pointer_path(root).exists())

    def test_legacy_existing_model_preserved(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            legacy = root / "old" / "xtts_v2"
            complete(legacy)
            self.assertEqual(chosen_xtts_folder(root, legacy), legacy.resolve())


if __name__ == "__main__":
    unittest.main()
