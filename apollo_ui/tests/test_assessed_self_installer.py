"""Offline signed-assessment installer tests. Ephemeral keys; no live Apollo edits."""
from __future__ import annotations

import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.serialization import Encoding, PrivateFormat, NoEncryption

from apollo_assessed_update import AssessedUpdate, AssessmentFailure
from apollo_release import publish
from apollo_update import UpdateService
from apollo_updater import apply_update


class AssessedInstallerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="Apollo Assessed Installer ")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.source, self.target = self.root / "signed source", self.root / "installed Apollo"
        self.source.mkdir()
        self.target.mkdir()
        (self.source / "config.json").write_text('{"version":"3.2.0"}', encoding="utf-8")
        (self.source / "main.py").write_text("UPDATE_VALUE=2\n", encoding="utf-8")
        (self.target / "config.json").write_text(
            '{"version":"3.1.0","model":"keep-local"}', encoding="utf-8")
        (self.target / "main.py").write_text("UPDATE_VALUE=1\n", encoding="utf-8")
        (self.target / "workspace").mkdir()
        (self.target / "workspace" / "private.txt").write_text("DO-NOT-CHANGE")
        self.source_health = Path(__file__).resolve().parents[1] / "apollo_health_check.py"
        (self.source / "apollo_health_check.py").write_text(
            self.source_health.read_text(encoding="utf-8"), encoding="utf-8")
        (self.target / "apollo_health_check.py").write_text(
            self.source_health.read_text(encoding="utf-8"), encoding="utf-8")
        key = Ed25519PrivateKey.generate()
        self.private = key.private_bytes(Encoding.PEM, PrivateFormat.PKCS8, NoEncryption()).decode()
        self.service = UpdateService(self.target)
        self.release()
        self.assessor = AssessedUpdate(self.target)

    def release(self):
        with patch.dict(os.environ, {"APOLLO_RELEASE_PRIVATE_PEM": self.private}):
            output = publish(self.source, self.root / "releases", "beta")
        self.service.import_trusted_key(output["public_key"])
        self.staged = self.service.stage_local_package(output["package"])
        self.assertTrue(self.staged["ok"], self.staged)
        self.stage_path = Path(self.staged["stage_dir"])

    def assert_unchanged(self):
        self.assertEqual((self.target / "main.py").read_text(), "UPDATE_VALUE=1\n")
        self.assertEqual((self.target / "workspace" / "private.txt").read_text(), "DO-NOT-CHANGE")

    def test_assessment_has_evidence_no_install_or_model_claims(self):
        record = self.service.assess_staged_update()
        self.assertTrue(record["ok"], record)
        self.assertTrue(record["manifest_sha256"])
        self.assertGreaterEqual(record["static_python_checked"], 2)
        self.assertGreater(record["estimated_core_backup_bytes"], 0)
        self.assertFalse(record["runtime_tests_executed"])
        self.assertTrue(record["manual_release_approval_required"])
        self.assertTrue(Path(record["report_path"]).exists())
        self.assert_unchanged()

    def test_signed_assessment_then_backup_install_and_health(self):
        receipt = self.assessor.assess(self.stage_path)
        self.assertTrue(receipt["ok"], receipt)
        health = Mock(returncode=0, stdout="health PASS", stderr="")
        with patch("apollo_updater.subprocess.run", return_value=health):
            applied = apply_update(self.target, self.stage_path, restart=False,
                                   assessed_manifest_sha256=receipt["manifest_sha256"])
        self.assertTrue(applied["ok"], applied)
        self.assertTrue((Path(applied["backup"]) / "config.json").is_file())
        self.assertEqual((Path(applied["backup"]) / "files" / "main.py").read_text(), "UPDATE_VALUE=1\n")
        self.assertEqual((self.target / "main.py").read_text(), "UPDATE_VALUE=2\n")
        self.assertEqual(json.loads((self.target / "config.json").read_text())["model"], "keep-local")
        self.assertEqual((self.target / "workspace" / "private.txt").read_text(), "DO-NOT-CHANGE")

    def test_external_installer_refuses_wrong_or_missing_assessment(self):
        receipt = self.assessor.assess(self.stage_path)
        self.assertTrue(receipt["ok"])
        with patch("apollo_updater.subprocess.run") as health:
            refused = apply_update(self.target, self.stage_path, restart=False,
                                   assessed_manifest_sha256="0" * 64)
            health.assert_not_called()
        self.assertFalse(refused["ok"])
        self.assertEqual(refused["stage"], "assessment")
        self.assert_unchanged()

    def test_signed_invalid_python_is_refused_before_backup_and_launch(self):
        (self.source / "main.py").write_text("def broken(:\n")
        (self.source / "config.json").write_text('{"version":"3.3.0"}')
        self.release()
        receipt = self.assessor.assess(self.stage_path)
        self.assertFalse(receipt["ok"])
        self.assertIn("Python syntax", receipt["reason"])
        (self.target / "apollo_updater.py").write_text("# subprocess stub\n")
        with patch("apollo_update.subprocess.Popen") as spawned:
            launch = self.service.launch_installer(version="3.3.0")
            spawned.assert_not_called()
        self.assertFalse(launch["ok"])
        self.assertEqual(launch["stage"], "assessment")
        self.assert_unchanged()
        self.assertFalse(list((self.target / "storage" / "backups" / "core_updates").glob("*"))
                         if (self.target / "storage" / "backups" / "core_updates").exists()
                         else True)

    def test_tamper_and_low_space_blocks_assessment(self):
        receipt = self.assessor.assess(self.stage_path)
        self.assertTrue(receipt["ok"])
        (self.stage_path / "payload" / "main.py").write_text("UPDATE_VALUE=666\n")
        self.assertFalse(self.assessor.assess(self.stage_path, save=False)["ok"])
        (self.stage_path / "payload" / "main.py").write_text("UPDATE_VALUE=2\n")
        with patch("apollo_assessed_update.shutil.disk_usage", return_value=Mock(free=0)):
            low = self.assessor.assess(self.stage_path, save=False)
        self.assertFalse(low["ok"])
        self.assertIn("disk", low["reason"])
        self.assert_unchanged()

    def test_rollback_is_still_transactional_after_assessment(self):
        receipt = self.assessor.assess(self.stage_path, save=False)
        self.assertTrue(receipt["ok"])
        health = Mock(returncode=1, stdout="health FAILED", stderr="")
        with patch("apollo_updater.subprocess.run", return_value=health):
            result = apply_update(self.target, self.stage_path, restart=False,
                                  assessed_manifest_sha256=receipt["manifest_sha256"])
        self.assertFalse(result["ok"])
        self.assertTrue(result["restored"], result)
        self.assert_unchanged()
        self.assertEqual(json.loads((self.target / "config.json").read_text())["version"], "3.1.0")

    def test_assessment_is_bound_to_internal_stage_directory(self):
        external = self.root / "outside_stage"
        external.mkdir()
        self.assertFalse(self.assessor.assess(external, save=False)["ok"])
        with self.assertRaises(AssessmentFailure):
            self.assessor.require(external, "a" * 64)


if __name__ == "__main__":
    unittest.main()
