Apollo V6.6.24 — Settings Model Switcher

PATCH CONTENTS
--------------
main.py

INSTALL
-------
1. Close Apollo.
2. Back up your current main.py if you want an easy rollback.
3. Copy this patch's main.py over Apollo's existing root main.py.
4. Start Apollo.
5. Open Settings -> General.
6. Under AI Model / Ollama click "Refresh Installed Models".
7. Choose an installed Ollama model.
8. Click "Save & Switch Model".

Your config.json and storage folder are NOT included in this patch, so your
current settings, memory and learned knowledge are not overwritten.

BEHAVIOUR
---------
- Model selection is saved into config.json.
- New chats use the newly selected model.
- Apollo memory/modules remain the same.
- Module Repair follows the newly selected model too.
- The selector remains editable in case you need to enter a model manually while
  Ollama is offline.
