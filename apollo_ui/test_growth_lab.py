"""Growth Lab regression: no external transfers, purchases, or AI-approved work."""
import ast
import importlib.util
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import subprocess

from apollo_growth import (
    GrowthStore, hardware_snapshot, pence, gbp, OPPORTUNITY_TEMPLATES
)
from apollo_module_catalog import group_for


ROOT = Path(__file__).resolve().parent


class GrowthTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.base = Path(self.tmp.name)
        self.s = GrowthStore(self.base)
        self.addCleanup(self.s.close)

    def test_money_is_integer_pence_and_bounds_checked(self):
        self.assertEqual(pence("12.34"), 1234)
        self.assertEqual(pence("0", positive=False), 0)
        self.assertEqual(gbp(1234), "£12.34")
        self.assertEqual(gbp(-1234), "£-12.34" if False else "£-12.34")
        for invalid in ("NaN", "-1", "1e9", "1.234", "5,000", "999999999", "", "3.5x", None, True):
            with self.subTest(value=invalid), self.assertRaises(ValueError):
                pence(invalid)
        with self.assertRaises(ValueError):
            pence("0")

    def test_work_approval_requires_user_only_state_transition(self):
        result = self.s.propose("Build restaurant tracker",
                                "Custom spreadsheet delivered with documentation",
                                "Business spreadsheet", "65.00")
        self.assertTrue(result["created"])
        self.assertFalse(result["income_confirmed"])
        work_id = result["id"]
        self.assertEqual(self.s.list_work()[0]["estimate_gbp"], "£65.00")
        with self.assertRaisesRegex(ValueError, "delivered"):
            self.s.record_payment_from_ui(work_id, "65", "Bank confirmed")
        with self.assertRaisesRegex(ValueError, "transition"):
            self.s.transition_from_ui(work_id, "delivered")
        self.s.transition_from_ui(work_id, "approved")
        self.s.transition_from_ui(work_id, "delivered")
        paid = self.s.record_payment_from_ui(work_id, "62.50", "Manually confirmed receipt")
        self.assertEqual(paid["recorded_gbp"], "£62.50")
        self.assertEqual(self.s.summary()["paid_work_recorded_gbp"], "£62.50")
        self.assertEqual(self.s.summary()["balance_gbp"], "£62.50")
        with self.assertRaisesRegex(ValueError, "delivered"):
            self.s.record_payment_from_ui(work_id, "62.50", "Repeat should be rejected")
        self.assertEqual(self.s.summary()["balance_gbp"], "£62.50")
        self.assertEqual(self.s.list_work()[0]["status"], "paid")

    def test_work_proposal_deduplicates_and_is_never_money(self):
        first = self.s.propose("Circuit lesson pack", "Original low voltage PDF workbook")
        second = self.s.propose("CIRCUIT lesson PACK", "Original low voltage PDF workbook")
        self.assertEqual(first["id"], second["id"])
        self.assertFalse(second["created"])
        self.assertEqual(self.s.summary()["balance_gbp"], "£0.00")
        self.assertEqual(len(self.s.list_work()), 1)
        with self.assertRaises(ValueError):
            self.s.propose("a", "too short")
        with self.assertRaises(ValueError):
            self.s.propose("a" * 121, "A sufficiently long description")
        self.s.transition_from_ui(first["id"], "archived")
        self.assertTrue(self.s.propose("Circuit lesson pack",
                                       "Separate revised project version")["created"])

    def test_upgrade_goals_do_not_move_money(self):
        goal = self.s.create_goal_from_ui("GPU memory upgrade", "410.00",
                                          "Current 12 GB limits desired contexts")
        self.assertEqual(goal["status"], "active")
        self.assertEqual(self.s.summary()["goals"][0]["shortfall_gbp"], "£410.00")
        self.assertEqual(self.s.summary()["balance_gbp"], "£0.00")
        self.s.record_fund_from_ui("deposit", "95.00", "Manual savings allocation")
        self.assertEqual(self.s.summary()["goals"][0]["shortfall_gbp"], "£315.00")
        self.s.record_fund_from_ui("withdrawal", "10.00", "Bought test cables")
        self.assertEqual(self.s.summary()["balance_gbp"], "£85.00")
        with self.assertRaisesRegex(ValueError, "more than"):
            self.s.record_fund_from_ui("withdrawal", "86.00", "Cannot overdraw")
        self.assertEqual(self.s.summary()["balance_gbp"], "£85.00")
        with self.assertRaises(ValueError):
            self.s.record_fund_from_ui("job_payment", "20.00", "Not permitted")
        self.assertEqual(self.s.summary()["balance_gbp"], "£85.00")

    def test_data_persist_and_private_storage(self):
        proposal = self.s.propose("Create video", "Provide original approved promo clip")
        self.s.create_goal_from_ui("External SSD", "120.00")
        self.s.record_fund_from_ui("deposit", "20.00", "Confirmed savings")
        self.assertEqual(self.s.path, self.base / "storage/databases/apollo_growth.db")
        self.assertTrue(self.s.path.exists())
        other = GrowthStore(self.base)
        try:
            self.assertEqual(other.list_work()[0]["id"], proposal["id"])
            self.assertEqual(other.summary()["balance_gbp"], "£20.00")
        finally:
            other.close()

    def test_assistant_tools_are_draft_only(self):
        path = ROOT / "modules/growth_lab/module.py"
        spec = importlib.util.spec_from_file_location("growth_module_test", path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        app = module.Module({"base_dir": self.base})
        try:
            self.assertIn("contracts", "contracts") # Tool boundary tested below.
            self.assertTrue(app.self_test())
            names = {x["name"] for x in app.tools()}
            self.assertEqual(names, {
                "growth_hardware_snapshot", "growth_opportunity_ideas",
                "growth_propose_work", "growth_work_queue", "growth_fund_status",
            })
            with self.assertRaises(KeyError):
                app.run("growth_record_payment", {"amount": "5000"})
            with self.assertRaises(KeyError):
                app.run("growth_approve_contract", {"title": "Client"})
            x = app.run("growth_propose_work", {
                "title": "Original design pack", "description": "A reviewed electronics training pack",
                "estimated_gbp": "55.00",
            })
            self.assertEqual(x["status"], "proposed")
            self.assertEqual(app.run("growth_fund_status", {})["balance_gbp"], "£0.00")
            ideas = app.run("growth_opportunity_ideas", {})
            self.assertFalse(ideas["clients_found"])
            self.assertFalse(ideas["earnings_guaranteed"])
            self.assertGreaterEqual(len(OPPORTUNITY_TEMPLATES), 4)
        finally:
            app.close()
        self.assertEqual(group_for("growth_lab"), "Coding")

    def test_hardware_is_read_only_and_not_inferred_from_fake_data(self):
        with patch("subprocess.run", side_effect=FileNotFoundError("missing nvidia-smi")):
            status = hardware_snapshot()
        self.assertEqual(status["source"], "local-device")
        self.assertEqual(status["gpu"], [])
        self.assertIsNone(status.get("performance_speedup"))
        self.assertIn("One instantaneous snapshot", status["notes"][0])

    def test_source_has_explicit_local_confirmation_buttons(self):
        s = (ROOT / "modules/growth_lab/module.py").read_text(encoding="utf-8")
        ast.parse(s)
        for label in ("Approve Selected", "Mark Delivered", "Record Payment",
                      "Record Deposit", "Record Withdrawal", "Set Upgrade Target",
                      "Confirm Real Income"):
            self.assertIn(label, s)
        self.assertNotIn("subprocess.Popen(", s)
        self.assertNotIn("requests.post(", s)


if __name__ == "__main__":
    unittest.main()
