"""Release pipeline cannot publish unsigned, stale, or unexpectedly re-keyed assets."""
import hashlib
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import zipfile

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.serialization import (
    Encoding, PrivateFormat, PublicFormat, NoEncryption,
)

from apollo_release import ensure_signing_key, publish
from tools import release_ci


class SignedPipelineTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        (self.root / "config.json").write_text('{"version":"7.5.13.3"}', encoding="utf-8")
        (self.root / "main.py").write_text("x=1\n", encoding="utf-8")
        private = Ed25519PrivateKey.generate()
        self.key = private.private_bytes(
            Encoding.PEM, PrivateFormat.PKCS8, NoEncryption()
        ).decode("ascii")
        public = private.public_key().public_bytes(
            Encoding.PEM, PublicFormat.SubjectPublicKeyInfo,
        )
        self.fingerprint = hashlib.sha256(public).hexdigest()

    def test_tag_validation(self):
        self.assertEqual(release_ci.tag_for("7.5.13.3", "beta"), "v7.5.13.3-beta")
        self.assertEqual(release_ci.tag_for("7.5.13.3", "stable"), "v7.5.13.3")
        for version, channel in (("../2", "stable"), ("7.5.3", "development"),
                                 ("7.5.13.3 ; touch exploit", "beta")):
            with self.subTest(version=version), self.assertRaises(ValueError):
                release_ci.tag_for(version, channel)

    def test_ci_refuses_to_generate_new_key(self):
        with patch.dict(os.environ, {"CI": "true", "APOLLO_RELEASE_PRIVATE_PEM": ""}):
            with self.assertRaisesRegex(RuntimeError, "missing"):
                ensure_signing_key(self.root)
        self.assertFalse((self.root / "storage" / "updates" / "keys" / "release_private.pem").exists())

    def test_existing_secret_signed_release_does_not_write_private_key(self):
        with patch.dict(os.environ, {"CI": "true", "APOLLO_RELEASE_PRIVATE_PEM": self.key}):
            built = publish(self.root, self.root / "output", "beta")
        self.assertEqual(built["version"], "7.5.13.3")
        self.assertFalse((self.root / "storage" / "updates" / "keys" / "release_private.pem").exists())
        manifest = release_ci.verify_release(built["package"], built["public_key"])
        self.assertEqual(manifest["channel"], "beta")
        self.assertEqual(manifest["version"], "7.5.13.3")

    def test_changed_package_byte_fails_validation(self):
        with patch.dict(os.environ, {"CI": "true", "APOLLO_RELEASE_PRIVATE_PEM": self.key}):
            built = publish(self.root, self.root / "output", "stable")
        package = Path(built["package"])
        tampered = self.root / "tampered.zip"
        with zipfile.ZipFile(package) as inp, zipfile.ZipFile(tampered, "w") as out:
            for name in inp.namelist():
                data = inp.read(name)
                if name == "payload/main.py":
                    data = b"x=9\n"
                out.writestr(name, data)
        with self.assertRaisesRegex(ValueError, "hash"):
            release_ci.verify_release(tampered, built["public_key"])

    def test_pinned_fingerprint_and_verified_sha_required(self):
        sha = "1" * 40
        with patch.dict(os.environ, {"CI": "true", "APOLLO_RELEASE_PRIVATE_PEM": self.key}), \
             patch.object(release_ci, "ROOT", self.root), \
             patch("tools.release_ci.subprocess.check_output", return_value=sha):
            with self.assertRaisesRegex(RuntimeError, "fingerprint"):
                release_ci.prepare("stable", sha, "0" * 64)
            good = release_ci.prepare("stable", sha, self.fingerprint)
            self.assertEqual(good["tag"], "v7.5.13.3")
            self.assertTrue(Path(good["checksum"]).exists())
            with self.assertRaisesRegex(RuntimeError, "verified commit"):
                release_ci.prepare("stable", "2" * 40, self.fingerprint)

    def test_duplicate_tag_never_overwritten(self):
        bundle = {"tag": "v7.5.13.3", "channel": "stable"}
        with patch("tools.release_ci.subprocess.run") as gh:
            gh.return_value.returncode = 0  # release already exists
            with self.assertRaisesRegex(RuntimeError, "already exists"):
                release_ci.publish_to_github(bundle)
            self.assertTrue(release_ci.publish_to_github(bundle, skip_existing=True)["skipped"])
            self.assertEqual(gh.call_count, 2)  # lookup only, no release creation


if __name__ == "__main__":
    unittest.main()
