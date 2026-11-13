"""Offline Windows wake phrase + one utterance; cancellable microphone ownership.

No audio files, ambient transcripts, cloud calls or model inference. Only the
matched phrase and following message enter a small in-memory event queue.
"""
import base64
import json
import os
import queue
import re
import shutil
import subprocess
import sys
import threading
import time


def normalize_wake_word(value):
    word = " ".join(str(value or "apollo").casefold().split())
    if not re.fullmatch(r"[a-z]+(?: [a-z]+){0,2}", word) or len(word) > 32:
        raise ValueError("Use one to three English words for the wake phrase.")
    return word


def matches_wake(text, word, confidence):
    phrase = " ".join(str(text or "").casefold().split())
    return float(confidence or 0) >= .75 and phrase in (word, "hey " + word)


WAKE_SCRIPT = r"""
$ErrorActionPreference = 'Stop'
[Console]::OutputEncoding = New-Object System.Text.UTF8Encoding($false)
Add-Type -AssemblyName System.Speech
$r = $null
$command = $null
try {
    $infos = @([System.Speech.Recognition.SpeechRecognitionEngine]::InstalledRecognizers())
    $info = $infos | Where-Object { $_.Culture.Name -eq [System.Globalization.CultureInfo]::CurrentUICulture.Name } | Select-Object -First 1
    if ($null -eq $info) { $info = $infos | Where-Object { $_.Culture.TwoLetterISOLanguageName -eq 'en' } | Select-Object -First 1 }
    if ($null -eq $info -or $info.Culture.TwoLetterISOLanguageName -ne 'en') { throw 'Install an English Windows speech recognition language pack.' }
    $r = New-Object System.Speech.Recognition.SpeechRecognitionEngine($info)
    $choices = New-Object System.Speech.Recognition.Choices
    $choices.Add([string[]]@($env:APOLLO_WAKE_WORD, ('hey ' + $env:APOLLO_WAKE_WORD)))
    $b = New-Object System.Speech.Recognition.GrammarBuilder
    $b.Culture = $info.Culture
    $b.Append($choices)
    $g = New-Object System.Speech.Recognition.Grammar($b)
    $r.LoadGrammar($g)
    $r.BabbleTimeout = [TimeSpan]::FromSeconds(3)
    $r.EndSilenceTimeout = [TimeSpan]::FromMilliseconds(650)
    $r.SetInputToDefaultAudioDevice()
    [Console]::WriteLine('{"kind":"ready"}')
    $deadline = [DateTime]::UtcNow.AddSeconds(60)
    while ([DateTime]::UtcNow -lt $deadline) {
        $result = $r.Recognize([TimeSpan]::FromSeconds(1))
        if ($null -eq $result -or $result.Confidence -lt 0.75) { continue }
        [Console]::WriteLine((@{kind='wake'; phrase=$result.Text; confidence=$result.Confidence} | ConvertTo-Json -Compress))
        $r.UnloadAllGrammars()
        $r.LoadGrammar((New-Object System.Speech.Recognition.DictationGrammar))
        $r.BabbleTimeout = [TimeSpan]::FromSeconds(12)
        $r.EndSilenceTimeout = [TimeSpan]::FromMilliseconds(1100)
        $utterance = $r.Recognize([TimeSpan]::FromSeconds(8))
        $text = if ($null -ne $utterance) { $utterance.Text } else { '' }
        $command = @{kind='command'; text=$text}
        break
    }
} catch {
    [Console]::WriteLine((@{kind='error'; message=$_.Exception.Message} | ConvertTo-Json -Compress))
} finally {
    if ($null -ne $r) { $r.Dispose() }
}
if ($null -ne $command) { [Console]::WriteLine(($command | ConvertTo-Json -Compress)) }
"""


class WakeWordMonitor:
    def __init__(self, process_factory=None, supported=None):
        self._factory = process_factory or subprocess.Popen
        self._supported = supported if supported is not None else sys.platform == 'win32' and bool(shutil.which('powershell.exe'))
        self._lock = threading.RLock()
        self._stop = threading.Event()
        self._paused = True
        self._thread = self._process = None
        self._generation = 0
        self._state, self._error = 'off', ''
        self._events = queue.Queue(maxsize=8)

    def snapshot(self):
        with self._lock:
            return {'state': self._state, 'error': self._error,
                    'running': bool(self._thread and self._thread.is_alive()),
                    'microphone_open': self._process is not None,
                    'supported': bool(self._supported)}

    def start(self, word='apollo'):
        word = normalize_wake_word(word)
        if not self._supported:
            raise RuntimeError('Wake word needs Windows PowerShell and an English Windows speech recognizer.')
        with self._lock:
            if self._thread and self._thread.is_alive():
                if self._stop.is_set():
                    raise RuntimeError('Microphone is stopping; try enabling Wake word again in a moment.')
                return
            self._word = word
            self._stop.clear(); self._paused = True
            self._state, self._error = 'paused', ''
            self._thread = threading.Thread(target=self._loop, name='ApolloWakeWord', daemon=True)
            self._thread.start()

    def set_paused(self, paused):
        with self._lock:
            if self._paused == bool(paused): return
            self._paused = bool(paused)
            if paused: self._generation += 1
            process = self._process if paused else None
        self._terminate(process)

    def stop(self):
        with self._lock:
            self._stop.set(); self._paused = True; self._generation += 1
            process = self._process; self._state = 'off'
        self._terminate(process)
        self.drain_events()

    def close(self):
        self.stop()
        thread = self._thread
        if thread and thread is not threading.current_thread(): thread.join(timeout=2.5)

    def drain_events(self):
        events = []
        while True:
            try: event = self._events.get_nowait()
            except queue.Empty: break
            if event['generation'] == self._generation: events.append(event)
        return events

    @staticmethod
    def _terminate(process):
        if process is not None and process.poll() is None:
            try: process.terminate()
            except OSError: pass

    def _emit(self, event, generation):
        if self._stop.is_set() or generation != self._generation: return
        try: self._events.put_nowait({**event, 'generation': generation})
        except queue.Full: pass

    def _loop(self):
        while not self._stop.is_set():
            with self._lock: paused = self._paused
            if paused:
                with self._lock:
                    if self._state not in ('off', 'error', 'handoff'): self._state = 'paused'
                self._stop.wait(.1)
                continue
            try: self._listen_window()
            except Exception as exc:
                if not self._stop.is_set() and not self._paused:
                    with self._lock: self._state, self._error = 'error', str(exc)[:220]
                    self._stop.set()
                    break

    def _listen_window(self):
        with self._lock:
            generation = self._generation; self._state = 'starting'
        env = os.environ.copy(); env['APOLLO_WAKE_WORD'] = self._word
        encoded = base64.b64encode(WAKE_SCRIPT.encode('utf-16-le')).decode('ascii')
        process = self._factory(
            ['powershell.exe', '-NoProfile', '-NonInteractive', '-EncodedCommand', encoded],
            env=env, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, stdin=subprocess.DEVNULL,
            text=True, encoding='utf-8', errors='replace', creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
        with self._lock: self._process = process
        lines = queue.Queue(maxsize=32)
        def read_lines():
            try:
                for line in process.stdout:
                    try: lines.put(line, timeout=.1)
                    except queue.Full: break
            finally:
                try: lines.put_nowait(None)
                except queue.Full: pass
        reader = threading.Thread(target=read_lines, name='ApolloWakeOutput', daemon=True); reader.start()
        started = time.monotonic(); ready = woke = False; command = None; capture_started = None
        try:
            while not self._stop.is_set() and not self._paused and generation == self._generation:
                if time.monotonic() - started > (85 if woke else 72 if ready else 15):
                    raise RuntimeError('Wake-word microphone startup/capture timed out.')
                if capture_started is not None and time.monotonic() - capture_started > 20:
                    raise RuntimeError('Voice message reached the 20-second capture limit.')
                try: line = lines.get(timeout=.1)
                except queue.Empty: continue
                if line is None:
                    if not ready: raise RuntimeError('Windows speech recognizer did not start. Check microphone permissions and language pack.')
                    break
                try: event = json.loads(line.lstrip('\ufeff'))
                except ValueError: continue
                if event.get('kind') == 'error': raise RuntimeError(event.get('message') or 'Windows recognition failed')
                if event.get('kind') == 'ready':
                    ready = True
                    with self._lock: self._state = 'listening'
                elif event.get('kind') == 'wake' and matches_wake(event.get('phrase'), self._word, event.get('confidence')):
                    woke = True
                    capture_started = time.monotonic()
                    with self._lock: self._state = 'capturing'
                    self._emit({'kind': 'wake'}, generation)
                elif event.get('kind') == 'command' and woke:
                    command = str(event.get('text') or '')[:12000]; break
        finally:
            self._terminate(process)
            try: process.wait(timeout=1)
            except subprocess.TimeoutExpired:
                process.kill(); process.wait(timeout=1)
            reader.join(timeout=.2); process.stdout.close()
            with self._lock:
                if self._process is process: self._process = None
        # Deliver text only after the recognizer has released the microphone.
        if woke and not self._stop.is_set() and generation == self._generation:
            with self._lock: self._paused = True; self._state = 'handoff'
            self._emit({'kind': 'command', 'text': command or ''}, generation)
