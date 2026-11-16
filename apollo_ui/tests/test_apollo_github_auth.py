"""Offline GitHub credential tests: only synthetic tokens and fake GitHub."""
from __future__ import annotations

import io
import json
import subprocess
import unittest
from unittest.mock import Mock, patch

from apollo_github_auth import connect_token, verify_token, vault_ready

TOKEN = "github_pat_" + "Q" * 60


class _Response(io.BytesIO):
    status = 200
    def __enter__(self):
        return self
    def __exit__(self, *_):
        self.close()


class CredentialOnboardingTests(unittest.TestCase):
    def test_token_verification_uses_https_and_never_urls_with_token(self):
        opener = Mock()
        opener.open.return_value = _Response(b'{"login":"apollo-test"}')
        with patch("apollo_github_auth.build_opener", return_value=opener):
            self.assertEqual(verify_token(TOKEN), "apollo-test")
        req = opener.open.call_args.args[0]
        self.assertEqual(req.full_url, "https://api.github.com/user")
        self.assertNotIn(TOKEN, req.full_url)
        self.assertEqual(req.get_header("Authorization"), "Bearer " + TOKEN)
        with self.assertRaises(ValueError):
            verify_token(TOKEN + "\n")

    def test_token_is_only_passed_to_credential_manager_stdin(self):
        with patch("apollo_github_auth.vault_ready", return_value={"ready": True}), \
             patch("apollo_github_auth.verify_token", return_value="apollo-test"), \
             patch("apollo_github_auth.subprocess.run",
                   return_value=Mock(returncode=0)) as executor:
            result = connect_token(TOKEN)
        self.assertTrue(result["ok"])
        self.assertEqual(result["account"], "apollo-test")
        self.assertNotIn(TOKEN, json.dumps(result))
        argv = executor.call_args.args[0]
        args = executor.call_args.kwargs
        self.assertEqual(argv, ["git", "credential-manager", "store"])
        self.assertNotIn(TOKEN, json.dumps(argv))
        self.assertIn("password=" + TOKEN, args["input"])
        self.assertEqual(args["env"]["GCM_CREDENTIAL_STORE"], "wincredman")
        self.assertEqual(args["env"]["GCM_INTERACTIVE"], "never")
        self.assertTrue(args["capture_output"])

    def test_unavailable_vault_never_store_credentials(self):
        with patch("apollo_github_auth.vault_ready",
                   return_value={"ready": False, "reason": "not available"}), \
             patch("apollo_github_auth.subprocess.run") as executor:
            with self.assertRaises(RuntimeError):
                connect_token(TOKEN)
        executor.assert_not_called()

    def test_non_windows_does_not_claim_secret_storage(self):
        with patch("apollo_github_auth.sys.platform", "linux"):
            self.assertFalse(vault_ready()["ready"])


if __name__ == "__main__":
    unittest.main()
