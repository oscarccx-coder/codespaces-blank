"""Foundry local preview preparation: no generated code is executed by tests."""
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from apollo_foundry_preview import prepare_local_preview
from tests.test_foundry_phase1 import GOOD_UI, GOOD_BACKEND, CONTRACT


class PreviewPreparationTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.folder = Path(self.tmp.name)
        (self.folder / "ui.py").write_text(GOOD_UI, encoding="utf-8")
        (self.folder / "service.py").write_text(GOOD_BACKEND, encoding="utf-8")
        (self.folder / "foundry.json").write_text(
            json.dumps(CONTRACT), encoding="utf-8"
        )

    def test_requires_real_launcher(self):
        with self.assertRaisesRegex(ValueError, "launch.py"):
            prepare_local_preview(self.folder)

    def test_validates_static_ui_before_offering_local_execution(self):
        launcher = self.folder / "launch.py"
        launcher.write_text("print('never executed by this test')\n", encoding="utf-8")
        self.assertEqual(prepare_local_preview(self.folder), launcher)
        (self.folder / "service.py").write_text("def bad(:\n", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "Static checks"):
            prepare_local_preview(self.folder)

    def test_rejects_symlink_launcher(self):
        target = self.folder / "real.py"
        target.write_text("pass\n", encoding="utf-8")
        try:
            (self.folder / "launch.py").symlink_to(target)
        except (OSError, NotImplementedError):
            self.skipTest("Symlinks not available")
        with self.assertRaisesRegex(ValueError, "regular"):
            prepare_local_preview(self.folder)

    def test_preparation_does_not_start_a_process(self):
        (self.folder / "launch.py").write_text("raise RuntimeError('must not run')\n")
        with patch("subprocess.Popen", side_effect=AssertionError("executed")):
            self.assertEqual(
                prepare_local_preview(self.folder), self.folder / "launch.py"
            )


if __name__ == "__main__":
    unittest.main()
