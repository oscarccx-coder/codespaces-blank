"""Backup preflight failure must never leave an Apollo update half-installed."""
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.serialization import (
    Encoding, PrivateFormat, NoEncryption,
)

from apollo_release import publish
from apollo_update import UpdateService
from apollo_updater import apply_update


class SafeBackupFailureTests(unittest.TestCase):
    def test_permission_or_disk_error_refuses_update_before_live_mutation(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source, target = root / "source", root / "target"
            source.mkdir()
            target.mkdir()
            (source / "config.json").write_text('{"version":"8.0.0.0"}', encoding="utf-8")
            (source / "main.py").write_text("NEW_CODE = True\n", encoding="utf-8")
            (target / "config.json").write_text('{"version":"7.5.13.0","model":"local"}', encoding="utf-8")
            (target / "main.py").write_text("OLD_CODE = True\n", encoding="utf-8")

            secret = Ed25519PrivateKey.generate().private_bytes(
                Encoding.PEM, PrivateFormat.PKCS8, NoEncryption()
            ).decode("ascii")
            with patch.dict(os.environ, {"APOLLO_RELEASE_PRIVATE_PEM": secret}):
                release = publish(source, root / "releases", "beta")
            service = UpdateService(target)
            service.import_trusted_key(release["public_key"])
            staged = service.stage_local_package(release["package"])
            self.assertTrue(staged["ok"], staged)

            with patch("apollo_updater.shutil.copy2", side_effect=PermissionError("storage full")):
                result = apply_update(target, staged["stage_dir"])
            self.assertFalse(result["ok"])
            self.assertEqual(result["stage"], "backup")
            self.assertTrue(result["restored"])
            self.assertIn("no live files changed", result["error"])
            self.assertEqual((target / "main.py").read_text(encoding="utf-8"), "OLD_CODE = True\n")
            self.assertEqual(json.loads((target / "config.json").read_text(encoding="utf-8")),
                             {"version": "7.5.13.0", "model": "local"})


if __name__ == "__main__":
    unittest.main()
