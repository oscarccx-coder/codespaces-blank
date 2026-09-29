Apollo 7.5.12.7 — XTTS Runtime Compatibility + Installer Hardening

Install over Apollo 7.5.12.6 with Apollo completely closed.

IMPORTANT FIX
-------------
The XTTS failure:
  ImportError: cannot import name 'isin_mps_friendly'

is caused by the installed Transformers 5.x runtime being incompatible with the
current Coqui-TTS XTTS import path on this Apollo build.

Apollo now pins:
  coqui-tts==0.27.5
  transformers==4.57.6

RUNNING THE FIX
---------------
After copying the patch into Apollo, run:
  install_xtts_v2.bat

Or open Apollo -> Voice Imprint Lab -> Install / Repair XTTS Engine.

The installer checks Python, Coqui, Transformers and XTTS imports BEFORE the
large model download.

BASE INSTALLER FIX
------------------
install.bat no longer reports success after failed Python commands.
start_apollo_ui.bat also ignores stale PYTHONHOME/PYTHONPATH values and searches
for a healthy Python interpreter.

If Python itself fails to import encodings, run:
  repair_apollo_python.bat

SAFE VERSION FINALISER
----------------------
The safe cumulative update includes apply_update_7_5_12_7.bat.
It changes only config.json's version field and preserves the rest of the user's settings.
