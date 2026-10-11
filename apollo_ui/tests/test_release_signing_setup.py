"""Offline tests for safe first-time Apollo signing key provisioning."""
import hashlib
import importlib.util
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TOOL = ROOT / "tools" / "prepare_release_identity.py"
spec = importlib.util.spec_from_file_location("prepare_release_identity", TOOL)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class ReleaseSigningSetupTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name) / "Apollo with spaces" / "apollo_ui"
        self.root.mkdir(parents=True)
        (self.root / "config.json").write_text('{"version":"7.5.13.10"}')
        (self.root / "apollo_release.py").write_text("# test fixture")

    def test_generates_and_reuses_stable_ed25519_identity(self):
        from cryptography.hazmat.primitives.serialization import load_pem_public_key
        from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
        first = module.prepare_identity(self.root)
        self.assertFalse(first["reused_existing_signing_key"])
        private_bytes = Path(first["private_key_file"]).read_bytes()
        pub = Path(first["public_key_file"]).read_bytes()
        self.assertTrue(isinstance(load_pem_public_key(pub), Ed25519PublicKey))
        self.assertIn(b"PRIVATE KEY", private_bytes)
        self.assertEqual(first["public_key_sha256"], hashlib.sha256(pub).hexdigest())
        self.assertEqual(Path(first["fingerprint_file"]).read_text().strip(), first["public_key_sha256"])
        second = module.prepare_identity(self.root)
        self.assertTrue(second["reused_existing_signing_key"])
        self.assertEqual(private_bytes, Path(first["private_key_file"]).read_bytes())
        self.assertEqual(pub, Path(first["public_key_file"]).read_bytes())
        self.assertFalse((self.root / "storage/updates/trust/release_public.pem").exists())

    def test_existing_public_key_is_not_replaced(self):
        output = module.prepare_identity(self.root)
        public = Path(output["public_key_file"])
        public.write_bytes(b"incorrect key")
        with self.assertRaisesRegex(RuntimeError, "does not match"):
            module.prepare_identity(self.root)
        self.assertEqual(public.read_bytes(), b"incorrect key")

    def test_unmatched_existing_trust_does_not_get_changed(self):
        trusted = self.root / "storage" / "updates" / "trust" / "release_public.pem"
        trusted.parent.mkdir(parents=True)
        trusted.write_text("already trusted")
        with self.assertRaisesRegex(RuntimeError, "already exists"):
            module.prepare_identity(self.root)
        self.assertFalse((self.root / "storage/updates/keys/release_private.pem").exists())
        self.assertEqual(trusted.read_text(), "already trusted")

    def test_key_must_not_be_regenerated_after_partial_loss(self):
        folder = self.root / "storage/updates/keys"
        folder.mkdir(parents=True)
        (folder / "release_public.pem").write_text("public only")
        with self.assertRaisesRegex(RuntimeError, "missing"):
            module.prepare_identity(self.root)
        self.assertFalse((folder / "release_private.pem").exists())

    def test_missing_app_refuses_to_write(self):
        (self.root / "apollo_release.py").unlink()
        with self.assertRaisesRegex(ValueError, "not an Apollo"):
            module.prepare_identity(self.root)
        self.assertFalse((self.root / "storage/updates/keys").exists())

    def test_launcher_has_no_remote_key_fetch_or_implicit_trust(self):
        bat = (ROOT / "Setup/12_SETUP_RELEASE_SIGNING.bat").read_text(encoding="utf-8")
        self.assertIn(r".venv\Scripts\python.exe", bat)
        self.assertIn("prepare_release_identity.py", bat)
        self.assertNotIn("git clone", bat)
        self.assertNotIn("pip install", bat)


if __name__ == "__main__":
    unittest.main()
