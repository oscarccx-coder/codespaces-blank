"""Crash, resume, range validation and checksum-stage download regression tests."""
import io
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from apollo_github_updates import download_release_asset

URL = "https://github.com/oscarccx-coder/codespaces-blank/releases/download/v8.0.0.1-beta/apollo-8.0.0.1.zip"


class FakeResponse:
    status = 200
    def __init__(self, data, *, headers=None, status=200, fail_after_first=False, host="github.com"):
        self.buff = io.BytesIO(data)
        self.headers = headers or {"Content-Length": str(len(data))}
        self.status = status
        self.fail_after_first = fail_after_first
        self.calls = 0
        self.host = host

    def read(self, size):
        self.calls += 1
        if self.fail_after_first and self.calls >= 2:
            raise ConnectionResetError("Network went offline")
        return self.buff.read(size)

    def geturl(self):
        return "https://" + self.host + "/asset"

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


class DownloadRecoveryTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.out = Path(self.folder.name) / "apollo.zip"

    def test_network_failure_retains_partial_then_resumes(self):
        def first(url_request, timeout):
            self.assertIsNone(url_request.get_header("Range"))
            return FakeResponse(b"part", headers={"Content-Length": "8"}, fail_after_first=True)
        with patch("apollo_github_updates.urllib.request.urlopen", side_effect=first):
            with self.assertRaises(ConnectionResetError):
                download_release_asset(URL, self.out)
        self.assertFalse(self.out.exists())
        self.assertEqual(self.out.with_name("apollo.zip.part").read_bytes(), b"part")

        def second(url_request, timeout):
            self.assertEqual(url_request.get_header("Range"), "bytes=4-")
            return FakeResponse(b"tail", status=206,
                headers={"Content-Length": "4", "Content-Range": "bytes 4-7/8"})
        with patch("apollo_github_updates.urllib.request.urlopen", side_effect=second):
            result = download_release_asset(URL, self.out)
        self.assertEqual(result["resumed_bytes"], 4)
        self.assertEqual(result["transferred_bytes"], 4)
        self.assertEqual(self.out.read_bytes(), b"parttail")
        self.assertFalse(self.out.with_name("apollo.zip.part").exists())

    def test_server_ignoring_range_restarts_instead_of_appending(self):
        self.out.with_name("apollo.zip.part").write_bytes(b"stale")
        with patch("apollo_github_updates.urllib.request.urlopen",
                   return_value=FakeResponse(b"newdata")):
            result = download_release_asset(URL, self.out)
        self.assertEqual(self.out.read_bytes(), b"newdata")
        self.assertEqual(result["resumed_bytes"], 0)

    def test_invalid_resume_range_rejected_without_installation(self):
        self.out.with_name("apollo.zip.part").write_bytes(b"partial")
        with patch("apollo_github_updates.urllib.request.urlopen",
                   return_value=FakeResponse(b"stuff", status=206,
                     headers={"Content-Length": "5", "Content-Range": "bytes 3-7/8"})):
            with self.assertRaisesRegex(ValueError, "Invalid resume"):
                download_release_asset(URL, self.out)
        self.assertFalse(self.out.exists())

    def test_redirects_outside_github_refused(self):
        with patch("apollo_github_updates.urllib.request.urlopen",
                   return_value=FakeResponse(b"fake", host="evil.example")):
            with self.assertRaisesRegex(ValueError, "redirect"):
                download_release_asset(URL, self.out)
        self.assertFalse(self.out.exists())

    def test_excessive_size_does_not_create_installable_zip(self):
        with patch("apollo_github_updates.urllib.request.urlopen",
                   return_value=FakeResponse(b"123456", headers={"Content-Length": "6"})):
            with self.assertRaisesRegex(ValueError, "limit"):
                download_release_asset(URL, self.out, max_bytes=4)
        self.assertFalse(self.out.exists())


if __name__ == "__main__":
    unittest.main()
