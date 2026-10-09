"""Pure-Python regression of Speech I/O worker state, without loading Qt/XTTS.

Extract the actual worker methods from the shipped source and execute them on
a minimal test instance. This keeps the test independent of PySide6/Coqui.
"""
import ast
import threading
import time
import unittest
import uuid
from pathlib import Path

SOURCE = Path(__file__).resolve().parents[1] / "modules" / "text_to_speech" / "module.py"


def build_speech_methods():
    tree = ast.parse(SOURCE.read_text(encoding="utf-8"), filename=str(SOURCE))
    parent = next(node for node in tree.body
                  if isinstance(node, ast.ClassDef) and node.name == "Module")
    names = {"_queue_voice_imprint", "_speech_status"}
    nodes = [node for node in parent.body
             if isinstance(node, ast.FunctionDef) and node.name in names]
    assert {node.name for node in nodes} == names
    klass = ast.ClassDef(name="SpeechUnderTest", bases=[], keywords=[],
                         body=nodes, decorator_list=[])
    scope = {"threading": threading, "time": time, "uuid": uuid}
    exec(compile(ast.fix_missing_locations(ast.Module(body=[klass], type_ignores=[])),
                 str(SOURCE), "exec"), scope)
    return scope["SpeechUnderTest"]


class SpeechQueueTests(unittest.TestCase):
    def make_speech(self, call):
        obj = build_speech_methods()()
        obj._imprint_worker_lock = threading.RLock()
        obj._imprint_worker_thread = None
        obj._imprint_pending = None
        obj._imprint_last_error = ""
        obj._imprint_generation = 0
        obj._imprint_status = {"state": "idle", "job_id": None, "updated_at": time.time()}
        obj._voice_imprint_call = call
        return obj

    def test_last_request_wins_and_job_terminates(self):
        running, release = threading.Event(), threading.Event()
        seen = []

        def speak(action, job):
            self.assertEqual(action, "speak")
            seen.append(job["text"])
            if job["text"] == "first":
                running.set()
                self.assertTrue(release.wait(3))

        obj = self.make_speech(speak)
        first = obj._queue_voice_imprint("first")
        self.assertTrue(running.wait(3))
        middle = obj._queue_voice_imprint("discard me")
        last = obj._queue_voice_imprint("last")
        self.assertTrue(middle["queued"])
        self.assertTrue(last["queued"])
        self.assertNotEqual(first["job_id"], last["job_id"])
        release.set()

        deadline = time.monotonic() + 4
        while time.monotonic() < deadline:
            with obj._imprint_worker_lock:
                worker = obj._imprint_worker_thread
                state = obj._imprint_status["state"]
            if worker is None and state == "completed":
                break
            time.sleep(0.01)
        self.assertEqual(seen, ["first", "last"])
        self.assertEqual(obj._speech_status()["state"], "completed")
        self.assertEqual(obj._speech_status()["job_id"], last["job_id"])

    def test_failure_is_terminal_and_recoverable(self):
        def broken(action, args):
            raise RuntimeError("GPU unavailable")
        obj = self.make_speech(broken)
        job = obj._queue_voice_imprint("speech")
        deadline = time.monotonic() + 3
        while obj._speech_status()["state"] not in {"failed"} and time.monotonic() < deadline:
            time.sleep(0.01)
        result = obj._speech_status()
        self.assertEqual(result["state"], "failed")
        self.assertEqual(result["job_id"], job["job_id"])
        self.assertIn("GPU unavailable", result["last_error"])


if __name__ == "__main__":
    unittest.main()
