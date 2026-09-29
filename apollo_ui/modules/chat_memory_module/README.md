# Chat Memory Module

Persistent SQLite-backed chat memory for Apollo.

Apollo V6.4 automatically:
- searches this module before each Ollama request
- injects relevant memories into the system context
- saves completed user/assistant exchanges after each reply

Runtime database:

`storage/chat_memory_module.db`
