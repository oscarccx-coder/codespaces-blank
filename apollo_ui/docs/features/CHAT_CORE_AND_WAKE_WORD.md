# Chat core and wake word

The green Home core is also shown on Chat. When Chat opens, it starts larger,
shrinks into a 100-pixel header over 480 ms, and the conversation fades in.
Breathing, rings and speech waves remain animated while typing. Moving from
Home carries the animation phase into Chat instead of restarting it. Reduce
motion disables the entry/fade animation and the continuous core animation.
Fade effects are removed after entry; hidden cores stop their frame timers.

## Wake word

On Windows, enable **Wake word: Apollo** in the Chat header for the current
application session. Say **Apollo** or **Hey Apollo**, pause, then speak your
message. Apollo opens Chat, captures the following utterance, and places it in
the composer. Review it, then press Send. An existing typed draft is preserved;
captured speech is appended. It never sends an instruction automatically.

The microphone status is visible in the header. Uncheck the same control to
stop it, or use the permanent **Stop wake word** button on any Apollo page.
Every application launch starts with wake listening off. If Voice Agent
is disabled, enable it in Modules. The backend needs Windows PowerShell and an
installed English Windows System.Speech recognizer, with desktop microphone
access enabled in Windows privacy settings. Other platforms display the
unsupported state without attempting to open a device or install anything.

Wake detection uses a constrained local phrase grammar and a confidence
threshold of 0.75. It matches the complete phrase, not arbitrary substrings.
The recognizer switches to dictation only after a wake match. A 20-second
supervisor limit bounds the following capture, including silence. Starting
the microphone has a separate 15-second watchdog. A visible error turns the
listener off; no retry storm or automatic package/model download is performed.

The listener pauses during model replies, voice generation/playback, manual
dictation, file imports and temporary chats. An 800 ms guard after playback
reduces the chance of hearing Apollo's own speaker echo. This is half-duplex:
it does not implement speaking over Apollo to interrupt him. A changed chat or
stale/cancelled generation discards the captured message instead of inserting
it in a different conversation. Module disable, permission revocation and app
shutdown stop wake listening. Manual Dictate waits for the wake microphone to
be released before using its existing recorder.

Wake listening does not write ambient audio, transcripts or training samples,
and makes no cloud/model calls. Only the wake notification and following
message pass through a bounded in-memory queue. The worker owns and disposes
its Windows recognizer before delivering the message. Explicitly pressing Send
uses the normal Chat history/memory/tools settings and permission gate.
Ordinary manual Dictate retains its existing separate save-dictation setting.

`voice_agent` is the single canonical service. Its tools cannot opt the owner
into microphone use; the UI must enable it first. Persisted legacy `enabled`
values do not automatically activate a microphone after an update/restart.

## Validation and limitations

Run `python -m unittest -v tests.test_chat_voice tests.test_home_core tests.test_chat_workspace`.
Tests exercise fake-process stop/release, exact phrase/confidence, stale-event
discard, reply/privacy pauses, draft preservation, source syntax and real Qt
entry/opacity cleanup/typing/reduced-motion behavior. Windows CI also parses
the PowerShell script without opening a microphone. Actual acoustic wake
accuracy and device permissions need validation on the user's Windows PC.

APIs: [Microsoft SpeechRecognitionEngine](https://learn.microsoft.com/en-us/dotnet/api/system.speech.recognition.speechrecognitionengine.recognize?view=netframework-4.8),
[Qt property animations](https://doc.qt.io/qtforpython-6/PySide6/QtCore/QPropertyAnimation.html).
