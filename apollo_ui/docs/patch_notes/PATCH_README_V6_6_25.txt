Apollo V6.6.25 — Workshop / Natural Voice / Voice Dataset / Self-Improvement Foundation

PATCH FILES
-----------
main.py
workers.py
requirements.txt
modules/file_builder/module.py
modules/file_builder/manifest.json
modules/text_to_speech/module.py
modules/text_to_speech/manifest.json
modules/text_to_speech/README.md

INSTALL
-------
1. Close Apollo.
2. Copy the patch files over the matching files in your Apollo root.
3. Re-run install.bat once. This adds numpy + sounddevice for microphone WAV capture.
4. Start Apollo.
5. Open Workshop -> Refresh Capabilities.
6. Open Voice Studio and choose Precise / Natural / Expressive. Leave "Save Dictate..." enabled if you want to collect future TinyVoice data.

DATA SAFETY
-----------
The patch ZIP contains NO config.json, storage folder, memories, local Pile cache or user voice data.
Your dictation samples stay local under storage/voice_dataset/.

SELF-IMPROVEMENT SAFETY
-----------------------
Self-improvement remains approval-gated. Apollo can inspect itself read-only, create workspace prototypes, or create pending modules. It cannot silently install its own pending module or overwrite core Apollo through file_builder.
