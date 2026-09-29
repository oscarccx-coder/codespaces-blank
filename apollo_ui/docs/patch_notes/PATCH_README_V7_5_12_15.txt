Apollo 7.5.12.15 — Voice Center + Deep Freeze Optimization
25 September 2026

VOICE CENTER
- Combines the old Voice Studio / control-selection UI and Voice Imprint Lab in one Voice Center app.
- Adds tabs: Voice Control & Selection, Voice Imprint Lab, Performance.
- The old two app surfaces are hidden, but their underlying modules/tools stay loaded.

FREEZE FIX — PROCESS ISOLATION
- XTTS/PyTorch no longer need to load into Apollo's Qt GUI process.
- A persistent dedicated `xtts_worker.py` process owns the model and CUDA state.
- Worker runs below-normal Windows priority and limits CPU-side torch threads.
- The GUI sends small JSON requests and receives file/result metadata only.
- Worker is reused between replies so the model still stays warm for speed.
- `Unload XTTS / Free GPU Memory` stops the worker; the next speech request starts it again.

ADDITIONAL OPTIMIZATION
- Voice readiness/status no longer imports torch, torchcodec, TTS or faster-whisper just to display status.
- Speaker conditioning remains cached, now inside the isolated worker.
- XTTS token-aware chunking remains below the ~400-token hard limit and never uses spaCy sentence splitting.
- Normal Apollo speech still coalesces pending neural requests so a conversation cannot build a speech backlog.
- Active Voice Imprint state is cached by file timestamp rather than re-reading JSON every speech request.
- Windows installed-voice enumeration is moved off the main UI thread.
- Voice Imprint training timer no longer queries training status twice per tick.
- Stop Speech cancels playback and kills an in-progress XTTS worker generation if necessary.

RECOVERY
- In-process XTTS remains as an explicit legacy fallback only if `process_isolation` is manually disabled in Voice Imprint settings.
- Worker errors are written to `storage/logs/xtts_worker.log`.
