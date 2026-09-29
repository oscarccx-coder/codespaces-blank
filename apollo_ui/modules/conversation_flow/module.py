import json
import re
from pathlib import Path


STOP = {
    "the", "a", "an", "and", "or", "to", "of", "in", "on", "for", "with",
    "this", "that", "it", "is", "are", "be", "you", "your", "i", "me", "my",
    "we", "our", "can", "could", "would", "please", "just", "then", "from",
}


class Module:
    RETRY_PHRASES = {
        "try again", "retry", "again", "do it again", "have another go",
        "try that again", "redo it", "retry that", "go again",
    }

    FOLLOW_PREFIXES = (
        "also ", "and ", "but ", "now ", "then ", "what about ", "same ",
        "do that", "do it", "make it", "change it", "fix it", "this ", "that ",
        "try again", "retry", "again",
    )

    def __init__(self, context=None):
        context = context or {}
        self.base = Path(context.get("base_dir", ".")).resolve()

    def tools(self):
        return [
            {
                "name": "analyse_turn",
                "description": "Build a compact conversation-continuity packet from the current message and recent visible chat history.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "current_text": {"type": "string"},
                        "recent_messages": {"type": "array"},
                    },
                    "required": ["current_text"],
                },
            },
            {
                "name": "flow_status",
                "description": "Describe Conversation Flow rules and readiness.",
                "parameters": {"type": "object", "properties": {}},
            },
        ]

    @staticmethod
    def _clean(text, max_chars=1800):
        text = " ".join(str(text or "").split()).strip()
        return text[:max_chars]

    @staticmethod
    def _keywords(text, limit=12):
        words = re.findall(r"[a-zA-Z0-9_+#.-]+", str(text).lower())
        out = []
        seen = set()
        for word in words:
            if len(word) < 3 or word in STOP or word in seen:
                continue
            seen.add(word)
            out.append(word)
            if len(out) >= limit:
                break
        return out

    def _previous_turns(self, recent_messages, current_text):
        messages = recent_messages if isinstance(recent_messages, list) else []
        previous_user = ""
        previous_assistant = ""
        for message in reversed(messages):
            if not isinstance(message, dict):
                continue
            role = str(message.get("role", "")).lower()
            content = self._clean(message.get("content", ""))
            if not content:
                continue
            if role == "assistant" and not previous_assistant:
                previous_assistant = content
            if role == "user" and content != self._clean(current_text) and not previous_user:
                previous_user = content
            if previous_user and previous_assistant:
                break
        return previous_user, previous_assistant

    def run(self, action, arguments):
        x = arguments or {}
        if action == "flow_status":
            return {
                "ready": True,
                "mode": "deterministic-no-extra-llm",
                "recognises_retries": sorted(self.RETRY_PHRASES),
                "purpose": "Preserve conversational intent across short follow-ups without inventing actions.",
            }

        if action == "analyse_turn":
            current = self._clean(x.get("current_text", ""))
            lower = current.lower().strip(" .!?\t\r\n")
            previous_user, previous_assistant = self._previous_turns(
                x.get("recent_messages", []), current
            )
            retry = lower in self.RETRY_PHRASES or any(lower.startswith(p) for p in ("retry ", "try again "))
            short = len(current.split()) <= 7
            follow = retry or any(lower.startswith(prefix) for prefix in self.FOLLOW_PREFIXES)
            pronoun_follow = short and bool(re.search(r"\b(it|that|this|same|one|again)\b", lower))
            is_follow_up = bool(previous_user and (follow or pronoun_follow))

            keywords = self._keywords(current + " " + (previous_user if is_follow_up else ""))
            packet = {
                "is_follow_up": is_follow_up,
                "is_retry": bool(previous_user and retry),
                "current_text": current,
                "previous_user_request": previous_user if is_follow_up else "",
                "previous_assistant_result": previous_assistant[:900] if is_follow_up else "",
                "topic_keywords": keywords,
                "guidance": (
                    "Continue the previous user request rather than restarting or asking what they mean. "
                    "If the previous attempt failed, retry the real operation using its original intent and report the new real result."
                    if is_follow_up else
                    "Treat this as a new turn unless the ordinary conversation context clearly says otherwise."
                ),
            }
            return packet

        raise KeyError(action)

    def self_test(self):
        packet = self.run("analyse_turn", {
            "current_text": "try again",
            "recent_messages": [
                {"role": "user", "content": "make a module for yourself to help make our conversations more fluid"},
                {"role": "assistant", "content": "module creation failed"},
            ],
        })
        assert packet["is_retry"]
        assert "module" in packet["previous_user_request"].lower()
        return "Conversation Flow retry/follow-up continuity passed."

    def build_ui(self, parent=None, ui_context=None):
        from PySide6.QtWidgets import QWidget, QVBoxLayout, QLabel, QTextEdit
        page = QWidget(parent)
        layout = QVBoxLayout(page)
        title = QLabel("Conversation Flow")
        title.setStyleSheet("font-size:22px;font-weight:800;")
        layout.addWidget(title)
        note = QLabel(
            "Apollo uses this automatically on normal chat turns. It recognises short follow-ups such as 'try again', "
            "'do that', 'same but…', and preserves the previous visible request. It is deterministic and does not add another LLM call."
        )
        note.setWordWrap(True)
        layout.addWidget(note)
        output = QTextEdit()
        output.setReadOnly(True)
        output.setPlainText(json.dumps(self.run("flow_status", {}), indent=2))
        layout.addWidget(output, 1)
        return page
