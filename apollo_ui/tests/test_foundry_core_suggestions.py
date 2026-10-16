"""Apollo-core discovery and verification gate: offline, fail-closed tests."""
import hashlib
import json
from pathlib import Path
import tempfile
import unittest

from apollo_foundry_core import ApolloCoreSuggestions, _source_relative


def sha(data):
    return hashlib.sha256(data).hexdigest()


class CoreSuggestionTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        (self.root / "modules" / "example").mkdir(parents=True)
        self.source = self.root / "modules" / "example" / "module.py"
        self.source.write_text(
            "# TODO: improve error handling\n"
            "# FIXME: missing test coverage\n"
            "def compute():\n    return 42\n",
            encoding="utf-8",
        )
        self.core = ApolloCoreSuggestions(self.root)

    def test_scan_is_local_deduplicated_and_does_not_change_source(self):
        original = self.source.read_bytes()
        first = self.core.scan()
        second = self.core.scan()
        self.assertEqual(first["new_suggestions"], 2)
        self.assertEqual(second["new_suggestions"], 0)
        self.assertEqual(first["scanned_files"], 1)
        self.assertEqual(len(self.core.list()), 2)
        self.assertEqual(self.source.read_bytes(), original)
        self.assertEqual(first["policy"], "local_read_only_no_git_no_core_changes")

    def test_scan_ignores_secrets_workspace_and_symlink(self):
        (self.root / "storage" / "keys").mkdir(parents=True)
        (self.root / "storage" / "keys" / "password.py").write_text(
            "# TODO: secret should never be indexed")
        (self.root / "workspace").mkdir()
        (self.root / "workspace" / "private.py").write_text("# FIXME: secret")
        self.assertEqual(self.core.scan()["scanned_files"], 1)
        self.assertNotIn("password.py", json.dumps(self.core.list()))
        self.assertNotIn("private.py", json.dumps(self.core.list()))

    def test_review_is_explicit_and_dismiss_is_persistent(self):
        self.core.scan()
        ident = self.core.list()[0]["id"]
        self.assertEqual(self.core.set_review(
            ident, request_review=True, notes="Investigate safely"
        )["status"], "review_requested")
        self.assertEqual(ApolloCoreSuggestions(self.root).list()[0]["status"],
                         "review_requested")
        self.assertEqual(self.core.set_review(
            ident, request_review=False
        )["status"], "dismissed")

    def test_proactive_quality_and_missing_self_test_findings(self):
        self.source.write_text(
            "class Module:\n"
            "    def run(self):\n"
            "        try:\n"
            "            return 1\n"
            "        except:\n"
            "            return None\n",
            encoding="utf-8",
        )
        report = self.core.scan()
        self.assertEqual(report["new_suggestions"], 2)
        kinds = {item["kind"] for item in self.core.list()}
        self.assertEqual(kinds, {"quality", "testing"})

    def test_ai_idea_only_queues_never_changes_core(self):
        original = self.source.read_bytes()
        args = (
            "Improve calculation error handling",
            "The module returns a constant and lacks input validation; "
            "consider explicit validation and a regression test.",
            "modules/example/module.py",
        )
        first = self.core.propose(*args)
        second = self.core.propose(*args)
        self.assertTrue(first["new"])
        self.assertFalse(second["new"])
        self.assertFalse(first["pushed"])
        self.assertFalse(first["applied"])
        self.assertEqual(self.source.read_bytes(), original)
        self.assertEqual(first["suggestion"]["status"], "suggested")

    def test_ai_idea_rejects_unverified_file_or_vague_rationale(self):
        with self.assertRaises(ValueError):
            self.core.propose("Fix bug", "Unknown", "modules/example/module.py")
        with self.assertRaises(ValueError):
            self.core.propose(
                "Improve error handling",
                "There is a clear issue that deserves a closer look.",
                "storage/private.py",
            )

    def test_bad_paths_rejected(self):
        for name in ("../secret.py", "/tmp/evil.py", "storage/private.py",
                     ".git/hooks.py", "modules/../../evil.py", "modules\\evil.py",
                     "modules/credentials.json"):
            with self.subTest(name=name):
                with self.assertRaises(ValueError):
                    _source_relative(name)

    def _candidate(self):
        self.core.scan()
        suggestion = self.core.list()[0]["id"]
        self.core.set_review(suggestion, request_review=True)
        folder = self.root / "workspace" / "self_improvement" / "proposal-1"
        candidate = folder / "candidate" / "modules" / "example" / "module.py"
        candidate.parent.mkdir(parents=True)
        data = b"def compute():\n    return 43\n"
        candidate.write_bytes(data)
        manifest = {"changes": [{
            "path": "modules/example/module.py",
            "original_sha256": sha(self.source.read_bytes()),
            "candidate_sha256": sha(data),
        }]}
        (folder / "proposal.json").write_text(json.dumps(manifest))
        return suggestion, folder, candidate

    def test_candidate_static_check_never_authorises_push(self):
        suggestion, folder, _ = self._candidate()
        result = self.core.candidate_status(suggestion, folder)
        self.assertTrue(result["static_pass"])
        for name in ("runtime_verified", "ci_verified", "owner_approved",
                     "push_allowed", "merge_allowed", "applied"):
            self.assertFalse(result[name], name)
        self.assertEqual(self.source.read_text().splitlines()[-1], "    return 42")

    def test_candidate_hash_tampering_fails(self):
        suggestion, folder, candidate = self._candidate()
        candidate.write_text("def compute():\n    return 'tampered'\n")
        with self.assertRaisesRegex(ValueError, "hash mismatch"):
            self.core.candidate_status(suggestion, folder)

    def test_changed_original_blocks_stale_candidate(self):
        suggestion, folder, _ = self._candidate()
        self.source.write_text("def compute():\n    return 99\n")
        with self.assertRaisesRegex(ValueError, "rebase required"):
            self.core.candidate_status(suggestion, folder)

    def test_syntax_error_is_not_verified(self):
        suggestion, folder, candidate = self._candidate()
        bad = b"def broken(:\n"
        candidate.write_bytes(bad)
        proposal = json.loads((folder / "proposal.json").read_text())
        proposal["changes"][0]["candidate_sha256"] = sha(bad)
        (folder / "proposal.json").write_text(json.dumps(proposal))
        result = self.core.candidate_status(suggestion, folder)
        self.assertFalse(result["static_pass"])
        self.assertEqual(result["candidate_files"][0]["status"], "syntax_failed")

    def test_unreviewed_suggestion_cannot_be_verified(self):
        self.core.scan()
        with self.assertRaisesRegex(ValueError, "Owner must request review"):
            self.core.candidate_status(self.core.list()[0]["id"], self.root)

    def test_candidate_outside_is_rejected(self):
        suggestion, folder, _ = self._candidate()
        with self.assertRaisesRegex(ValueError, "isolated"):
            self.core.candidate_status(suggestion, self.root / "modules")

    def test_no_git_subprocess_or_network_dependencies(self):
        import inspect
        import apollo_foundry_core
        source = inspect.getsource(apollo_foundry_core)
        self.assertNotIn("subprocess.run(", source)
        self.assertNotIn("git push", source)
        self.assertNotIn("requests.post(", source)
        self.assertNotIn("os.system(", source)


if __name__ == "__main__":
    unittest.main()
