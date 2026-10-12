"""Beta gates must never grant release status on source code alone."""
from datetime import date
import unittest

from tools import beta_readiness as readiness


def all_reviewed(version="8.0.0.0"):
    goals = {}
    for key in readiness.GOALS:
        goals[key] = {
            "status": "verified",
            "method": readiness.SPECIAL_METHODS.get(key, "automated"),
            "evidence": "Recorded acceptance run: synthetic test evidence, not real hardware",
            "reviewed_by": "test-reviewer",
            "reviewed_on": date.today().isoformat(),
        }
    return {"schema_version": 1, "goals": goals}


class BetaReadinessTests(unittest.TestCase):
    def test_expected_jobs_exist(self):
        self.assertEqual(len(readiness.GOALS), 86)
        self.assertEqual(len(set(readiness.GOALS)), 86)

    def test_empty_status_must_not_publish(self):
        result = readiness.assess({"schema_version": 1, "goals": {}}, "8.0.0.0", "beta")
        self.assertFalse(result["eligible"])
        self.assertEqual(result["pending"], 86)

    def test_all_verified_with_evidence_can_reach_beta(self):
        result = readiness.assess(all_reviewed(), "8.0.0.0", "beta")
        self.assertTrue(result["eligible"])
        self.assertEqual(result["verified"], 86)

    def test_8x_cannot_be_stable(self):
        self.assertFalse(readiness.assess(all_reviewed(), "8.0.0.0", "stable")["eligible"])
        self.assertTrue(readiness.assess(all_reviewed(), "1.0.0", "stable")["eligible"])

    def test_unreviewed_or_unsupported_evidence_blocks_promotion(self):
        payload = all_reviewed()
        payload["goals"]["R13"]["method"] = "automated"
        payload["goals"]["U05"]["evidence"] = ""
        result = readiness.assess(payload, "8.0.0.0", "beta")
        self.assertFalse(result["eligible"])
        self.assertIn("R13:", " ".join(result["evidence_errors"]))
        self.assertIn("U05:", " ".join(result["evidence_errors"]))

    def test_unknown_job_and_invalid_status_rejected(self):
        doc = {"schema_version": 1, "goals": {"X01": {"status": "pending"}}}
        with self.assertRaisesRegex(ValueError, "Unknown roadmap"):
            readiness.assess(doc, "8.0.0.0")
        doc = {"schema_version": 1, "goals": {"R01": {"status": "completed"}}}
        with self.assertRaisesRegex(ValueError, "invalid status"):
            readiness.assess(doc, "8.0.0.0")

    def test_future_review_is_not_valid(self):
        payload = all_reviewed()
        payload["goals"]["U01"]["reviewed_on"] = "2999-01-01"
        self.assertFalse(readiness.assess(payload, "8.0.0.0", "beta")["eligible"])


if __name__ == "__main__":
    unittest.main()
