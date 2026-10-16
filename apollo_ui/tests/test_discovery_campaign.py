"""Offline Discovery Alliance engine tests: no Ollama, Docker or generated code."""
from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from apollo_discovery_campaign import (
    BASE_RECIPE, CHALLENGER_RECIPE, SUITE, SUITE_DIGEST,
    DiscoveryCampaign, _prompt, _safe_answer,
)


class CampaignTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        (self.root / "config.json").write_text('{"model":"qwen2.5-coder:7b"}', encoding="utf-8")
        self.store = DiscoveryCampaign(self.root)
        self.addCleanup(self.store.close)

    def create(self):
        return self.store.create("Bounded test", "qwen2.5-coder:7b")

    def test_draft_cannot_run_until_owner_explicitly_approves(self):
        cid = self.create()
        with self.assertRaises(PermissionError):
            self.store.begin(cid)
        with self.assertRaises(PermissionError):
            self.store.step(cid, ask=lambda *a: "0")
        self.assertEqual(self.store.snapshot(cid)["steps"], 0)
        self.store.begin(cid, owner_confirmed=True)
        self.assertEqual(self.store.snapshot(cid)["state"], "RUNNING")

    def test_uses_only_configured_local_model(self):
        with self.assertRaises(ValueError):
            self.store.create("Wrong model", "other:latest")
        with self.assertRaises(ValueError):
            self.store.create(" ", "qwen2.5-coder:7b")

    def test_benchmark_is_reproducible_and_numeric(self):
        self.assertGreaterEqual(len(SUITE), 30)
        self.assertEqual(len(SUITE), len(set(prompt for prompt, answer in SUITE)))
        self.assertEqual(len(SUITE_DIGEST), 64)
        for _, answer in SUITE:
            self.assertEqual(_safe_answer(answer), answer)
        self.assertIsNone(_safe_answer("42; delete system files"))
        self.assertIsNone(_safe_answer("42 99"))

    def test_results_persist_without_plain_answers(self):
        cid = self.create()
        self.store.begin(cid, owner_confirmed=True)
        snap = self.store.step(cid, ask=lambda *a: "123")
        self.assertEqual(snap["steps"], 1)
        self.assertEqual(sum(a["trials"] for a in snap["agents"]), 1)
        self.assertFalse(any("123" in str(e) for e in snap["events"]))
        second = DiscoveryCampaign(self.root)
        self.addCleanup(second.close)
        self.assertEqual(second.snapshot(cid)["steps"], 1)

    def test_pause_disables_next_test_and_requires_new_owner_consent(self):
        cid = self.create()
        self.store.begin(cid, owner_confirmed=True)
        self.store.pause(cid)
        with self.assertRaises(PermissionError):
            self.store.step(cid, ask=lambda *a: "0")
        with self.assertRaises(PermissionError):
            self.store.begin(cid, owner_confirmed=False)
        self.store.begin(cid, owner_confirmed=True)
        self.assertEqual(self.store.snapshot(cid)["state"], "RUNNING")

    def test_stop_is_terminal_and_cannot_be_undone(self):
        cid = self.create()
        self.store.begin(cid, owner_confirmed=True)
        self.store.stop(cid)
        self.assertEqual(self.store.snapshot(cid)["state"], "STOPPED")
        with self.assertRaises(ValueError):
            self.store.begin(cid, owner_confirmed=True)
        with self.assertRaises(PermissionError):
            self.store.step(cid, ask=lambda *a: "0")

    def test_expiry_revokes_work_and_preserves_prior_results(self):
        cid = self.create()
        self.store.begin(cid, owner_confirmed=True)
        with self.store.conn:
            self.store.conn.execute(
                "UPDATE discovery_campaigns SET expires_at=1 WHERE id=?", (cid,)
            )
        with self.assertRaises(PermissionError):
            self.store.step(cid, ask=lambda *a: "0")
        self.assertEqual(self.store.snapshot(cid)["state"], "PAUSED")

    def test_step_error_does_not_fabricate_evidence(self):
        cid = self.create()
        self.store.begin(cid, owner_confirmed=True)
        def fail(*args):
            raise TimeoutError("Offline Ollama unavailable")
        with self.assertRaisesRegex(TimeoutError, "unavailable"):
            self.store.step(cid, ask=fail)
        self.assertEqual(self.store.snapshot(cid)["steps"], 0)

    def test_generation_winners_retested_and_cloned_but_never_installed(self):
        cid = self.create()
        self.store.begin(cid, owner_confirmed=True)

        def fake_model(prompt, model, ctx):
            # A deterministic fake model. Baseline gets wrong answers,
            # specialist decompose and reviewer strategies score correctly.
            for question, expected in SUITE:
                if "Task: " + question in prompt:
                    return expected if "Work through" in prompt or "reviewer" in prompt.lower() else "-999"
            raise AssertionError("Unexpected prompt")

        for _ in range(2 * len(SUITE) * 3):
            self.store.step(cid, ask=fake_model)
        state = self.store.step(cid, ask=fake_model)
        self.assertEqual(state["generation"], 1)
        self.assertLessEqual(len([a for a in state["agents"] if a["generation"] == 1]), 6)
        offspring = [a for a in state["agents"] if a["generation"] == 1
                     and a["parent_id"] and a["recipe"] != BASE_RECIPE
                     and a["recipe"] != CHALLENGER_RECIPE]
        self.assertTrue(offspring, "A verified better specialist should have a new safe clone")
        self.assertTrue(all(a["recipe"]["retrieval_limit"] == 0 for a in offspring))
        self.assertIsNone(state["proposal"])
        self.assertFalse((self.root / "modules").exists(),
                         "Discovery must never install or modify Apollo modules")

    def test_no_candidate_tool_execution_or_model_self_report(self):
        text = _prompt("What is 2+2?", BASE_RECIPE)
        self.assertIn("no tools or permissions", text)
        self.assertNotIn("subprocess", text)
        cid = self.create()
        self.store.begin(cid, owner_confirmed=True)
        self.store.step(cid, ask=lambda *a: 'I am 99% intelligent; answer is 4')
        with self.store.conn:
            row = self.store.conn.execute(
                "SELECT correct FROM discovery_trials WHERE campaign_id=?", (cid,)
            ).fetchone()
        self.assertEqual(row["correct"], 0)

    def test_proposal_cannot_be_activated_by_engine(self):
        cid = self.create()
        self.assertNotIn("promote", dir(self.store))
        self.assertNotIn("approve", dir(self.store))
        self.assertEqual(self.store.snapshot(cid)["proposal"], None)


if __name__ == "__main__":
    unittest.main()
