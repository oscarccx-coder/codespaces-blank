"""Tests of ordinary Apollo chat income planning and explicit-only Pile access.

No PySide6, Ollama, The Pile, network or external account is needed.
"""
import ast
import re
from pathlib import Path
import unittest

from apollo_growth_chat import (
    FALLBACK_IDEAS, explicit_pile_command, growth_advice, wants_growth_advice,
)

ROOT = Path(__file__).resolve().parents[1]
WORKERS = ROOT / "workers.py"


def router_class():
    tree = ast.parse(WORKERS.read_text(encoding="utf-8"), filename=str(WORKERS))
    original = next(node for node in tree.body
                    if isinstance(node, ast.ClassDef) and node.name == "ChatTask")
    want = {
        "_last_user_text", "_resolved_user_request", "_is_retry_phrase",
        "_is_meaningful_prior_request", "_previous_meaningful_user_request",
        "_pile_query_from_text", "_explicit_pile_directive",
        "_run_growth_advice", "_select_tools",
    }
    methods = [node for node in original.body
               if isinstance(node, ast.FunctionDef) and node.name in want]
    missing = want - {m.name for m in methods}
    assert not missing, missing
    cls = ast.ClassDef(
        name="Router", bases=[], keywords=[], body=methods, decorator_list=[]
    )
    code = ast.fix_missing_locations(ast.Module(body=[cls], type_ignores=[]))
    scope = {
        "re": re, "explicit_pile_command": explicit_pile_command,
        "wants_growth_advice": wants_growth_advice, "growth_advice": growth_advice,
    }
    exec(compile(code, str(WORKERS), "exec"), scope)
    return scope["Router"]


class Signals:
    class Chunk:
        def __init__(self):
            self.calls = []

        def emit(self, value):
            self.calls.append(value)

    def __init__(self):
        self.chunk = self.Chunk()


class GrowthManager:
    def __init__(self, *, failing=False):
        self.failing = failing
        self.calls = []

    def ollama_tools(self):
        return [
            {"type": "function", "function": {"name": "pile_knowledge__search_pile"}},
            {"type": "function", "function": {"name": "pile_knowledge__learn_from_pile"}},
            {"type": "function", "function": {"name": "growth_lab__growth_opportunity_ideas"}},
            {"type": "function", "function": {"name": "growth_lab__growth_fund_status"}},
        ]

    def execute_tool(self, name, args):
        self.calls.append((name, args))
        if self.failing:
            raise RuntimeError("Growth Lab is offline")
        if name == "growth_lab__growth_opportunity_ideas":
            return {"opportunities": [{"title": "Testable spreadsheet product",
                                        "category": "Spreadsheet",
                                        "deliverable": "A tested workbook"}]}
        if name == "growth_lab__growth_fund_status":
            return {"balance_gbp": "£15.00", "goals": [
                {"title": "More VRAM", "shortfall_gbp": "£150.00"}]}
        raise AssertionError("No Pile calls or writes permitted")


class GrowthChatRoutingTests(unittest.TestCase):
    def make_router(self, current, older=None, manager=None):
        router = router_class()()
        router.messages = ([{"role": "user", "content": older}] if older else []) + [
            {"role": "user", "content": current}
        ]
        router.module_manager = manager
        router.signals = Signals()
        router._allowed_tool_names = (
            lambda tools: {x["function"]["name"] for x in tools}
        )
        return router

    def test_user_original_request_goes_to_income_planning(self):
        ask = ("you need to learn to make money so we can use it to improve you "
               "what can you do as an ai to do this")
        self.assertTrue(wants_growth_advice(ask))
        mgr = GrowthManager()
        chat = self.make_router(ask, older="learn from the Pile on physics", manager=mgr)
        self.assertIsNone(chat._explicit_pile_directive())
        selected = chat._select_tools(mgr.ollama_tools())
        self.assertEqual({t["function"]["name"] for t in selected},
                         {"growth_lab__growth_opportunity_ideas", "growth_lab__growth_fund_status"})
        text = chat._run_growth_advice()
        self.assertIn("Testable spreadsheet product", text)
        self.assertIn("£15.00", text)
        self.assertIn("manual Growth Lab ledger", text)
        self.assertIn("no authority", text)
        self.assertEqual(len(mgr.calls), 2)
        self.assertTrue(all(name.startswith("growth_lab__") for name, _ in mgr.calls))
        self.assertEqual(chat.signals.chunk.calls, [text])

    def test_pasted_pile_error_must_not_trigger_pile(self):
        current = (
            "Apollo says the pile_knowledge__search_pile tool failed. "
            "It tried to learn how to earn money from The Pile. "
            "Why does normal chat do that?"
        )
        chat = self.make_router(current)
        self.assertIsNone(explicit_pile_command(current))
        self.assertIsNone(chat._explicit_pile_directive())

    def test_explicit_requests_still_work(self):
        for utterance, expected in (
            ("learn from The Pile advanced AI coding", "learn"),
            ("please search the pile for robotics", "search"),
            ("study The Pile on reasoning", "learn"),
        ):
            with self.subTest(utterance=utterance):
                chat = self.make_router(utterance)
                self.assertEqual(chat._explicit_pile_directive()["mode"], expected)
                self.assertTrue(chat._explicit_pile_directive()["query"])
        self.assertIsNone(explicit_pile_command("why did Apollo search the pile?"))

    def test_offline_growth_lab_still_provides_workable_ideas(self):
        mgr = GrowthManager(failing=True)
        chat = self.make_router("How can Apollo make money to fund upgrades?", manager=mgr)
        text = chat._run_growth_advice()
        self.assertIn(FALLBACK_IDEAS[0]["title"], text)
        self.assertIn("not guaranteed earnings", text.lower())
        self.assertNotIn("£15.00", text)
        self.assertFalse(any(name.startswith("pile_knowledge") for name, _ in mgr.calls))

    def test_no_money_request_means_no_auto_business_answer(self):
        chat = self.make_router("Hi, can you explain Python functions?")
        self.assertFalse(wants_growth_advice(chat._last_user_text()))
        self.assertIsNone(chat._run_growth_advice())
        self.assertEqual(chat.signals.chunk.calls, [])

    def test_income_plan_does_not_claim_income_or_mutate_fund(self):
        response = growth_advice(fund={"balance_gbp": "£0.00"})
        for statement in ("not guaranteed", "no authority", "manual Growth Lab ledger"):
            self.assertIn(statement, response.lower() if statement == "not guaranteed" else response)
        self.assertNotIn("I have made money", response)
        self.assertNotIn("bank transfer initiated", response)

    def test_current_request_does_not_inherit_previous_gadgets(self):
        manager = GrowthManager()
        chat = self.make_router("hello", older="search the pile for neural networks", manager=manager)
        self.assertEqual(chat._select_tools(manager.ollama_tools()), [])
        self.assertIsNone(chat._explicit_pile_directive())

    def test_routing_is_wired_before_general_tool_loop(self):
        source = WORKERS.read_text(encoding="utf-8")
        # Compare ordering inside the ordinary chat controller, not earlier
        # module-build methods that have their own unrelated tool catalogues.
        controller = source[source.index("    def _run_with_modules(self):"):]
        self.assertLess(
            controller.index("direct_growth = self._run_growth_advice()"),
            controller.index("        all_tools = ("),
        )
        self.assertNotIn('        text = self._request_text()\n        lower = text.lower()', source[
            source.index("    def _select_tools("):source.index("    @staticmethod\n    def _fingerprint")
        ])


if __name__ == "__main__":
    unittest.main()
