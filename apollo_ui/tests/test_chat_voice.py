"""Wake microphone lifecycle, scoped Chat handoff and native transition checks."""
import base64
import importlib.util
import json
import queue
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch
from apollo_wake_word import WakeWordMonitor, matches_wake, normalize_wake_word, WAKE_SCRIPT
from apollo_chat_voice import ChatWakeController
from modules.voice_agent.module import Module


class Pipe:
    def __init__(self, events):
        self.items = queue.Queue()
        for event in events: self.items.put(json.dumps(event) + '\n')
    def __iter__(self): return self
    def __next__(self):
        value = self.items.get(timeout=3)
        if value is None: raise StopIteration
        return value
    def close(self): pass


class Process:
    def __init__(self, events):
        self.stdout = Pipe(events); self.returncode = None; self.stopped = threading.Event()
    def poll(self): return self.returncode
    def terminate(self):
        self.returncode = 0; self.stopped.set(); self.stdout.items.put(None)
    def kill(self): self.terminate()
    def wait(self, timeout=1):
        if not self.stopped.wait(timeout): raise subprocess.TimeoutExpired('fake', timeout)
        return self.returncode


class WakeTests(unittest.TestCase):
    def wait_for(self, predicate):
        until = time.monotonic() + 3
        while not predicate() and time.monotonic() < until: time.sleep(.01)
        self.assertTrue(predicate())

    def test_exact_phrase_confidence_and_no_shell_interpolation(self):
        self.assertTrue(matches_wake('Hey Apollo', 'apollo', .9))
        for text in ('apollonian', 'do not say apollo', 'apollo change settings'):
            self.assertFalse(matches_wake(text, 'apollo', .99))
        self.assertFalse(matches_wake('Apollo', 'apollo', .5))
        with self.assertRaises(ValueError): normalize_wake_word('apollo; Start-Process cmd')
        self.assertIn('$env:APOLLO_WAKE_WORD', WAKE_SCRIPT)
        self.assertNotIn('SetOutputToWaveFile', WAKE_SCRIPT)

    def test_mic_released_before_command_and_stop_clears_events(self):
        proc = Process([{'kind':'ready'}, {'kind':'wake','phrase':'Apollo','confidence':.9}, {'kind':'command','text':'Test message'}])
        factory = Mock(return_value=proc)
        monitor = WakeWordMonitor(factory, supported=True); self.addCleanup(monitor.close)
        monitor.start(); self.assertFalse(factory.called)  # Starts paused, owned by UI controller.
        monitor.set_paused(False)
        self.wait_for(lambda: monitor.snapshot()['state']=='handoff')
        self.assertFalse(monitor.snapshot()['microphone_open'])
        self.assertTrue(proc.stopped.is_set())
        events=monitor.drain_events()
        self.assertEqual([e['kind'] for e in events], ['wake','command'])
        self.assertEqual(events[-1]['text'], 'Test message')
        self.assertEqual(factory.call_args.kwargs['env']['APOLLO_WAKE_WORD'], 'apollo')
        monitor.stop(); self.assertEqual(monitor.drain_events(), [])

    def test_pause_during_capture_discards_late_text(self):
        proc=Process([{'kind':'ready'},{'kind':'wake','phrase':'Apollo','confidence':.9}])
        monitor=WakeWordMonitor(Mock(return_value=proc), supported=True); self.addCleanup(monitor.close)
        monitor.start(); monitor.set_paused(False)
        self.wait_for(lambda: monitor.snapshot()['state']=='capturing')
        monitor.set_paused(True)
        self.wait_for(lambda: not monitor.snapshot()['microphone_open'])
        self.assertEqual(monitor.drain_events(), [])

    def test_start_is_opt_in_and_missing_backend_fails_closed(self):
        with tempfile.TemporaryDirectory() as folder:
            module=Module({'base_dir':folder}); self.addCleanup(module.close)
            with self.assertRaises(PermissionError): module.run('start_listening',{})
            with self.assertRaises(PermissionError): module.run('set_voice_agent_settings',{'enabled':True})
            module.monitor=WakeWordMonitor(supported=False)
            with self.assertRaises(RuntimeError): module.enable_from_ui(True)
            self.assertFalse(module.owner_enabled)

    @unittest.skipUnless(sys.platform=='win32', 'Windows parser check')
    def test_windows_powershell_syntax(self):
        encoded=base64.b64encode(WAKE_SCRIPT.encode('utf-8')).decode()
        parser="$s=[Text.Encoding]::UTF8.GetString([Convert]::FromBase64String('"+encoded+"')); $t=$null; $e=$null; [void][System.Management.Automation.Language.Parser]::ParseInput($s,[ref]$t,[ref]$e); if ($e.Count) { $e | Out-String | Write-Output; exit 1 }"
        result=subprocess.run(['powershell.exe','-NoProfile','-NonInteractive','-EncodedCommand',base64.b64encode(parser.encode('utf-16-le')).decode()],capture_output=True,text=True,timeout=30)
        self.assertEqual(result.returncode,0,result.stdout+result.stderr)


class ControllerTests(unittest.TestCase):
    def setUp(self):
        self.monitor=Mock(); self.monitor.snapshot.return_value={'state':'listening','supported':True,'error':'','microphone_open':True}
        self.monitor.drain_events.return_value=[]
        self.agent=Mock(owner_enabled=True, monitor=self.monitor)
        self.agent.enable_from_ui.side_effect=lambda enabled: setattr(self.agent,'owner_enabled',enabled)
        self.workspace=SimpleNamespace(core_header=Mock(),session_store=SimpleNamespace(temporary=False),chat_id='first',io_busy=False,status=Mock(),composer=Mock())
        self.workspace.composer.text.return_value='Typed draft'
        self.owner=SimpleNamespace(chat_workspace=self.workspace,module_manager=Mock(),runtime=Mock(),speech_task=None,stt_task=None,chat_busy=False,_stt_waiting_for_wake=False,_closing=False,_core_error=('',0),statusBar=Mock(return_value=Mock()),switch_page=Mock(),isMinimized=lambda:False)
        self.owner.module_manager.get_module.return_value={'enabled':True,'instance':self.agent}
        self.owner.runtime.get_permission.return_value='allow'
        self.controller=ChatWakeController(self.owner); self.controller.agent=self.agent

    def test_opens_chat_preserves_typed_draft_and_never_sends(self):
        self.monitor.drain_events.return_value=[{'kind':'wake'},{'kind':'command','text':'Voice request'}]
        self.controller.pump({})
        self.owner.switch_page.assert_called_once_with('Chat')
        self.workspace.composer.setText.assert_called_once_with('Typed draft\nVoice request')
        self.assertIn('review',self.workspace.status.setText.call_args.args[0])

    def test_playback_temporary_chat_and_busy_block_capture(self):
        for speech,temporary,busy in [({'playing':True},False,False),({},True,False),({},False,True)]:
            self.controller.hold_until=0
            self.workspace.session_store.temporary=temporary; self.owner.chat_busy=busy
            self.monitor.drain_events.return_value=[{'kind':'wake'},{'kind':'command','text':'Must not appear'}]
            self.controller.pump(speech)
            self.monitor.set_paused.assert_called_with(True)
        self.workspace.composer.setText.assert_not_called()

    def test_switched_chat_and_revoked_permission_do_not_deliver(self):
        self.controller.target=(self.workspace.session_store,'old-chat')
        self.monitor.drain_events.return_value=[{'kind':'command','text':'Private message'}]
        self.controller.pump({}); self.workspace.composer.setText.assert_not_called()
        self.owner.runtime.get_permission.return_value='deny'
        self.controller.pump({})
        self.agent.enable_from_ui.assert_called_with(False)


if __name__=='__main__': unittest.main()
