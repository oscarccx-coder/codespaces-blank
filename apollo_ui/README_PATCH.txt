Apollo V6.6.20 module-creation patch

Copy workers.py into your Apollo root, replacing the old workers.py.

Copy pending_modules/text_to_speech into your Apollo pending_modules folder.
Do NOT replace your storage folder.

Restart Apollo. Open Modules -> Pending / Generated and validate/review
Text to Speech. It remains pending until you explicitly approve it.

The workers.py patch also fixes future Coding Workspace module requests so
Apollo executes Module Factory instead of merely describing a JSON call.
