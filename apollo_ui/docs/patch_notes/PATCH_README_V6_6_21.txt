Apollo V6.6.21 Voice I/O + Chat Fix patch

Copy main.py and workers.py into the Apollo root.
Copy modules/text_to_speech into Apollo/modules/text_to_speech (replace the older version).
Restart Apollo.

The module is included as installed because this patch is the user's explicit request to add TTS/STT chat functionality.
