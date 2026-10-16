"""Deterministic regression tests for survival-of-the-fittest recipe selection."""
from dataclasses import replace
import unittest

from apollo_discovery_selection import (
    CandidateEvaluation, SelectionPolicy, clone_recipe, select_generation,
)

DIGEST = "f" * 64
POLICY = SelectionPolicy(max_population=5, min_accuracy=.85,
                         min_gain=.03, min_efficiency_gain=.20)


def evaluation(name, **overrides):
    value = dict(candidate_id=name, generation=0, suite_sha256=DIGEST,
                 accuracy=.90, robustness=.88, efficiency=.50, cases=100,
                 repeat_runs=3, safety_passed=True, regressions_passed=True,
                 provenance_passed=True)
    value.update(overrides)
    return CandidateEvaluation(**value)


class SelectionTests(unittest.TestCase):
    def test_successful_new_candidate_selected_and_cloned(self):
        result = select_generation([evaluation("baseline"),
                                    evaluation("new", accuracy=.96)],
                                   baseline_id="baseline", suite_sha256=DIGEST,
                                   generation=0, policy=POLICY)
        self.assertEqual(result.retained, ("baseline", "new"))
        self.assertEqual(result.clone_parents, ("new",))

    def test_weak_candidate_on_probation_then_retired(self):
        weak = evaluation("weak", accuracy=.50)
        first = select_generation([evaluation("baseline"), weak],
                                  baseline_id="baseline", suite_sha256=DIGEST,
                                  generation=0, policy=POLICY)
        self.assertIn("weak", first.probation)
        second = select_generation([evaluation("baseline"), replace(weak, prior_misses=1)],
                                   baseline_id="baseline", suite_sha256=DIGEST,
                                   generation=0, policy=POLICY)
        self.assertIn("weak", second.retired)
        self.assertNotIn("weak", second.retained)

    def test_critical_safety_failure_quarantined_even_if_fast(self):
        dangerous = evaluation("bad", accuracy=1, efficiency=1, safety_passed=False)
        result = select_generation([evaluation("baseline"), dangerous],
                                   baseline_id="baseline", suite_sha256=DIGEST,
                                   generation=0, policy=POLICY)
        self.assertEqual(result.quarantined, ("bad",))
        self.assertEqual(result.clone_parents, ())

    def test_last_baseline_cannot_be_retired(self):
        bad_base = evaluation("baseline", accuracy=.4, safety_passed=False)
        result = select_generation([bad_base, evaluation("new", accuracy=1)],
                                   baseline_id="baseline", suite_sha256=DIGEST,
                                   generation=0, policy=POLICY)
        self.assertEqual(result.retained, ("baseline",))
        self.assertEqual(result.clone_parents, ())

    def test_bad_evidence_never_cloned(self):
        weak_evidence = evaluation("new", accuracy=1, cases=4)
        result = select_generation([evaluation("baseline"), weak_evidence],
                                   baseline_id="baseline", suite_sha256=DIGEST,
                                   generation=0, policy=POLICY)
        self.assertIn("new", result.probation)
        self.assertFalse(result.clone_parents)

    def test_quota_limits_population_and_spawning(self):
        policy = SelectionPolicy(max_population=4, max_clone_orders=2)
        results = [evaluation("baseline")] + [evaluation(f"a{i}", accuracy=.96) for i in range(3)]
        outcome = select_generation(results, baseline_id="baseline", suite_sha256=DIGEST,
                                    generation=0, policy=policy)
        self.assertLessEqual(len(outcome.retained) + len(outcome.clone_parents), policy.max_population)
        self.assertEqual(outcome.clone_parents, ("a0", "a0"))
        self.assertEqual(outcome.archived, ("a1", "a2"))

    def test_no_clones_after_final_generation(self):
        policy = SelectionPolicy(max_generations=3)
        results = [evaluation("baseline", generation=2), evaluation("new", generation=2, accuracy=.98)]
        outcome = select_generation(results, baseline_id="baseline", suite_sha256=DIGEST,
                                    generation=2, policy=policy)
        self.assertEqual(outcome.clone_parents, ())

    def test_hash_mismatch_is_quarantined(self):
        outcome = select_generation([evaluation("baseline"), evaluation("new", accuracy=1, suite_sha256="0" * 64)],
                                    baseline_id="baseline", suite_sha256=DIGEST, generation=0)
        self.assertEqual(outcome.quarantined, ("new",))

    def test_duplicate_ids_and_mixed_generations_refused(self):
        with self.assertRaises(ValueError):
            select_generation([evaluation("baseline"), evaluation("baseline")],
                              baseline_id="baseline", suite_sha256=DIGEST, generation=0)
        with self.assertRaises(ValueError):
            select_generation([evaluation("baseline"), evaluation("new", generation=1)],
                              baseline_id="baseline", suite_sha256=DIGEST, generation=0)

    def test_bad_numbers_and_unbounded_population_refused(self):
        with self.assertRaises(ValueError):
            evaluation("bad", accuracy=float("nan"))
        with self.assertRaises(ValueError):
            SelectionPolicy(max_population=100000)

    def test_clone_allowlisted_recipe_only(self):
        parent = dict(strategy="direct", review_passes=1, context_budget=1024,
                      retrieval_limit=0)
        clone = clone_recipe(parent, {"review_passes": 2})
        self.assertEqual(clone["review_passes"], 2)
        self.assertEqual(parent["review_passes"], 1)
        with self.assertRaises(ValueError):
            clone_recipe(parent, {"safety_policy": "disabled"})
        with self.assertRaises(ValueError):
            clone_recipe(parent, {"review_passes": 999})

    def test_efficiency_can_win_with_noninferior_quality(self):
        baseline = evaluation("baseline", accuracy=.90, efficiency=.40)
        efficient = evaluation("efficient", accuracy=.895, efficiency=.75)
        outcome = select_generation([baseline, efficient], baseline_id="baseline",
                                    suite_sha256=DIGEST, generation=0, policy=POLICY)
        self.assertEqual(outcome.clone_parents, ("efficient",))


if __name__ == "__main__":
    unittest.main()
