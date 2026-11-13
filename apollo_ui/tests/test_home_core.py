"""Activity/playback regressions and real Qt smoke coverage for the Home core."""
from array import array
import ast
import importlib.util
import math
import os
from pathlib import Path
import tempfile
import threading
import time
import unittest
from unittest.mock import Mock, patch
import wave

from apollo_core_activity import CoreActivity, PlaybackEnvelope, resolve_activity, speech_motion_level
from apollo_runtime import ApolloRuntime

ROOT = Path(__file__).resolve().parents[1]
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


class ActivityTests(unittest.TestCase):
    def test_voice_generation_playback_and_completion_are_distinct(self):
        self.assertEqual(resolve_activity(speech={"generating": True}).state, "voice")
        self.assertEqual(resolve_activity(speech={"playing": True, "generating": True}, thinking=True).state, "speaking")
        self.assertEqual(resolve_activity(speech={"playing": False, "generating": False}).state, "idle")
        self.assertEqual(resolve_activity(listening=True, thinking=True).state, "listening")
        self.assertEqual(resolve_activity(thinking=True).state, "thinking")
        self.assertEqual(resolve_activity(tool="training_module__explore_web_and_save").state, "researching")
        self.assertEqual(resolve_activity(working=("file_builder__build",)).state, "working")
        self.assertEqual(resolve_activity(error="Ollama unavailable").state, "attention")
        self.assertIn("muted", resolve_activity(muted=True).detail)

    def test_pcm_silence_speech_end_and_stop(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "voice.wav"
            pcm = array("h", [0] * 800 + [int(12000 * math.sin(i * .2)) for i in range(800)])
            with wave.open(str(path), "wb") as output:
                output.setnchannels(1); output.setsampwidth(2); output.setframerate(8000)
                output.writeframes(pcm.tobytes())
            meter = PlaybackEnvelope()
            levels = meter.read(path)
            self.assertEqual(len(levels), 4)
            self.assertEqual(levels[:2], (0.0, 0.0))
            self.assertGreater(levels[2], .5)
            proc = Mock(); proc.poll.return_value = None
            with patch("apollo_core_activity.time.monotonic", return_value=10): meter.start(proc, levels)
            with patch("apollo_core_activity.time.monotonic", return_value=10.01):
                silent = meter.snapshot()
                self.assertTrue(silent["level_available"])
                self.assertEqual(silent["level"], 0)
            with patch("apollo_core_activity.time.monotonic", return_value=10.12):
                self.assertGreater(meter.snapshot()["level"], .5)
            proc.poll.return_value = 0
            self.assertEqual(meter.snapshot(), {"playing": False, "level": 0.0, "level_available": False})
            meter.stop()
            self.assertFalse(meter.snapshot()["playing"])
            self.assertEqual(meter.read(Path(folder) / "missing.wav"), ())

    def test_measured_silence_never_becomes_an_invented_syllable(self):
        for elapsed in (.1, .4, 1.5, 5.6):
            self.assertEqual(speech_motion_level(0, elapsed, available=True), 0)
            self.assertEqual(speech_motion_level(.7, elapsed, available=True), .7)
        self.assertEqual(speech_motion_level(2, .2, available=True), 1)
        self.assertGreater(speech_motion_level(0, .2, available=False), .5)
        activity = resolve_activity(speech={"playing": True, "level": 0, "level_available": True})
        self.assertTrue(activity.level_available)

    def test_only_in_flight_current_process_actions_animate_background_work(self):
        with tempfile.TemporaryDirectory() as folder:
            runtime = ApolloRuntime(folder)
            manager = Mock()
            manager.ollama_tools.return_value = []
            runtime.attach_manager(manager)
            entered, release = threading.Event(), threading.Event()
            errors = []
            def run_tool(*_):
                entered.set(); release.wait(3)
                raise RuntimeError("tool failed")
            manager._execute_tool_direct.side_effect = run_tool
            def call():
                try: runtime.execute_tool(manager, "demo__inspect", {}, actor="test")
                except Exception as exc: errors.append(exc)
            # The permission gate is kept active and granted only this fake tool.
            runtime.set_permission("demo__inspect", "allow")
            worker = threading.Thread(target=call); worker.start()
            try:
                self.assertTrue(entered.wait(3))
                self.assertEqual(runtime.active_capabilities(), ("demo__inspect",))
            finally:
                release.set(); worker.join(3)
            self.assertEqual(runtime.active_capabilities(), ())
            self.assertEqual(str(errors[0]), "tool failed")
            runtime.mark_clean_shutdown()


@unittest.skipUnless(importlib.util.find_spec("PySide6"), "Qt smoke checks run with desktop dependencies")
class HomeCoreWidgetTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from PySide6.QtWidgets import QApplication
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        from apollo_home_core import ApolloHomeCore
        self.panel = ApolloHomeCore()
        self.panel.resize(620, 450); self.panel.show(); self.app.processEvents()
        self.addCleanup(self.panel.close)

    def test_real_widgets_render_all_states_and_pause_animation(self):
        from PySide6.QtTest import QTest
        canvas = self.panel.canvas
        self.assertTrue(canvas.timer.isActive())
        phase = canvas._phase
        QTest.qWait(120)
        self.assertGreater(canvas._phase, phase)
        for state in ("idle", "thinking", "speaking", "voice", "listening", "working", "researching", "attention"):
            self.panel.set_activity(CoreActivity(state, state.title(), "Current activity", .8))
            self.assertFalse(self.panel.grab().isNull())
            self.assertEqual(self.panel.title.text(), state.title())
        self.panel.motion.click()
        self.assertFalse(canvas.timer.isActive())
        phase = canvas._phase
        QTest.qWait(120)
        self.assertEqual(canvas._phase, phase)
        self.panel.motion.click()
        self.assertTrue(canvas.timer.isActive())
        self.panel.hide(); self.app.processEvents()
        self.assertFalse(canvas.timer.isActive())
        self.panel.show(); self.app.processEvents()
        self.assertTrue(canvas.timer.isActive())
        # Controls fit the content width of Apollo's minimum desktop window.
        for control in (self.panel.chat, self.panel.listen, self.panel.mute, self.panel.motion):
            self.assertTrue(self.panel.rect().contains(control.geometry()))

    def test_home_observes_xtts_queue_playback_chat_and_failure_without_tools(self):
        # Execute the actual window observer without booting unrelated modules.
        source = ast.parse((ROOT / "main.py").read_text(encoding="utf-8"))
        parent = next(n for n in source.body if isinstance(n, ast.ClassDef) and n.name == "ApolloWindow")
        method = next(n for n in parent.body if isinstance(n, ast.FunctionDef) and n.name == "_refresh_home_core")
        scope = {"time": time, "resolve_activity": resolve_activity}
        exec(compile(ast.fix_missing_locations(ast.Module(body=[method], type_ignores=[])), "main.py", "exec"), scope)
        host = Mock()
        host.chat_wake = Mock(enabled=False, capturing=False)
        host.isMinimized.return_value = False
        host.home_core = self.panel; host._core_error = ("", 0); host._core_tool = ""
        host.chat_busy = True; host.speech_task = None; host.stt_task = None; host.speech_muted = False
        host.client.model = "test-local-model"
        host.runtime.active_capabilities.return_value = ()
        host.chat_workspace = Mock(active_core_tool="")
        host.chat_workspace.session_store.temporary = False
        host.chat_workspace.turn_client.model = "test-local-model"
        speech = Mock(); speech._speech_process = None
        speech._speech_status.return_value = {"worker_alive": False, "state": "idle"}
        trainer = Mock(); trainer.playback_activity.return_value = {"playing": False, "level": 0}
        host.module_manager.get_module.side_effect = lambda mid: {
            "enabled": True, "instance": speech if mid == "text_to_speech" else trainer}
        refresh = lambda: scope["_refresh_home_core"](host)
        refresh(); self.assertEqual(self.panel.canvas.activity.state, "thinking")
        host.chat_workspace.active_core_tool = "web_explorer__search"
        refresh(); self.assertEqual(self.panel.canvas.activity.state, "researching")
        host.chat_workspace.active_core_tool = ""; host.chat_busy = False
        speech._speech_status.return_value = {"worker_alive": True, "state": "generating"}
        refresh(); self.assertEqual(self.panel.canvas.activity.state, "voice")
        speech._speech_status.return_value = {"worker_alive": False, "state": "completed"}
        trainer.playback_activity.return_value = {"playing": True, "level": .8, "level_available": True}
        refresh(); self.assertEqual(self.panel.canvas.activity.state, "speaking")
        self.assertTrue(self.panel.canvas.activity.level_available)
        trainer.playback_activity.return_value = {"playing": False, "level": 0}
        refresh(); self.assertEqual(self.panel.canvas.activity.state, "idle")
        host._core_error = ("Voice failed", time.monotonic() + 10)
        refresh(); self.assertEqual(self.panel.canvas.activity.state, "attention")
        host._core_error = ("Voice failed", 0)
        refresh(); self.assertEqual(self.panel.canvas.activity.state, "idle")
        host.module_manager.execute.assert_not_called()

    def test_slow_rings_and_speech_waves_close_in_silence(self):
        canvas = self.panel.canvas
        canvas.timer.stop()
        canvas.set_activity(CoreActivity("speaking", "Speaking", "", .9, True))
        canvas._last_tick = 100
        angle = canvas._ring_angle
        with patch("apollo_home_core.time.monotonic", return_value=100.04): canvas._tick()
        self.assertAlmostEqual(canvas._ring_angle - angle, .24, places=5)  # 6 degrees/second
        for i in range(2, 12):
            with patch("apollo_home_core.time.monotonic", return_value=100 + i * .04): canvas._tick()
        self.assertGreater(canvas._level, .89)
        elapsed = canvas._elapsed
        canvas.set_activity(CoreActivity("speaking", "Speaking", "", 0, True))
        for i in range(12, 30):
            with patch("apollo_home_core.time.monotonic", return_value=100 + i * .04): canvas._tick()
        self.assertLess(canvas._level, .001)
        self.assertGreater(canvas._elapsed, elapsed)
        self.assertFalse(canvas.grab().isNull())


if __name__ == "__main__": unittest.main()
