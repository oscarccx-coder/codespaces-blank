"""Static GUI safety checks for System Job History and voice cancellation."""
import ast
import unittest
from pathlib import Path


class SystemJobWiringTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = (Path(__file__).resolve().parents[1] / "main.py").read_text(encoding="utf-8")
        cls.tree = ast.parse(cls.source)
        window = next(x for x in cls.tree.body
                      if isinstance(x, ast.ClassDef) and x.name == "ApolloWindow")
        cls.methods = {x.name for x in window.body if isinstance(x, ast.FunctionDef)}

    def test_expected_methods(self):
        for method in ("refresh_job_history", "_show_selected_job", "stop_voice_job"):
            self.assertIn(method, self.methods)

    def test_runtime_history_and_non_blocking_cancel(self):
        self.assertIn("self.runtime.task_history(40)", self.source)
        self.assertIn('task = ModuleActionTask(self.module_manager, "text_to_speech", "stop_speaking", {})', self.source)
        self.assertIn("self.thread_pool.start(task)", self.source)
        self.assertIn("self.system_jobs_timer.start()", self.source)


if __name__ == "__main__":
    unittest.main()
