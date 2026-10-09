"""Regression checks for the XTTS subprocess protocol, without Coqui or Qt.

The tests use only the Python standard library and MUST NOT load any model.
"""
import ast
import io
import json
import queue
import subprocess
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
WORKER = ROOT / "modules" / "voice_imprint_trainer" / "xtts_worker.py"
CONTROLLER = ROOT / "modules" / "voice_imprint_trainer" / "module.py"
PREFIX = "APOLLO_XTTS_JSON "


def controller_reader():
    """Isolate the actual reader method; GUI dependencies are not imported."""
    tree = ast.parse(CONTROLLER.read_text(encoding="utf-8"), filename=str(CONTROLLER))
    module_class = next(
        node for node in tree.body
        if isinstance(node, ast.ClassDef) and node.name == "Module"
    )
    method = next(
        node for node in module_class.body
        if isinstance(node, ast.FunctionDef) and node.name == "_xtts_worker_reader_loop"
    )
    cls = ast.ClassDef(
        name="ReaderUnderTest", bases=[], keywords=[],
        body=[method], decorator_list=[],
    )
    scope = {"json": json}
    exec(compile(ast.fix_missing_locations(ast.Module(body=[cls], type_ignores=[])),
                 str(CONTROLLER), "exec"), scope)
    return scope["ReaderUnderTest"]()


class FakeProcess:
    def __init__(self, text):
        self.stdout = io.StringIO(text)

    def poll(self):
        return 0


class XTTSWorkerProtocolTests(unittest.TestCase):
    def run_worker(self, messages):
        process = subprocess.run(
            [sys.executable, "-u", str(WORKER)],
            input="\n".join(messages) + "\n",
            capture_output=True,
            text=True,
            timeout=20,
            cwd=str(ROOT),
        )
        self.assertEqual(process.returncode, 0, process.stderr)
        lines = [line for line in process.stdout.splitlines() if line.strip()]
        self.assertTrue(lines, process.stderr)
        self.assertTrue(all(line.startswith(PREFIX) for line in lines), lines)
        return [json.loads(line[len(PREFIX):]) for line in lines]

    def test_ping_and_shutdown_reply_in_expected_frame(self):
        frames = self.run_worker([
            json.dumps({"id": "hello", "op": "ping"}),
            json.dumps({"id": "bye", "op": "shutdown"}),
        ])
        self.assertEqual([frame["id"] for frame in frames], ["hello", "bye"])
        self.assertTrue(all(frame["ok"] for frame in frames))
        self.assertEqual(frames[0]["result"]["status"], "ready")

    def test_invalid_input_returns_error_without_crashing(self):
        frames = self.run_worker([
            "{not json",
            json.dumps({"id": "recover", "op": "ping"}),
            json.dumps({"id": "bye", "op": "shutdown"}),
        ])
        self.assertEqual(len(frames), 3)
        self.assertFalse(frames[0]["ok"])
        self.assertIsNone(frames[0]["id"])
        self.assertEqual(frames[1]["id"], "recover")
        self.assertTrue(frames[1]["ok"])

    def test_parent_reader_accepts_framed_and_legacy_json(self):
        first = {"id": "one", "ok": True, "result": {"status": "ready"}}
        second = {"id": "two", "ok": False, "error": "load failed"}
        data = ("Library banner\n"
                + PREFIX + json.dumps(first) + "\n"
                + json.dumps(second) + "\n"
                + json.dumps({"unrelated": "noise"}) + "\n")
        received = queue.Queue()
        controller_reader()._xtts_worker_reader_loop(FakeProcess(data), received)
        self.assertEqual(received.get_nowait(), first)
        self.assertEqual(received.get_nowait(), second)
        self.assertEqual(received.get_nowait()["_worker_exit"], True)
        self.assertTrue(received.empty())


if __name__ == "__main__":
    unittest.main()
