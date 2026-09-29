# Apollo Modules

Drop one folder per feature into this directory, then open Apollo's **Modules**
page and press **Reload Modules**.

Removing a module folder and reloading removes the feature. You can also disable
a module from the UI without deleting its files.

**Security:** modules are trusted Python code and run with the same Windows user
permissions as Apollo. Only install code you trust.

Start by copying `_template` and renaming the copied folder.


## Included in V6.4

### chat_memory_module
Persistent SQLite conversation memory. Apollo automatically searches it before
chat and saves completed exchanges after chat.

### neural_learning
A small trainable one-hidden-layer neural network. Teach it labelled examples
from Train / Learn, then train it. Apollo can use its strongest prediction as
extra context for Ollama.
