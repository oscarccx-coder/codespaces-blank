Apollo V6.6.23 — Accent Fix + Apps in Settings

PATCH FROM V6.6.22

Copy over:
- main.py
- modules/text_to_speech/manifest.json
- modules/text_to_speech/module.py
- modules/text_to_speech/tests.py
- modules/text_to_speech/README.md

Do NOT replace your storage folder.

After restart:
- Apps is removed from the left sidebar.
- Open Settings -> Apps for module mini-apps.
- Open Voice Studio and use Accent to choose an installed Windows voice culture.

Accent is real voice-culture selection, not a fake pitch effect.
Only accents provided by installed Windows voices can be selected.
