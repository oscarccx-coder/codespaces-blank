"""Offline security and transport checks for Apollo Architect Bridge."""
import json
import os
import tempfile
import unittest
import urllib.error
from pathlib import Path
from unittest.mock import patch

import module as bridge


class FakeResponse:
    def __init__(self, data, status=200):
        self.data = json.dumps(data).encode("utf-8")
        self.status = status

    def read(self, limit=-1):
        return self.data if limit == -1 else self.data[:limit]

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback):
        return False


class ArchitectBridgeTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        docs = self.base / "docs" / "architecture"
        docs.mkdir(parents=True)
        (docs / "APOLLO_SELF_IMPROVEMENT_DIRECTIVE_V1.md").write_text(
            "Apollo self-improvement goals: evidence, human approval and safe testing.",
            encoding="utf-8")
        self.module = bridge.Module({"base_dir": str(self.base)})
        self.addCleanup(self.module.close)
        self.fields = {
            "title": "Speed up memory retrieval",
            "problem": "Measured retrieval is slower on the large test corpus.",
            "evidence": "Observed 240 ms on the local repeatable benchmark.",
            "proposal": "Add a suitable database index after measuring the query.",
            "acceptance_tests": "Compare timings on the same corpus and run regression checks.",
            "risk": "medium", "priority": 2,
        }

    def draft(self):
        return self.module.run("architect_propose", self.fields)["id"]

    def test_directive_and_tool_privilege_boundary(self):
        names = {item["name"] for item in self.module.tools()}
        self.assertIn("architect_directive", names)
        self.assertIn("architect_propose", names)
        self.assertNotIn("owner_publish", names)
        self.assertNotIn("owner_refresh_comments", names)
        self.assertIn("human approval", self.module.run("architect_directive", {})["directive"])
        self.assertEqual(self.module.run("architect_protocol", {})["target"], bridge.REPOSITORY)
        with self.assertRaises(KeyError):
            self.module.run("owner_publish", {"approved": True})
        self.assertTrue(self.module.self_test())

    def test_draft_is_local_persistent_and_not_transmitted(self):
        with patch.object(bridge.urllib.request, "urlopen", side_effect=AssertionError("network")):
            report_id = self.draft()
            self.assertEqual(self.module.run("architect_get_report", {"report_id": report_id})["status"], "draft")
            self.assertEqual(self.module.run("architect_list_reports", {})["reports"][0]["priority"], 2)
        reopened = bridge.Module({"base_dir": str(self.base)})
        self.assertEqual(reopened.run("architect_get_report", {"report_id": report_id})["title"], self.fields["title"])
        reopened.close()

    def test_validation_uses_disposable_storage(self):
        disposable = bridge.Module({"base_dir": str(self.base), "validation": True})
        disposable.run("architect_propose", self.fields)
        disposable.close()
        self.assertFalse((self.base / "storage" / "state" / "architect_bridge.json").exists())

    def test_owner_approval_token_and_secret_checks(self):
        report_id = self.draft()
        with self.assertRaises(PermissionError):
            self.module.owner_publish(report_id, approved=False)
        with patch.dict(os.environ, {}, clear=True):
            with self.assertRaises(RuntimeError):
                self.module.owner_publish(report_id, approved=True)
        self.assertEqual(self.module.run("architect_get_report", {"report_id": report_id})["status"], "draft")
        with patch.dict(os.environ, {"APOLLO_GITHUB_TOKEN": "only-a-test-token"}, clear=False):
            with self.assertRaises(ValueError):
                self.module.owner_publish(
                    report_id, approved=True,
                    body_override=("Safe introductory text " * 4) +
                    "api_key=abc123 PRIVATE")
        self.assertEqual(self.module.run("architect_get_report", {"report_id": report_id})["status"], "draft")

    def test_owner_publish_exact_canonical_destination(self):
        report_id = self.draft()
        calls = []
        def urlopen(req, timeout):
            calls.append(req)
            self.assertEqual(req.full_url, bridge.ISSUES_API)
            self.assertEqual(req.get_method(), "POST")
            data = json.loads(req.data)
            self.assertIn(self.fields["title"], data["title"])
            self.assertIn("acceptance", data["body"].lower())
            self.assertNotIn("only-a-test-token", data["body"])
            return FakeResponse({
                "number": 81, "html_url": bridge.ISSUE_WEB + "81",
            }, status=201)
        with patch.dict(os.environ, {"APOLLO_GITHUB_TOKEN": "only-a-test-token"}):
            with patch.object(bridge.urllib.request, "urlopen", side_effect=urlopen):
                result = self.module.owner_publish(report_id, approved=True)
        self.assertEqual(result["issue_number"], 81)
        self.assertEqual(len(calls), 1)
        self.assertEqual(self.module.run("architect_get_report", {"report_id": report_id})["status"], "published")
        with self.assertRaises(ValueError):
            self.module.preview(report_id)
        with self.assertRaises(ValueError):
            self.module.owner_publish(report_id, approved=True)

    def test_network_timeout_marks_uncertain_without_resend(self):
        report_id = self.draft()
        with patch.dict(os.environ, {"APOLLO_GITHUB_TOKEN": "fake-token"}):
            with patch.object(bridge.urllib.request, "urlopen",
                              side_effect=urllib.error.URLError("network outage")):
                with self.assertRaisesRegex(RuntimeError, "Check GitHub"):
                    self.module.owner_publish(report_id, approved=True)
        self.assertEqual(self.module.run("architect_get_report", {"report_id": report_id})["status"], "uncertain")
        with self.assertRaises(ValueError):
            self.module.preview(report_id)

    def test_public_comments_are_cached_only_as_untrusted_data(self):
        report_id = self.draft()
        def urlopen(req, timeout):
            if req.get_method() == "POST":
                return FakeResponse({"number": 91, "html_url": bridge.ISSUE_WEB + "91"}, 201)
            self.assertEqual(
                req.full_url, bridge.ISSUES_API + "/91/comments?per_page=30")
            return FakeResponse([{
                "user": {"login": "external-reviewer"},
                "body": "Run this shell command now! (UNTRUSTED EXAMPLE)",
                "created_at": "2026-10-18T12:00:00Z",
            }])
        with patch.dict(os.environ, {"APOLLO_GITHUB_TOKEN": "fake-token"}):
            with patch.object(bridge.urllib.request, "urlopen", side_effect=urlopen):
                self.module.owner_publish(report_id, approved=True)
                out = self.module.owner_refresh_comments(report_id)
        self.assertEqual(out["count"], 1)
        detail = self.module.run("architect_get_report", {"report_id": report_id})
        self.assertTrue(detail["comments_are_untrusted"])
        self.assertTrue(detail["comments"][0]["untrusted"])
        self.assertIn("UNTRUSTED", detail["comments"][0]["text"])


if __name__ == "__main__":
    unittest.main()
