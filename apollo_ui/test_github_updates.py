"""GitHub Releases source and end-to-end signed staging without network access."""
import json
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import os
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.serialization import Encoding, PrivateFormat, NoEncryption


TEST_ONLY_SIGNING_KEY = Ed25519PrivateKey.generate().private_bytes(
    Encoding.PEM, PrivateFormat.PKCS8, NoEncryption()
).decode("ascii")

from apollo_github_updates import REPOSITORY, latest_release, _asset_url
from apollo_update import UpdateService
from apollo_release import publish


def candidate(version, channel="stable", with_asset=True, size=4096):
    suffix = "" if channel == "stable" else ("-dev" if channel == "development" else "-beta")
    tag = f"v{version}{suffix}"
    asset = {
        "name": f"apollo-{version}.zip",
        "size": size,
        "browser_download_url": (
            f"https://github.com/{REPOSITORY}/releases/download/{tag}/apollo-{version}.zip"
        ),
    }
    return {
        "tag_name": tag, "draft": False, "prerelease": channel != "stable",
        "assets": [asset] if with_asset else [],
        "published_at": "2026-10-08T12:00:00Z",
    }


@patch.dict(os.environ, {"APOLLO_RELEASE_PRIVATE_PEM": TEST_ONLY_SIGNING_KEY})
class GitHubReleaseTests(unittest.TestCase):
    def test_channel_filters_and_version_selection(self):
        releases = [candidate("7.5.14.1"), candidate("7.5.13.0"),
                    candidate("7.5.15.0", "beta"), candidate("7.5.16.0", "development")]
        self.assertEqual(latest_release("stable", releases)["version"], "7.5.14.1")
        self.assertEqual(latest_release("beta", releases)["version"], "7.5.15.0")
        self.assertEqual(latest_release("development", releases)["version"], "7.5.16.0")
        self.assertIsNone(latest_release("pinned", releases))
        self.assertIsNone(latest_release("stable", [candidate("99.0", with_asset=False)]))

    def test_repo_url_validation(self):
        allowed = candidate("7.5.13.0")["assets"][0]["browser_download_url"]
        self.assertEqual(_asset_url(allowed), allowed)
        for address in (
            "http://github.com/oscarccx-coder/codespaces-blank/releases/download/x/file",
            "https://evil.example/update.zip",
            "https://github.com/untrusted/repo/releases/download/x/update.zip",
            "https://github.com/oscarccx-coder/codespaces-blank/archive/main.zip",
            allowed + "?token=something",
        ):
            with self.subTest(address=address), self.assertRaises(ValueError):
                _asset_url(address)

    def test_staged_github_package_is_signed_and_preserves_user_storage(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            source, target, releases = (root / x for x in ("source", "target", "releases"))
            for x in (source, target):
                x.mkdir()
            (source / "config.json").write_text(json.dumps({"version": "1.2.0"}))
            (source / "main.py").write_text("VALUE = 2\n")
            (source / "Audio").mkdir()
            (source / "Audio" / "private.wav").write_bytes(b"private voice sample")
            (source / "models" / "voice" / "xtts_v2").mkdir(parents=True)
            (source / "models" / "voice" / "xtts_v2" / "model.pth").write_bytes(b"model")
            published = publish(source, releases, "stable")
            archive = Path(published["package"])
            (target / "config.json").write_text(json.dumps({"version": "1.1.0"}))
            service = UpdateService(target)
            service.import_trusted_key(published["public_key"])
            with patch("apollo_github_updates._read_releases", return_value=[
                candidate("1.2.0", "stable", size=archive.stat().st_size)
            ]), patch("apollo_update.download_release_asset",
                      side_effect=lambda url, dest, progress=None: (
                          shutil.copyfile(archive, dest),
                          {"bytes": archive.stat().st_size},
                      )[1]):
                checked = service.check_for_updates()
                self.assertTrue(checked["available"])
                staged = service.stage_update()
            self.assertTrue(staged["ok"], staged)
            stage = Path(staged["stage_dir"])
            self.assertEqual((stage / "payload" / "main.py").read_text(), "VALUE = 2\n")
            self.assertFalse((stage / "payload" / "Audio").exists())
            self.assertFalse((stage / "payload" / "models").exists())

    def test_github_release_manifest_channel_cannot_be_spoofed(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            src, target = root / "src", root / "target"
            src.mkdir()
            target.mkdir()
            (src / "config.json").write_text('{"version":"2.0.0"}')
            (src / "main.py").write_text("ok")
            built = publish(src, root / "releases", "beta")
            service = UpdateService(target)
            (target / "config.json").write_text('{"version":"1.0.0"}')
            service.import_trusted_key(built["public_key"])
            checked = service.stage_local_package(built["package"],
                                                expected_version="2.0.0",
                                                expected_channel="stable")
            self.assertFalse(checked["ok"])
            self.assertIn("channel", checked["error"])


if __name__ == "__main__":
    unittest.main()
