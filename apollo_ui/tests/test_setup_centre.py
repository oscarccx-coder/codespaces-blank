"""Offline setup, safe backup and XTTS diagnostic regressions."""
from pathlib import Path
import ast
import json
import sqlite3
import tempfile
import unittest
import zipfile

from apollo_backup import make_backup, inspect_backup, restore_backup
from apollo_setup_core import read_profile, save_profile, xtts_diagnostic


ROOT = Path(__file__).resolve().parents[1]


class ApolloSetupTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name) / "apollo"
        self.root.mkdir()

    def test_device_profile_round_trip_with_validation(self):
        self.assertEqual(read_profile(self.root), "desktop")
        self.assertEqual(save_profile(self.root, "pi")["profile"], "pi")
        self.assertEqual(read_profile(self.root), "pi")
        with self.assertRaises(ValueError):
            save_profile(self.root, "supercomputer")

    def _seed(self):
        voice = self.root / "storage/media/voice_imprint/profiles/apollo/profile.json"
        voice.parent.mkdir(parents=True)
        voice.write_text('{"name":"Apollo"}', encoding="utf-8")
        project = self.root / "workspace/Example/design.py"
        project.parent.mkdir(parents=True)
        project.write_text("print('original')\n", encoding="utf-8")
        database = self.root / "storage/databases/memory.db"
        database.parent.mkdir(parents=True)
        with sqlite3.connect(database) as conn:
            conn.execute("CREATE TABLE fact (text TEXT)")
            conn.execute("INSERT INTO fact VALUES ('keep me')")
        model = self.root / "storage/models/voice/xtts_v2/model.pth"
        model.parent.mkdir(parents=True)
        model.write_bytes(b"pretend 4GB model")
        return voice, project, database, model

    def test_backup_round_trip_and_model_exclusion(self):
        voice, project, database, model = self._seed()
        target = self.root / "storage/backups/exports/test.zip"
        made = make_backup(self.root, target)
        self.assertGreaterEqual(made["files"], 3)
        preview = inspect_backup(target)
        self.assertFalse(any("model.pth" in item["path"] for item in preview["entries"]))
        voice.write_text("changed", encoding="utf-8")
        project.write_text("changed", encoding="utf-8")
        with self.assertRaises(PermissionError):
            restore_backup(self.root, target)
        result = restore_backup(self.root, target, confirmed=True)
        self.assertEqual(result["restored"], made["files"])
        self.assertEqual(voice.read_text(), '{"name":"Apollo"}')
        self.assertEqual(project.read_text(), "print('original')\n")
        self.assertTrue(model.exists())
        with sqlite3.connect(database) as conn:
            self.assertEqual(conn.execute("SELECT text FROM fact").fetchone()[0], "keep me")

    def test_corrupt_checksum_rejected_before_live_writes(self):
        voice, project, _, _ = self._seed()
        target = self.root / "safe.zip"
        make_backup(self.root, target)
        corrupt = self.root / "tampered.zip"
        with zipfile.ZipFile(target) as original, zipfile.ZipFile(corrupt, "w") as output:
            for item in original.namelist():
                data = original.read(item)
                if item.endswith("profile.json"):
                    data = b"tampered"
                output.writestr(item, data)
        original_content = voice.read_bytes()
        with self.assertRaises(ValueError):
            restore_backup(self.root, corrupt, confirmed=True)
        self.assertEqual(voice.read_bytes(), original_content)

    def test_path_traversal_rejected(self):
        zip_path = self.root / "unsafe.zip"
        with zipfile.ZipFile(zip_path, "w") as output:
            output.writestr("files/storage/state/../../escape.txt", "danger")
            output.writestr("manifest.json", json.dumps({
                "product": "Apollo", "format": 1,
                "entries": [{"path": "storage/state/../../escape.txt",
                             "bytes": 6, "sha256": "0"*64}]
            }))
        with self.assertRaises(ValueError):
            inspect_backup(zip_path)

    def test_xtts_diagnostics_report_missing_model_instead_of_hanging(self):
        report = xtts_diagnostic(self.root, deep=False)
        self.assertFalse(report["ok"])
        self.assertIn("model.pth", report["missing_model_files"])
        self.assertEqual(report["deep_import"], "skipped")

    def test_setup_scripts_route_to_compatibility_entrypoints(self):
        setup = ROOT / "Setup"
        for name in (
            "01_INSTALL_APOLLO.bat", "02_START_APOLLO.bat",
            "03_UPDATE_APOLLO.bat", "04_REPAIR_VOICE.bat",
            "05_DIAGNOSE.bat", "06_BACKUP.bat",
            "07_RESTORE_BACKUP.bat", "08_UNINSTALL_REQUIREMENTS.bat",
            "09_START_SAFE_MODE.bat", "10_SETUP_WIZARD.bat",
        ):
            self.assertTrue((setup / name).is_file(), name)
            self.assertIn("%~dp0", (setup / name).read_text(encoding="utf-8"))
        self.assertIn("create_shortcuts.ps1", (setup / "01_INSTALL_APOLLO.bat").read_text())

    def test_qt_ui_files_are_python_syntax_valid(self):
        for path in ("apollo_setup_ui.py", "apollo_setup.py", "apollo_setup_core.py",
                     "apollo_backup.py", "main.py"):
            file = ROOT / path
            ast.parse(file.read_text(encoding="utf-8"), filename=str(file))


if __name__ == "__main__":
    unittest.main()
