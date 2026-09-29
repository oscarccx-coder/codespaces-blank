import json
import re
from collections import Counter

from tool_call_parser import extract_text_tool_calls, normalize_tool_call
from PySide6.QtCore import QObject, QRunnable, Signal, Slot


class ChatSignals(QObject):
    chunk = Signal(str)
    finished = Signal(str)
    failed = Signal(str)
    completed = Signal()
    tool_used = Signal(str, str)


class ChatTask(QRunnable):
    """
    Apollo's guarded Ollama tool controller.

    Key protections:
      - filters the tool catalog for coding requests
      - detects duplicate/repeating calls
      - batch file creation is treated as a terminal successful action
      - a passing pending module is treated as a terminal successful action
      - when tool work is complete, Apollo forces a final no-tools response
      - hitting the round budget produces a final summary instead of discarding
        all completed work with a hard error
    """

    MAX_TOOL_ROUNDS = 10
    MAX_TOOL_CALLS_PER_ROUND = 12
    MAX_TOTAL_TOOL_CALLS = 28
    MAX_IDENTICAL_CALLS = 1

    def __init__(self, client, messages, module_manager=None):
        super().__init__()
        self.client = client
        self.messages = list(messages)
        self.module_manager = module_manager
        self.signals = ChatSignals()
        self._cancelled = False
        self._call_counts = Counter()
        self._tool_history = []
        self._total_tool_calls = 0
        self.setAutoDelete(True)

    def cancel(self):
        self._cancelled = True

    def _normal_stream(self, messages):
        full = []
        for part in self.client.stream_chat(messages):
            if self._cancelled:
                break
            full.append(part)
            self.signals.chunk.emit(part)
        return "".join(full)

    def _allowed_tool_names(self, tools):
        names = set()
        for tool in tools or []:
            fn = tool.get("function", {}) or {}
            name = str(fn.get("name", "")).strip()
            if name:
                names.add(name)
        return names

    def _normalize_tool_call(self, obj, allowed_names):
        return normalize_tool_call(obj, allowed_names)

    def _extract_text_tool_calls(self, content, allowed_names):
        return extract_text_tool_calls(content, allowed_names)

    def _native_tool_calls(self, assistant_message, allowed_names):
        calls = []
        for raw in (assistant_message.get("tool_calls") or []):
            fn = raw.get("function", {}) or {}
            call = self._normalize_tool_call(
                {
                    "name": fn.get("name", ""),
                    "arguments": fn.get("arguments", {}),
                },
                allowed_names,
            )
            if call:
                calls.append(call)
        return calls

    def _request_text(self):
        pieces = []
        for message in self.messages:
            if str(message.get("role", "")).lower() == "user":
                pieces.append(str(message.get("content", "")))
        return "\n".join(pieces)

    @staticmethod
    def _is_apollo_module_request(text):
        lower = str(text or "").lower()

        request_match = re.search(
            r"(?is)\bREQUEST\s*:\s*(.+)$",
            str(text or ""),
        )
        if request_match:
            lower = request_match.group(1).lower()

        module_words = (
            "apollo module",
            "apollo modual",
            "new module",
            "new modual",
            "training module",
            "training modual",
            "plugin for apollo",
            "module for apollo",
            "modual for apollo",
            "add a module",
            "add a modual",
            "module for yourself",
            "modual for yourself",
            "add to pending",
            "pending module",
            "pending modual",
            "plugin",
        )

        return any(word in lower for word in module_words)

    def _last_user_text(self):
        for message in reversed(self.messages):
            if str(
                message.get(
                    "role",
                    "",
                )
            ).lower() == "user":
                return str(
                    message.get(
                        "content",
                        "",
                    )
                ).strip()

        return ""

    @staticmethod
    def _pile_query_from_text(text):
        """
        Remove the explicit Pile command words while preserving the actual topic.

        Examples:
          learn from The Pile advanced ai coding -> advanced ai coding
          search The Pile for transformer saturation -> transformer saturation
        """
        value = " ".join(
            str(text or "").split()
        ).strip()

        for wrapper in [
            r"(?i)^\s*(?:says?\s+this|sent\s+this|request|coding\s+workspace\s+request)\s*[:,-]?\s*",
        ]:
            value = re.sub(wrapper, "", value, count=1).strip()

        patterns = [
            (
                r"(?i)^\s*(?:please\s+)?"
                r"(?:learn|study|research|remember|absorb)\s+"
                r"(?:about\s+)?(?:from\s+)?(?:the\s+)?pile"
                r"(?:\s+online)?"
                r"(?:\s+(?:about|on|for))?"
                r"\s*[:,-]?\s*"
            ),
            (
                r"(?i)^\s*(?:please\s+)?"
                r"(?:search|query|access|use|look\s+in|look\s+through)\s+"
                r"(?:the\s+)?pile"
                r"(?:\s+online)?"
                r"(?:\s+(?:about|on|for))?"
                r"\s*[:,-]?\s*"
            ),
        ]

        query = value

        for pattern in patterns:
            new_value = re.sub(
                pattern,
                "",
                query,
                count=1,
            ).strip()

            if new_value != query:
                query = new_value
                break

        query = re.sub(
            r"(?i)^\s*(?:about|on|for)\s+",
            "",
            query,
            count=1,
        ).strip(" :,-")

        return query

    def _explicit_pile_directive(self):
        text = self._last_user_text()
        lower = text.lower()

        if not re.search(
            r"\b(?:the\s+)?pile\b",
            lower,
        ):
            return None

        learn_words = (
            "learn",
            "study",
            "remember",
            "absorb",
            "gain knowledge",
            "research",
        )

        search_words = (
            "search",
            "query",
            "access",
            "look",
            "find",
            "use",
        )

        mode = None

        if any(
            word in lower
            for word in learn_words
        ):
            mode = "learn"

        elif any(
            word in lower
            for word in search_words
        ):
            mode = "search"

        if mode is None:
            return None

        query = self._pile_query_from_text(
            text
        )

        if not query:
            return {
                "mode": mode,
                "query": "",
                "original": text,
            }

        return {
            "mode": mode,
            "query": query,
            "original": text,
        }

    def _record_direct_tool(
        self,
        name,
        result=None,
        error=None,
    ):
        if error is None:
            payload = {
                "ok": True,
                "tool": name,
                "result": result,
            }
        else:
            payload = {
                "ok": False,
                "tool": name,
                "error": str(error),
            }

        tool_content = json.dumps(
            payload,
            ensure_ascii=False,
            default=str,
        )

        self._tool_history.append(
            payload
        )
        self.signals.tool_used.emit(
            name,
            tool_content,
        )

    @staticmethod
    def _pile_source_response(
        directive,
        result,
    ):
        query = directive["query"]
        mode = directive["mode"]

        if mode == "learn":
            chunks = int(
                result.get(
                    "chunks_added",
                    0,
                )
                or 0
            )

            passages = result.get(
                "learned_passages",
                [],
            )

            if chunks <= 0:
                errors = result.get(
                    "errors",
                    [],
                )

                if result.get("dependency_missing"):
                    return (
                        "The remote Pile service was unavailable and Apollo tried to "
                        "fall back to a local Pile cache, but the required dependency "
                        f"`{result.get('dependency_missing')}` is not installed.\n\n"
                        f"{result.get('action_required', 'Run install.bat and retry.')}"
                    )

                message = (
                    "I accessed The Pile for "
                    f"'{query}', but I did not find any passages that passed "
                    "the relevance checks, so I did not add anything to my "
                    "knowledge base."
                )

                if errors:
                    message += (
                        "\n\nProvider errors:\n"
                        + "\n".join(
                            "- "
                            + str(
                                item.get(
                                    "error",
                                    item,
                                )
                            )
                            for item in errors[:4]
                        )
                    )

                if result.get(
                    "partial"
                ):
                    message += (
                        "\n\nThe remote Hugging Face index reported `partial=true`, "
                        "so this was not an exhaustive search of every row in the "
                        "full Pile."
                    )

                return message

            lines = [
                (
                    f"I accessed The Pile and learned source-backed material "
                    f"for **{query}**."
                ),
                "",
                (
                    f"Stored **{chunks}** curated knowledge chunk(s) from "
                    f"**{result.get('documents_found', 0)}** relevant document(s)."
                ),
                (
                    f"Access method: **{result.get('access_method', 'unknown')}**."
                ),
            ]

            if result.get("auto_cache_downloaded"):
                cache_info = result.get("cache_download", {}) or {}
                cache = cache_info.get("cache", {}) or {}
                lines.append(
                    (
                        "The Hugging Face search service failed, so Apollo dynamically "
                        "discovered the current Parquet cache URL and created/resumed "
                        "the Lite local Pile cache "
                        f"({cache.get('shards_cached', 1)} shard, "
                        f"{cache.get('megabytes_on_disk', 'unknown')} MB on disk)."
                    )
                )

            rejected = int(
                result.get(
                    "rejected_as_irrelevant",
                    0,
                )
                or 0
            )

            if rejected:
                lines.append(
                    f"Rejected **{rejected}** unrelated or low-quality hit(s) instead of learning them."
                )

                reasons = result.get(
                    "rejection_reasons",
                    {},
                )

                if reasons:
                    readable = ", ".join(
                        (
                            f"{reason.replace('_', ' ')}: {count}"
                        )
                        for reason, count
                        in sorted(
                            reasons.items(),
                            key=lambda item: item[1],
                            reverse=True,
                        )[:5]
                    )
                    lines.append(
                        f"Main rejection reasons: {readable}."
                    )

            replaced = int(
                result.get(
                    "replaced_previous_chunks",
                    0,
                )
                or 0
            )

            if replaced:
                lines.append(
                    (
                        f"Replaced **{replaced}** older compiled chunk(s) "
                        "for this same topic."
                    )
                )

            if passages:
                lines.extend([
                    "",
                    "What was actually learned from the high-signal technical sections:",
                ])

                for item in passages[:5]:
                    excerpt = " ".join(
                        str(
                            item.get(
                                "text",
                                "",
                            )
                        ).split()
                    )

                    if len(excerpt) > 420:
                        excerpt = (
                            excerpt[:417]
                            + "..."
                        )

                    signals = item.get(
                        "quality_signals",
                        [],
                    )

                    signal_text = (
                        " • "
                        + ", ".join(
                            str(signal)
                            for signal
                            in signals[:6]
                        )
                        if signals
                        else ""
                    )

                    lines.append(
                        (
                            f"- **{item.get('subset', 'The Pile')}** "
                            f"(row {item.get('row_idx')})"
                            f"{signal_text}: {excerpt}"
                        )
                    )

            lines.extend([
                "",
                (
                    "This material is now in `storage/databases/compiled_knowledge.db` "
                    "and normal Chat can retrieve it later."
                ),
            ])

            if result.get(
                "partial"
            ):
                lines.append(
                    (
                        "Hugging Face reported a **partial** search index for this "
                        "very large dataset, so I am not claiming this searched "
                        "every row of the complete Pile."
                    )
                )

            return "\n".join(lines)

        results = result.get(
            "results",
            [],
        )

        if not results:
            return (
                f"I accessed The Pile for '{query}', but no passages passed "
                "the relevance checks. I am not substituting generic model "
                "knowledge for missing Pile results."
            )

        lines = [
            f"The Pile search for **{query}** returned these relevant passages:",
            "",
        ]

        for item in results[:6]:
            excerpt = " ".join(
                str(
                    item.get(
                        "text",
                        "",
                    )
                ).split()
            )

            if len(excerpt) > 500:
                excerpt = (
                    excerpt[:497]
                    + "..."
                )

            lines.append(
                (
                    f"- **{item.get('pile_set_name', 'The Pile')}** "
                    f"(row {item.get('row_idx')}, relevance "
                    f"{item.get('relevance')}): {excerpt}"
                )
            )

        if result.get(
            "partial"
        ):
            lines.extend([
                "",
                (
                    "The remote dataset index reports `partial=true`, so these "
                    "results do not represent an exhaustive search of every row "
                    "in the complete corpus."
                ),
            ])

        return "\n".join(lines)

    def _run_explicit_pile(self):
        directive = (
            self._explicit_pile_directive()
        )

        if directive is None:
            return None

        query = directive.get(
            "query",
            "",
        ).strip()

        if not query:
            content = (
                "I can access The Pile, but I need a topic to search or learn. "
                "For example: `learn from The Pile advanced AI coding`."
            )

            self.signals.chunk.emit(
                content
            )
            return content

        if not self.module_manager:
            content = (
                "The Pile Knowledge module is not available, so I did not "
                "pretend to learn anything."
            )
            self.signals.chunk.emit(
                content
            )
            return content

        tool_name = (
            "pile_knowledge__learn_from_pile"
            if directive["mode"] == "learn"
            else "pile_knowledge__search_pile"
        )

        try:
            result = (
                self.module_manager.execute_tool(
                    tool_name,
                    {
                        "query": query,
                        "limit": 6,
                        "auto_cache": (
                            directive["mode"] == "learn"
                        ),
                    },
                )
            )

            self._record_direct_tool(
                tool_name,
                result=result,
            )

            content = (
                self._pile_source_response(
                    directive,
                    result
                    if isinstance(
                        result,
                        dict,
                    )
                    else {},
                )
            )

        except Exception as exc:
            error_text = (
                f"{type(exc).__name__}: {exc}"
            )

            self._record_direct_tool(
                tool_name,
                error=error_text,
            )

            content = (
                "I tried to access The Pile directly, but the Pile tool failed:\n\n"
                f"`{error_text}`\n\n"
                "I did **not** replace the failed source lookup with generic model "
                "knowledge, and I did not store anything from this failed request."
            )

        self.signals.chunk.emit(
            content
        )
        return content

    def _explicit_to_do_directive(self):
        text = self._last_user_text()
        lower = text.lower()

        if not re.search(
            r"\bto[\s-]?do\s+list\b",
            lower,
        ):
            return None

        if re.search(
            r"\bachieve\b.*\bto[\s-]?do\s+list\b",
            lower,
        ):
            return {
                "mode": "achieve",
                "text": text,
            }

        patterns = [
            (
                "add",
                r"(?is)^\s*add\s+(.+?)\s+to\s+(?:my\s+|the\s+)?to[\s-]?do\s+list\s*$",
            ),
            (
                "remove",
                r"(?is)^\s*(?:remove|delete)\s+(.+?)\s+from\s+(?:my\s+|the\s+)?to[\s-]?do\s+list\s*$",
            ),
            (
                "complete",
                r"(?is)^\s*(?:tick\s+off|complete)\s+(.+?)(?:\s+(?:on|from)\s+(?:my\s+|the\s+)?to[\s-]?do\s+list)?\s*$",
            ),
        ]

        for mode, pattern in patterns:
            match = re.match(
                pattern,
                text,
            )
            if match:
                return {
                    "mode": mode,
                    "item": (
                        match.group(1)
                        .strip()
                    ),
                    "text": text,
                }

        if re.search(
            r"(?i)^\s*(?:show|list|display|what(?:'s| is)\s+on)\b.*\bto[\s-]?do\s+list\b",
            text,
        ):
            return {
                "mode": "list",
                "text": text,
            }

        return None

    def _run_simple_to_do(self):
        directive = (
            self._explicit_to_do_directive()
        )

        if (
            directive is None
            or directive.get("mode")
            == "achieve"
        ):
            return None

        if not self.module_manager:
            return None

        mode = directive["mode"]

        tool_map = {
            "add": "todo_list__add_to_do_item",
            "remove": "todo_list__remove_to_do_item",
            "complete": "todo_list__complete_to_do_item",
            "list": "todo_list__list_to_do_items",
        }

        tool_name = tool_map[mode]

        if mode == "add":
            arguments = {
                "title": directive["item"]
            }
        elif mode in {
            "remove",
            "complete",
        }:
            arguments = {
                "item": directive["item"]
            }
        else:
            arguments = {
                "include_completed": True,
                "limit": 50,
            }

        try:
            result = (
                self.module_manager
                .execute_tool(
                    tool_name,
                    arguments,
                )
            )

            self._record_direct_tool(
                tool_name,
                result=result,
            )

            if mode == "add":
                item = result.get(
                    "item",
                    {},
                )
                content = (
                    "Added to the To-Do List: "
                    f"**{item.get('title', directive['item'])}**."
                )

            elif mode == "remove":
                item = result.get(
                    "item",
                    {},
                )
                content = (
                    "Removed from the To-Do List: "
                    f"**{item.get('title', directive['item'])}**."
                )

            elif mode == "complete":
                item = result.get(
                    "item",
                    {},
                )
                content = (
                    "Completed and ticked off: "
                    f"**{item.get('title', directive['item'])}**."
                )

            else:
                items = (
                    result
                    if isinstance(
                        result,
                        list,
                    )
                    else []
                )

                if not items:
                    content = (
                        "The To-Do List is empty."
                    )
                else:
                    lines = [
                        "Current To-Do List:",
                        "",
                    ]

                    for item in items:
                        marker_text = (
                            "✓"
                            if item.get(
                                "status"
                            )
                            == "completed"
                            else "○"
                        )

                        lines.append(
                            (
                                f"- {marker_text} "
                                f"{item.get('id')}. "
                                f"{item.get('title')}"
                            )
                        )

                    content = "\n".join(
                        lines
                    )

        except Exception as exc:
            error_text = (
                f"{type(exc).__name__}: "
                f"{exc}"
            )

            self._record_direct_tool(
                tool_name,
                error=error_text,
            )

            content = (
                "The To-Do List command failed:\n\n"
                f"`{error_text}`"
            )

        self.signals.chunk.emit(
            content
        )
        return content

    def _prepare_to_do_achievement(self):
        directive = (
            self._explicit_to_do_directive()
        )

        if (
            directive is None
            or directive.get("mode")
            != "achieve"
            or not self.module_manager
        ):
            return None

        tool_name = (
            "todo_list__achieve_to_do_list"
        )

        try:
            result = (
                self.module_manager
                .execute_tool(
                    tool_name,
                    {
                        "limit": 10,
                    },
                )
            )

            self._record_direct_tool(
                tool_name,
                result=result,
            )

            items = (
                result.get(
                    "items",
                    [],
                )
                if isinstance(
                    result,
                    dict,
                )
                else []
            )

            if not items:
                return {
                    "empty": True,
                    "system": (
                        "The To-Do List has no open items."
                    ),
                }

            plan = "\n".join(
                (
                    f"- ID {item.get('id')}: "
                    f"{item.get('title')}"
                    + (
                        f" — {item.get('details')}"
                        if item.get(
                            "details"
                        )
                        else ""
                    )
                )
                for item in items
            )

            return {
                "empty": False,
                "items": items,
                "system": (
                    "TO-DO ACHIEVEMENT MODE IS ACTIVE.\n"
                    "Apollo already called todo_list__achieve_to_do_list and received "
                    "these open items:\n"
                    + plan
                    + "\n\nWork through actionable items one at a time using real "
                    "installed Apollo tools. After an item's real action succeeds, "
                    "call todo_list__complete_to_do_item with that item's ID. "
                    "Do not tick off an item merely because you described how to do it. "
                    "If an item requires physical/manual work or no suitable tool exists, "
                    "leave it open and report that limitation."
                ),
            }

        except Exception as exc:
            return {
                "empty": True,
                "system": (
                    "Apollo could not read the To-Do List achievement plan: "
                    f"{type(exc).__name__}: {exc}"
                ),
            }


    def _coding_workspace_request_body(self):
        """
        Return only the REQUEST body from the Coding Workspace wrapper.

        This avoids treating the routing instructions themselves as the user's
        project/module request.
        """
        text = self._last_user_text()

        if "CODING WORKSPACE REQUEST:" not in text.upper():
            return ""

        match = re.search(
            r"(?is)\bREQUEST\s*:\s*(.+)$",
            text,
        )

        if not match:
            return ""

        return match.group(1).strip()

    @staticmethod
    def _project_name_from_message(text):
        """Extract a previously-established Workspace project name from visible chat."""
        value = str(text or "")

        match = re.search(
            r"(?i)workspace[\\/]+([A-Za-z0-9_.-]{1,80})",
            value,
        )
        if match:
            return match.group(1)

        match = re.search(
            r"(?i)\bproject\s+(?:called|named)\s+[`'\"]?([A-Za-z0-9_.-]{1,80})",
            value,
        )
        if match:
            return match.group(1)

        return ""

    def _workspace_projects(self):
        """Return real Workspace project names without asking the model."""
        if not self.module_manager:
            return []

        try:
            result = self.module_manager.execute(
                "file_builder",
                "list_projects",
                {},
            )
        except Exception:
            return []

        projects = []
        for row in result.get("projects", []) or []:
            if isinstance(row, dict):
                name = str(row.get("project", "")).strip()
            else:
                name = str(row).strip()
            if name:
                projects.append(name)
        return projects

    def _persistent_active_project(self):
        """Read File Builder's restart-safe active-project pointer."""
        if not self.module_manager:
            return ""

        try:
            result = self.module_manager.execute(
                "file_builder",
                "active_project",
                {},
            )
            return str(result.get("project", "")).strip()
        except Exception:
            return ""

    @staticmethod
    def _project_name_mentioned(text, projects):
        """Match a real Workspace project named naturally in the request."""
        lower = str(text or "").lower()
        matches = []

        for project in projects or []:
            project = str(project).strip()
            if not project:
                continue
            pattern = (
                r"(?<![A-Za-z0-9_])"
                + re.escape(project.lower())
                + r"(?![A-Za-z0-9_])"
            )
            if re.search(pattern, lower):
                matches.append(project)

        if not matches:
            return ""

        return sorted(
            matches,
            key=len,
            reverse=True,
        )[0]

    def _recent_project_name(self):
        """Return the best current real project across chat history and restarts."""
        current_text = self._last_user_text()
        projects = self._workspace_projects()

        # A real project named in this exact request wins.
        mentioned = self._project_name_mentioned(
            current_text,
            projects,
        )
        if mentioned:
            return mentioned

        # Current running-chat context.
        for message in reversed(self.messages[-14:]):
            if str(message.get("role", "")).lower() != "assistant":
                continue
            name = self._project_name_from_message(
                message.get("content", "")
            )
            if name:
                return name

        for message in reversed(self.messages[-14:]):
            if str(message.get("role", "")).lower() != "user":
                continue
            name = self._project_name_from_message(
                message.get("content", "")
            )
            if name:
                return name

        # Survives restart/patch installation.
        active = self._persistent_active_project()
        if active:
            return active

        # Safe last resort when only one project actually exists.
        if len(projects) == 1:
            return projects[0]

        return ""

    @staticmethod
    def _looks_like_project_edit_followup(text):
        """Recognise a coding edit request that relies on the active project context."""
        lower = " ".join(str(text or "").lower().split())
        if not lower:
            return False

        if "new project" in lower or re.search(r"\bproject\s+(?:called|named)\s+", lower):
            return False

        excluded = (
            "to-do", "todo", "remind", "memory bank", "remember that",
            "learn from pile", "the pile", "apollo module", "apollo modual",
            "pending module", "voice imprint", "voice studio", "settings tab",
        )
        if any(term in lower for term in excluded):
            return False

        edit_action = bool(re.search(
            r"\b(add|change|update|modify|fix|remove|delete|rename|refactor|improve|extend|replace|support|make|also|include|implement|correct|adjust)\b",
            lower,
        ))
        if not edit_action:
            return False

        coding_signal = any(term in lower for term in (
            "calculator", "calculate", "function", "class", "method", "python",
            "code", "file", "script", "input", "output", "validation", "test",
            "error", "exception", "ui", "button", "menu", "api", "database",
            "velocity", "mass", "radius", "force", "gravity", "formula",
            "readme", "config", "module import", "entrypoint",
        ))
        continuation_signal = lower.startswith((
            "add ", "also ", "and ", "change ", "update ", "make it ",
            "fix ", "now ", "then ", "what about ", "same ",
        ))
        return bool(coding_signal or continuation_signal)

    @staticmethod
    def _is_retry_phrase(text):
        cleaned = " ".join(str(text or "").lower().split()).strip(" .!?\t\r\n")
        return cleaned in {
            "try again", "retry", "again", "do it again", "have another go",
            "try that again", "redo it", "retry that", "go again",
            "do it", "do that", "go ahead", "yes do it", "go for it",
            "make it", "build it", "create it",
        }

    @staticmethod
    def _is_meaningful_prior_request(text):
        cleaned = " ".join(str(text or "").lower().split()).strip(" .!?\t\r\n")
        if not cleaned:
            return False
        if ChatTask._is_retry_phrase(cleaned):
            return False
        if cleaned in {"hi", "hello", "hey", "thanks", "thank you", "ok", "okay", "cool", "nice"}:
            return False
        return len(cleaned) >= 3

    def _previous_meaningful_user_request(self):
        """Recover the previous real user intent across visible history or a restart."""
        current = self._last_user_text().strip()
        skipped_current = False
        for message in reversed(self.messages):
            if str(message.get("role", "")).lower() != "user":
                continue
            candidate = str(message.get("content", "")).strip()
            if not skipped_current and candidate == current:
                skipped_current = True
                continue
            if self._is_meaningful_prior_request(candidate):
                return candidate

        if self.module_manager:
            try:
                record = self.module_manager.get_module("chat_memory_module")
                if (
                    record
                    and record.get("enabled")
                    and record.get("instance") is not None
                ):
                    result = self.module_manager.execute(
                        "chat_memory_module",
                        "previous_user_request",
                        {"limit": 80, "skip_text": current},
                    )
                    candidate = str(result.get("user_text", "")).strip()
                    if result.get("found") and self._is_meaningful_prior_request(candidate):
                        return candidate
            except Exception:
                pass
        return ""

    def _resolved_user_request(self):
        current = self._last_user_text().strip()
        if self._is_retry_phrase(current):
            previous = self._previous_meaningful_user_request()
            if previous:
                return previous
        return current

    def _explicit_project_update(self):
        """Return project/request when this turn edits the recent real Workspace project."""
        text = self._resolved_user_request().strip()
        if not text or self._looks_like_module_build_request(text):
            return None

        if self._looks_like_real_file_build_request(text):
            if re.search(r"(?i)\b(?:new project|project\s+(?:called|named))\b", text):
                return None

        project = self._recent_project_name()
        if not project:
            return None

        projects = self._workspace_projects()
        explicitly_named = bool(
            self._project_name_mentioned(
                text,
                projects,
            )
        )
        edit_verb = bool(re.search(
            r"\b(add|change|update|modify|fix|remove|delete|rename|refactor|improve|extend|replace|support|make|include|implement|correct|adjust)\b",
            text.lower(),
        ))

        if not self._looks_like_project_edit_followup(text):
            if not (explicitly_named and edit_verb):
                return None

        return {"project": project, "request": text}

    def _project_source_snapshot(self, project, max_files=24, max_chars=90000):
        """Read a bounded snapshot of the real project before generating an edit."""
        if not self.module_manager:
            raise RuntimeError("Module manager unavailable")

        inspection = self.module_manager.execute(
            "file_builder",
            "inspect_project",
            {"project": project},
        )
        files = list(inspection.get("files") or [])
        readable_suffixes = {
            ".py", ".pyw", ".md", ".txt", ".json", ".jsonl", ".toml",
            ".yaml", ".yml", ".ini", ".cfg", ".html", ".css", ".js",
            ".ts", ".sql", ".csv",
        }
        snapshot = []
        used = 0

        for relative in files:
            if relative == ".apollo_project.json":
                continue
            suffix = ""
            filename = relative.rsplit("/", 1)[-1]
            if "." in filename:
                suffix = "." + filename.rsplit(".", 1)[-1].lower()
            if suffix not in readable_suffixes:
                continue
            if len(snapshot) >= max_files or used >= max_chars:
                break
            try:
                result = self.module_manager.execute(
                    "file_builder",
                    "read_file",
                    {"path": f"{project}/{relative}"},
                )
                content = str(result.get("content", ""))
            except Exception:
                continue
            remaining = max_chars - used
            content = content[:remaining]
            used += len(content)
            snapshot.append({"path": relative, "content": content})

        return {
            "project": project,
            "tree": files,
            "files": snapshot,
            "manifest": inspection.get("manifest"),
        }

    @staticmethod
    def _looks_like_unexecuted_tool_json(content):
        """Detect internal tool-protocol JSON so it never leaks raw into Chat."""
        text = str(content or "").strip()
        if not text.startswith("{") or "arguments" not in text:
            return False
        return bool(re.search(
            r'"(?:name|tool|tool_name)"\s*:\s*"[A-Za-z0-9_-]+(?:__(?:[A-Za-z0-9_.-]+)|\.[A-Za-z0-9_.-]+)?"',
            text,
        ))

    def _explicit_file_request_body(self):
        """Return a concrete real-file/project request from Chat or Workshop."""
        text = self._resolved_user_request().strip()
        if not text:
            return ""

        upper = text.upper()
        wrappers = (
            "CODING WORKSPACE REQUEST:",
            "APOLLO WORKSHOP REQUEST:",
            "SELF IMPROVEMENT WORKSHOP REQUEST:",
            "SELF-IMPROVEMENT WORKSHOP REQUEST:",
        )
        if any(marker in upper for marker in wrappers):
            match = re.search(r"(?is)\bREQUEST\s*:\s*(.+)$", text)
            body = match.group(1).strip() if match else ""
            if body and not self._looks_like_module_build_request(body):
                return body if self._looks_like_real_file_build_request(body) else ""
            return ""

        if self._looks_like_module_build_request(text):
            return ""
        return text if self._looks_like_real_file_build_request(text) else ""

    @staticmethod
    def _looks_like_real_file_build_request(text):
        lower = " ".join(str(text or "").lower().split())
        if not lower:
            return False

        if lower.startswith((
            "what is ", "what are ", "why ", "how does ", "how do i ",
            "can you explain", "tell me about", "show me how ",
        )):
            return False

        has_action = any(re.search(pattern, lower) for pattern in (
            r"\b(?:build|create|make|write|generate|develop|start|set up)\b",
            r"\bi want to (?:build|create|make|write|start)\b",
            r"\badd (?:a |an |the )?(?:file|script|project|program|app|website)\b",
        ))
        has_target = any(term in lower for term in (
            "python project", "project called", "project named", "coding project",
            "program", "script", "website", "web app", "desktop app", "application",
            "main.py", ".py", "create file", "make a file", "write a file",
            "real file", "real files", "workspace",
        ))
        named_project = bool(re.search(r"\bproject\s+(?:called|named)\s+[a-z0-9_-]+", lower))
        return bool(has_action and (has_target or named_project))

    @staticmethod
    def _module_ui_requested(text):
        lower = " ".join(str(text or "").lower().split())
        return any(term in lower for term in (
            "with ui", "with a ui", "user interface", "graphical interface",
            "gui", "ui page", "inside apollo", "within this program",
            "within apollo", "use it in apollo", "use it within apollo",
            "app page", "apps page",
        ))

    @staticmethod
    def _looks_like_project_to_module_request(text):
        lower = " ".join(str(text or "").lower().split())
        if not lower:
            return False
        has_module = any(term in lower for term in (
            "module", "modual", "plugin", "plug-in",
        ))
        if not has_module:
            return False
        conversion = bool(re.search(
            r"\b(turn|convert|wrap|package|transform|change)\b.*\b(?:into|to|as)\b.*\b(module|modual|plugin|plug-in)\b",
            lower,
        ))
        current_object = any(term in lower for term in (
            "turn it", "convert it", "wrap it", "package it", "this project",
            "current project", "existing project", "the project", "gravitylab",
        ))
        return bool(conversion or current_object)

    def _project_module_authoring_context(self, request):
        """Attach the real active Workspace project source to a conversion request."""
        if not self._looks_like_project_to_module_request(request):
            return {
                "is_conversion": False,
                "request": request,
                "project": "",
                "preferred_module_id": "",
                "preferred_name": "",
                "ui_required": self._module_ui_requested(request),
            }

        project = self._recent_project_name()
        if not project:
            return {
                "is_conversion": True,
                "request": request,
                "project": "",
                "preferred_module_id": "",
                "preferred_name": "",
                "ui_required": True,
                "error": "No active Workspace project could be resolved.",
            }

        try:
            snapshot = self._project_source_snapshot(
                project,
                max_files=30,
                max_chars=70000,
            )
        except Exception as exc:
            return {
                "is_conversion": True,
                "request": request,
                "project": project,
                "preferred_module_id": "",
                "preferred_name": "",
                "ui_required": True,
                "error": f"Could not read project source: {type(exc).__name__}: {exc}",
            }

        safe_id = re.sub(r"[^a-z0-9_-]+", "_", project.lower()).strip("_")
        preferred_module_id = ((safe_id or "project") + "_app")[:64]
        preferred_name = f"{project} App"
        authoring_request = (
            "PROJECT-TO-APOLLO-MODULE CONVERSION.\n"
            f"ORIGINAL USER REQUEST: {request}\n"
            f"ACTIVE REAL WORKSPACE PROJECT: {project}\n"
            f"PREFERRED MODULE ID: {preferred_module_id}\n"
            f"PREFERRED MODULE NAME: {preferred_name}\n\n"
            "CONVERSION REQUIREMENTS:\n"
            "- Convert the functionality that actually exists in the supplied project source.\n"
            "- Do NOT invent unrelated TensorFlow, NumPy, training, database, or demo functionality.\n"
            "- Preserve the project's calculation/business logic and useful validation.\n"
            "- Expose useful Apollo tools for the project's real functions.\n"
            "- Implement build_ui(parent=None, ui_context=None) as an Apollo PySide6 app page.\n"
            "- Import PySide6 only inside build_ui so headless module validation can import module.py.\n"
            "- The UI must let the user enter the real project inputs, run its calculations/actions, "
            "and display results/errors without needing a terminal.\n"
            "- Do not modify the original Workspace project. Create a pending Apollo module instead.\n\n"
            "CURRENT REAL PROJECT SNAPSHOT:\n"
            + json.dumps(snapshot, ensure_ascii=False, default=str)
        )
        return {
            "is_conversion": True,
            "request": authoring_request,
            "project": project,
            "preferred_module_id": preferred_module_id,
            "preferred_name": preferred_name,
            "ui_required": True,
            "snapshot": snapshot,
        }

    def _explicit_module_request_body(self):
        """Return a real module-build request from any Apollo authoring surface.

        V7 originally forced Module Factory only when the request came through the
        old Coding Workspace wrapper. Workshop, Self-Improvement Workshop and plain
        Chat could therefore fall back to narration such as ``Step 1: call
        module_factory__get_contract(...)`` without creating anything.

        This method deliberately recognises *action requests*, not informational
        questions about modules. Once recognised, _run_explicit_module_build gives
        the model only the real Module Factory creation tool.
        """
        text = self._resolved_user_request().strip()
        if not text:
            return ""

        upper = text.upper()
        wrapper_markers = (
            "CODING WORKSPACE REQUEST:",
            "APOLLO WORKSHOP REQUEST:",
            "SELF IMPROVEMENT WORKSHOP REQUEST:",
            "SELF-IMPROVEMENT WORKSHOP REQUEST:",
        )

        if any(marker in upper for marker in wrapper_markers):
            match = re.search(
                r"(?is)\bREQUEST\s*:\s*(.+)$",
                text,
            )
            if match:
                body = match.group(1).strip()
                if self._looks_like_module_build_request(body):
                    return body
            return ""

        lower = text.lower()

        # Plain Chat may also author modules, but only for an explicit build/create
        # intent. This avoids hijacking questions such as "what is an Apollo module?".
        action_terms = (
            "make ",
            "create ",
            "build ",
            "add ",
            "write ",
            "generate ",
            "develop ",
        )
        question_starts = (
            "what ",
            "why ",
            "how does ",
            "how do ",
            "can you explain",
            "tell me about",
        )

        if lower.startswith(question_starts):
            return ""

        has_action = any(term in lower for term in action_terms)
        conversion_request = self._looks_like_project_to_module_request(text)
        explicit_pending = any(
            phrase in lower
            for phrase in (
                "add to pending",
                "put in pending",
                "pending module",
                "pending modual",
            )
        )

        if (
            (has_action or explicit_pending or conversion_request)
            and self._looks_like_module_build_request(text)
        ):
            return text

        return ""

    @staticmethod
    def _looks_like_module_build_request(text):
        lower = str(text or "").lower()

        module_terms = (
            "module",
            "modual",
            "plugin",
            "plug-in",
            "pending module",
            "add to pending",
            "pending_modules",
            "feature for yourself",
            "feature for apollo",
        )

        return any(
            term in lower
            for term in module_terms
        )

    @staticmethod
    def _tts_authoring_hint(text):
        lower = str(text or "").lower()

        if not (
            "text to speech" in lower
            or "text-to-speech" in lower
            or "text to speach" in lower
            or re.search(r"\btts\b", lower)
        ):
            return ""

        return (
            "\nThis request is for TEXT TO SPEECH on Apollo's Windows PC. "
            "Apollo is offline-first. Prefer the built-in Windows System.Speech "
            "engine via PowerShell/subprocess so there is no network dependency. "
            "Do NOT use gTTS, Google services, macOS afplay, or import heavyweight "
            "optional TTS packages at module import time. Expose useful tools such "
            "as speak_text, save_wav and list_voices. Validation must be safe and "
            "must not actually speak audio."
        )

    def _module_factory_tools(self):
        all_tools = (
            self.module_manager.ollama_tools()
            if self.module_manager
            else []
        )

        return [
            tool
            for tool in all_tools
            if str(
                (tool.get("function", {}) or {}).get(
                    "name",
                    "",
                )
            ).startswith(
                "module_factory__"
            )
        ]

    @staticmethod
    def _first_json_object(text):
        text = str(text or "")
        decoder = json.JSONDecoder()
        for index, char in enumerate(text):
            if char != "{":
                continue
            try:
                obj, _end = decoder.raw_decode(text[index:])
            except Exception:
                continue
            if isinstance(obj, dict):
                return obj
        return {}

    @staticmethod
    def _strip_generated_code(text):
        text = str(text or "").strip()
        fenced = re.findall(
            r"```(?:python|py)?\\s*(.*?)```",
            text,
            flags=re.I | re.S,
        )
        if fenced:
            text = max(fenced, key=len).strip()
        # Small models sometimes prepend one sentence despite being told not to.
        first_code = min(
            [position for position in [
                text.find("import "),
                text.find("from "),
                text.find("class Module"),
            ] if position >= 0] or [0]
        )
        if first_code > 0:
            text = text[first_code:]
        return text.strip()

    @staticmethod
    def _safe_generated_module_id(value, request):
        value = str(value or "").strip().lower()
        value = re.sub(r"[^a-z0-9_-]+", "_", value).strip("_")
        if value:
            return value[:64]
        lower = str(request or "").lower()
        if "conversation" in lower and any(word in lower for word in ("fluid", "flow", "smooth")):
            return "conversation_flow"
        words = [
            word for word in re.findall(r"[a-z0-9]+", lower)
            if word not in {
                "make", "create", "build", "add", "write", "generate", "develop",
                "a", "an", "the", "module", "modual", "plugin", "for", "apollo",
                "yourself", "to", "help", "me", "my", "our", "you", "and", "with",
            }
        ]
        return ("_".join(words[:5]) or "generated_apollo_module")[:64]

    @staticmethod
    def _syntax_error_context(source, exc, radius=4):
        lines = str(source or "").splitlines()
        line_no = int(getattr(exc, "lineno", 0) or 0)
        if not lines:
            return "<empty source>"
        if line_no <= 0:
            line_no = 1
        start = max(1, line_no - radius)
        end = min(len(lines), line_no + radius)
        return "\n".join(
            f"{idx:04d}: {lines[idx - 1]}"
            for idx in range(start, end + 1)
        )

    @staticmethod
    def _project_adapter_expected_functions(snapshot):
        found = []
        for item in (snapshot or {}).get("files", []) or []:
            path = str(item.get("path", ""))
            if not path.lower().endswith(".py"):
                continue
            try:
                tree = __import__("ast").parse(str(item.get("content", "")))
            except Exception:
                continue
            for node in tree.body:
                if isinstance(node, (__import__("ast").FunctionDef, __import__("ast").AsyncFunctionDef)):
                    if node.name.startswith("_") or node.name == "main":
                        continue
                    found.append(f"{path}:{node.name}")
        return found[:100]

    @classmethod
    def _build_deterministic_project_adapter_source(cls, project, snapshot, title=""):
        project = str(project or "").strip()
        expected = cls._project_adapter_expected_functions(snapshot)
        if not project or not expected:
            return ""
        title = str(title or f"{project} App")
        template = 'from pathlib import Path\nimport importlib.util\nimport inspect\nimport json\nimport sys\n\nPROJECT_NAME = __PROJECT_LITERAL__\nAPP_TITLE = __TITLE_LITERAL__\nEXPECTED_FUNCTIONS = __EXPECTED_LITERAL__\n\n\nclass Module:\n    def __init__(self, context=None):\n        self.context = context or {}\n        self._functions = None\n\n    def tools(self):\n        return [\n            {\n                "name": "list_functions",\n                "description": "List callable functions exposed by the converted Workspace project.",\n                "parameters": {"type": "object", "properties": {}},\n            },\n            {\n                "name": "run_function",\n                "description": "Run one converted project function with named arguments.",\n                "parameters": {\n                    "type": "object",\n                    "properties": {\n                        "function": {"type": "string"},\n                        "arguments": {"type": "object"},\n                    },\n                    "required": ["function"],\n                },\n            },\n        ]\n\n    def _base_dir(self):\n        raw = self.context.get("base_dir") or self.context.get("apollo_base_dir") or "."\n        return Path(raw).resolve()\n\n    def _project_root(self):\n        root = (self._base_dir() / "workspace" / PROJECT_NAME).resolve()\n        if not root.is_dir():\n            raise FileNotFoundError(f"Workspace project not found: {root}")\n        return root\n\n    @staticmethod\n    def _json_safe(value):\n        try:\n            json.dumps(value)\n            return value\n        except Exception:\n            return repr(value)\n\n    def _discover(self, refresh=False):\n        if self._functions is not None and not refresh:\n            return self._functions\n\n        root = self._project_root()\n        root_text = str(root)\n        if root_text not in sys.path:\n            sys.path.insert(0, root_text)\n\n        discovered = {}\n        python_files = [\n            path for path in sorted(root.rglob("*.py"))\n            if "__pycache__" not in path.parts\n            and not path.name.startswith("test_")\n            and path.name not in {"tests.py", "setup.py"}\n        ]\n\n        for index, path in enumerate(python_files):\n            try:\n                safe_project = PROJECT_NAME.lower().replace("-", "_").replace(" ", "_")\n                module_name = f"apollo_project_{safe_project}_{index}"\n                spec = importlib.util.spec_from_file_location(module_name, path)\n                if spec is None or spec.loader is None:\n                    continue\n                module = importlib.util.module_from_spec(spec)\n                spec.loader.exec_module(module)\n            except Exception:\n                continue\n\n            for name, value in vars(module).items():\n                if name.startswith("_") or name == "main":\n                    continue\n                if not inspect.isfunction(value):\n                    continue\n                if getattr(value, "__module__", None) != module.__name__:\n                    continue\n                key = name\n                if key in discovered:\n                    key = f"{path.stem}.{name}"\n                discovered[key] = {\n                    "callable": value,\n                    "signature": str(inspect.signature(value)),\n                    "doc": inspect.getdoc(value) or "",\n                    "source": str(path.relative_to(root)).replace("\\\\", "/"),\n                }\n\n        self._functions = discovered\n        return discovered\n\n    def _function_rows(self, refresh=False):\n        rows = []\n        for name, meta in self._discover(refresh=refresh).items():\n            rows.append({\n                "name": name,\n                "signature": meta["signature"],\n                "doc": meta["doc"],\n                "source": meta["source"],\n            })\n        return rows\n\n    def run(self, action, arguments):\n        arguments = arguments or {}\n        if action == "list_functions":\n            functions = self._function_rows(refresh=bool(arguments.get("refresh")))\n            return {"project": PROJECT_NAME, "functions": functions, "count": len(functions)}\n\n        if action == "run_function":\n            name = str(arguments.get("function", "")).strip()\n            functions = self._discover()\n            if name not in functions:\n                raise KeyError(f"Unknown project function: {name}")\n            kwargs = arguments.get("arguments") or {}\n            if not isinstance(kwargs, dict):\n                raise TypeError("arguments must be an object")\n            result = functions[name]["callable"](**kwargs)\n            return {"function": name, "result": self._json_safe(result)}\n\n        raise KeyError(action)\n\n    def self_test(self):\n        return bool(PROJECT_NAME and EXPECTED_FUNCTIONS)\n\n    @staticmethod\n    def _parse_ui_value(text):\n        text = str(text).strip()\n        if text == "":\n            return ""\n        try:\n            return json.loads(text)\n        except Exception:\n            try:\n                return float(text) if "." in text or "e" in text.lower() else int(text)\n            except Exception:\n                return text\n\n    def build_ui(self, parent=None, ui_context=None):\n        from PySide6.QtWidgets import (\n            QWidget, QVBoxLayout, QHBoxLayout, QLabel, QComboBox, QPushButton,\n            QFormLayout, QLineEdit, QPlainTextEdit, QScrollArea\n        )\n\n        page = QWidget(parent)\n        outer = QVBoxLayout(page)\n        outer.addWidget(QLabel(APP_TITLE))\n\n        top = QHBoxLayout()\n        selector = QComboBox()\n        refresh = QPushButton("Refresh")\n        top.addWidget(QLabel("Function"))\n        top.addWidget(selector, 1)\n        top.addWidget(refresh)\n        outer.addLayout(top)\n\n        scroll = QScrollArea()\n        scroll.setWidgetResizable(True)\n        form_host = QWidget()\n        form = QFormLayout(form_host)\n        scroll.setWidget(form_host)\n        outer.addWidget(scroll, 1)\n\n        run_button = QPushButton("Run")\n        result_box = QPlainTextEdit()\n        result_box.setReadOnly(True)\n        result_box.setPlaceholderText("Result or validation error")\n        outer.addWidget(run_button)\n        outer.addWidget(result_box, 1)\n\n        fields = {}\n\n        def clear_form():\n            while form.rowCount():\n                form.removeRow(0)\n            fields.clear()\n\n        def rebuild_form():\n            clear_form()\n            name = selector.currentText()\n            meta = self._discover().get(name)\n            if not meta:\n                return\n            signature = inspect.signature(meta["callable"])\n            for parameter in signature.parameters.values():\n                if parameter.kind in (parameter.VAR_POSITIONAL, parameter.VAR_KEYWORD):\n                    continue\n                edit = QLineEdit()\n                if parameter.default is not inspect._empty:\n                    edit.setPlaceholderText(str(parameter.default))\n                fields[parameter.name] = (edit, parameter)\n                form.addRow(parameter.name, edit)\n\n        def populate():\n            selector.blockSignals(True)\n            selector.clear()\n            try:\n                names = list(self._discover(refresh=True).keys())\n                selector.addItems(names)\n                result_box.setPlainText(f"Loaded {len(names)} function(s) from workspace/{PROJECT_NAME}.")\n            except Exception as exc:\n                result_box.setPlainText(f"{type(exc).__name__}: {exc}")\n            selector.blockSignals(False)\n            rebuild_form()\n\n        def execute():\n            name = selector.currentText()\n            if not name:\n                result_box.setPlainText("No callable project function was found.")\n                return\n            kwargs = {}\n            try:\n                for parameter_name, (edit, parameter) in fields.items():\n                    raw = edit.text().strip()\n                    if raw == "" and parameter.default is not inspect._empty:\n                        continue\n                    if raw == "":\n                        raise ValueError(f"{parameter_name} is required")\n                    kwargs[parameter_name] = self._parse_ui_value(raw)\n                payload = self.run("run_function", {"function": name, "arguments": kwargs})\n                result_box.setPlainText(json.dumps(payload, indent=2, default=str))\n            except Exception as exc:\n                result_box.setPlainText(f"{type(exc).__name__}: {exc}")\n\n        selector.currentTextChanged.connect(rebuild_form)\n        refresh.clicked.connect(populate)\n        run_button.clicked.connect(execute)\n        populate()\n        return page\n'
        template = template.replace("__PROJECT_LITERAL__", repr(project))
        template = template.replace("__TITLE_LITERAL__", repr(title))
        template = template.replace("__EXPECTED_LITERAL__", repr(expected))
        return template

    def _compile_module_candidate_call(
        self,
        request,
        contract,
        create_name,
        preferred_module_id="",
        preferred_name="",
        ui_required=False,
        adapter_context=None,
    ):
        """Compile a module without relying on the model to perform a complex tool call.

        Tool calling is the fragile part for small local models: create_candidate has
        large nested string arguments containing complete Python.  Apollo therefore
        asks for SIMPLE outputs, parses them itself, validates Python syntax locally,
        and constructs the real Module Factory call deterministically.
        """
        metadata_prompt = [
            {
                "role": "system",
                "content": (
                    "You are Apollo's module metadata compiler. Return ONLY a small JSON object "
                    "with keys module_id, name, description, version. module_id must use only "
                    "lowercase letters, digits, underscore or hyphen. Do not include source code, "
                    "Markdown or commentary."
                ),
            },
            {"role": "user", "content": str(request)},
        ]
        metadata = {}
        try:
            response = self.client.chat_once(metadata_prompt, tools=None)
            metadata = self._first_json_object(
                str((response.get("message", {}) or {}).get("content", "") or "")
            )
        except Exception:
            metadata = {}

        module_id = self._safe_generated_module_id(
            preferred_module_id or metadata.get("module_id"),
            request,
        )
        name = str(
            preferred_name or metadata.get("name") or module_id.replace("_", " ").title()
        )[:120]
        description = str(metadata.get("description") or ("Apollo module for: " + str(request)))[:800]
        version = str(metadata.get("version") or "1.0.0")[:32]

        code_system = (
            "You are Apollo's module.py compiler. Write ONLY complete valid Python source; "
            "no Markdown fences, no explanation and no tool-call JSON. The source MUST define "
            "class Module. __init__(self, context=None) must be safe. tools() must return the "
            "real tool definitions this feature needs. run(action, arguments) must implement "
            "those tools. self_test() must be non-interactive and safe. Do not perform network, "
            "GUI, audio, package installs, subprocesses or destructive actions at import time or "
            "inside self_test. Keep dependencies in the Python standard library unless the request "
            "absolutely requires an Apollo-installed dependency. The module is a pending candidate, "
            "not installed yet."
            + (
                " UI IS REQUIRED. class Module MUST implement build_ui(parent=None, ui_context=None). "
                "Import PySide6 widgets INSIDE build_ui, not at module import time. The returned QWidget "
                "must provide usable controls for the requested feature and call the module's real logic."
                if ui_required else ""
            )
            + self._tts_authoring_hint(request)
            + "\n\nOFFICIAL APOLLO MODULE CONTRACT:\n"
            + json.dumps(contract, ensure_ascii=False, default=str)
        )
        code_messages = [
            {"role": "system", "content": code_system},
            {
                "role": "user",
                "content": (
                    f"Module id: {module_id}\nName: {name}\nDescription: {description}\n\n"
                    f"USER REQUEST:\n{request}\n\nReturn module.py source only."
                ),
            },
        ]

        module_code = ""
        error = ""
        last_invalid = ""
        seen_hashes = set()

        for attempt in range(5):
            try:
                response = self.client.chat_once(code_messages, tools=None)
                raw_source = str((response.get("message", {}) or {}).get("content", "") or "")
                module_code = self._strip_generated_code(raw_source)
                digest = __import__("hashlib").sha256(module_code.encode("utf-8", "ignore")).hexdigest()
                if digest in seen_hashes:
                    raise ValueError("Model repeated the same invalid source")
                seen_hashes.add(digest)
                tree = __import__("ast").parse(module_code)
                has_module = any(
                    isinstance(node, __import__("ast").ClassDef) and node.name == "Module"
                    for node in tree.body
                )
                if not has_module:
                    raise ValueError("Generated source does not define class Module")
                if ui_required:
                    module_class = next(
                        node for node in tree.body
                        if isinstance(node, __import__("ast").ClassDef) and node.name == "Module"
                    )
                    method_names = {
                        node.name for node in module_class.body
                        if isinstance(node, (__import__("ast").FunctionDef, __import__("ast").AsyncFunctionDef))
                    }
                    if "build_ui" not in method_names:
                        raise ValueError("UI module does not define build_ui")
                error = ""
                break
            except Exception as exc:
                error = f"{type(exc).__name__}: {exc}"
                last_invalid = module_code
                location = (
                    self._syntax_error_context(module_code, exc)
                    if isinstance(exc, SyntaxError)
                    else "<structural validation error>"
                )
                if module_code:
                    code_messages.append({"role": "assistant", "content": module_code})
                code_messages.append({
                    "role": "system",
                    "content": (
                        "The Python source immediately above is the exact invalid module.py you must repair. "
                        f"Compiler error: {error}.\n"
                        f"ERROR LOCATION:\n{location}\n\n"
                        "Return ONLY the entire corrected module.py. Preserve all valid project functionality. "
                        "Do not add Markdown, commentary, placeholders or pseudo-code. Check every quote, bracket, "
                        "indent and f-string before answering."
                    ),
                })

        fallback_used = False
        if error or not module_code:
            adapter_context = adapter_context or {}
            fallback_source = self._build_deterministic_project_adapter_source(
                adapter_context.get("project", ""),
                adapter_context.get("snapshot", {}) or {},
                preferred_name or name,
            )
            if fallback_source:
                try:
                    tree = __import__("ast").parse(fallback_source)
                    module_class = next(
                        node for node in tree.body
                        if isinstance(node, __import__("ast").ClassDef) and node.name == "Module"
                    )
                    methods = {
                        node.name for node in module_class.body
                        if isinstance(node, (__import__("ast").FunctionDef, __import__("ast").AsyncFunctionDef))
                    }
                    if not {"tools", "run", "self_test", "build_ui"}.issubset(methods):
                        raise ValueError("deterministic adapter missing required Module methods")
                    module_code = fallback_source
                    error = ""
                    fallback_used = True
                except Exception as fallback_exc:
                    error = f"{type(fallback_exc).__name__}: {fallback_exc}"

        if error or not module_code:
            return None, {
                "stage": "module_code",
                "error": error or "empty module source",
                "module_id": module_id,
                "repair_attempts": 5,
                "last_source_chars": len(last_invalid),
            }

        call = {
            "name": create_name,
            "arguments": {
                "module_id": module_id,
                "name": name,
                "description": description,
                "module_code": module_code,
                "version": version,
                **(
                    {
                        "ui": {
                            "enabled": True,
                            "title": name,
                            "default_placement": "apps",
                        }
                    }
                    if ui_required else {}
                ),
            },
        }
        return call, {
            "stage": "compiled_adapter_fallback" if fallback_used else "compiled",
            "module_id": module_id,
            "source_chars": len(module_code),
            "fallback_adapter": bool(fallback_used),
        }

    def _run_explicit_module_build(self):
        """
        Deterministic entry into module-authoring mode.

        The previous controller merely *told* Qwen to call module_factory. A
        small local model could ignore that and print an imaginary JSON example.
        This path executes get_contract for real first, then gives Qwen only the
        real module-factory create tool. If native tool calling fails, Apollo
        retries once using the text-JSON interception format.
        """
        request = (
            self._explicit_module_request_body()
        )

        if not request:
            return None

        authoring_context = self._project_module_authoring_context(request)
        if authoring_context.get("error"):
            content = (
                "Apollo understood this as a project-to-module conversion, but could not prepare the real "
                "source context: " + str(authoring_context.get("error")) + " No module was created."
            )
            self.signals.chunk.emit(content)
            return content
        authoring_request = str(authoring_context.get("request") or request)

        if not self.module_manager:
            content = (
                "Apollo cannot create the requested module because the module "
                "manager is unavailable. No files were created."
            )
            self.signals.chunk.emit(content)
            return content

        factory_tools = self._module_factory_tools()

        tool_by_name = {
            str(
                (tool.get("function", {}) or {}).get(
                    "name",
                    "",
                )
            ): tool
            for tool in factory_tools
        }

        contract_name = (
            "module_factory__get_contract"
        )
        create_name = (
            "module_factory__create_candidate"
        )

        if (
            contract_name not in tool_by_name
            or create_name not in tool_by_name
        ):
            content = (
                "Apollo's Module Factory is not installed/enabled, so I did not "
                "pretend to create a module. No pending files were written."
            )
            self.signals.chunk.emit(content)
            return content

        # Step 1 is real and deterministic: always read the actual contract.
        try:
            contract = self.module_manager.execute_tool(
                contract_name,
                {},
            )
        except Exception as exc:
            content = (
                "Apollo could not read the real Module Factory contract: "
                f"{type(exc).__name__}: {exc}. No module files were created."
            )
            self.signals.chunk.emit(content)
            return content

        self._record_direct_tool(
            contract_name,
            result=contract,
        )

        create_tool = [
            tool_by_name[
                create_name
            ]
        ]

        authoring_system = (
            "APOLLO MODULE AUTHORING MODE.\n"
            "A real module_factory__get_contract call already completed.\n"
            "You MUST create the requested Apollo module as REAL pending files now. "
            "Do not explain a hypothetical module and do not print sample tool JSON. "
            "Call module_factory__create_candidate exactly once using the real schema. "
            "The module must define class Module and follow the contract. "
            "Keep dependencies minimal and validation-safe. "
            "Do NOT invent calls such as module_factory__validate; validation is run "
            "automatically by Apollo after create_candidate/update_candidate_file. "
            "Do not output Python examples showing imaginary Module Factory calls. "
            "Do not install or enable the module; it must remain pending for user approval."
            + self._tts_authoring_hint(
                request
            )
            + "\n\nREAL CONTRACT RESULT:\n"
            + json.dumps(
                contract,
                ensure_ascii=False,
                default=str,
            )
        )

        conversation = [
            {
                "role": "system",
                "content": authoring_system,
            },
            {
                "role": "user",
                "content": authoring_request,
            },
        ]

        allowed = {
            create_name
        }

        calls = []
        response = None

        # Conversion gets the reliable compiler path first because the real project
        # source must be preserved and UI metadata must be deterministic.
        if authoring_context.get("is_conversion"):
            compiled_call, compiler_info = self._compile_module_candidate_call(
                authoring_request,
                contract,
                create_name,
                preferred_module_id=authoring_context.get("preferred_module_id", ""),
                preferred_name=authoring_context.get("preferred_name", ""),
                ui_required=bool(authoring_context.get("ui_required")),
                adapter_context=authoring_context,
            )
            if compiled_call:
                calls = [compiled_call]
                self._record_direct_tool(
                    "project_to_module_compiler",
                    result={
                        **compiler_info,
                        "source_project": authoring_context.get("project", ""),
                        "ui_required": bool(authoring_context.get("ui_required")),
                    },
                )
            else:
                content = (
                    "Apollo inspected the real Workspace project but could not compile a valid UI module. "
                    "No fake success was reported and no module was created. Compiler result: "
                    + json.dumps(compiler_info, ensure_ascii=False, default=str)
                )
                self.signals.chunk.emit(content)
                return content

        if not calls:
            try:
                response = self.client.chat_once(
                    conversation,
                    tools=create_tool,
                )
                assistant_message = (
                    response.get(
                        "message",
                        {},
                    )
                    or {}
                )

                calls = self._native_tool_calls(
                    assistant_message,
                    allowed,
                )

                if not calls:
                    calls = self._extract_text_tool_calls(
                        str(
                            assistant_message.get(
                                "content",
                                "",
                            )
                            or ""
                        ),
                        allowed,
                    )

            except Exception:
                calls = []

        # One strict retry for local models that narrate instead of tool-calling.
        if not calls:
            retry_messages = list(
                conversation
            )
            retry_messages.append({
                "role": "system",
                "content": (
                    "Your previous response did not execute anything. "
                    "Return ONLY one exact JSON object in this shape: "
                    '{"name":"module_factory__create_candidate","arguments":{...}}. '
                    "Use the REAL create_candidate schema from the contract. "
                    "Do not use module_name/module_files. Do not call a nonexistent "
                    "module_factory__validate function. Do not write Step 1/Step 2 prose, "
                    "Python call examples, or Markdown fences."
                ),
            })

            try:
                retry = self.client.chat_once(
                    retry_messages,
                    tools=None,
                )
                retry_content = str(
                    (
                        retry.get(
                            "message",
                            {},
                        )
                        or {}
                    ).get(
                        "content",
                        "",
                    )
                    or ""
                )

                calls = self._extract_text_tool_calls(
                    retry_content,
                    allowed,
                )
            except Exception:
                calls = []

        if not calls:
            # V7.5.04 fallback: stop asking a small model to serialize a huge Python
            # program inside tool-call JSON. Compile simple metadata + raw Python,
            # then Apollo constructs the REAL create_candidate call itself.
            compiled_call, compiler_info = self._compile_module_candidate_call(
                authoring_request,
                contract,
                create_name,
                preferred_module_id=authoring_context.get("preferred_module_id", ""),
                preferred_name=authoring_context.get("preferred_name", ""),
                ui_required=bool(authoring_context.get("ui_required")),
                adapter_context=authoring_context,
            )
            if compiled_call:
                calls = [compiled_call]
                self._record_direct_tool(
                    "module_authoring_compiler",
                    result=compiler_info,
                )
            else:
                content = (
                    "Apollo read the real Module Factory contract, but both native tool calling "
                    "and the deterministic module-authoring compiler failed. No fake success was "
                    "reported and no module was created. Compiler result: "
                    + json.dumps(compiler_info, ensure_ascii=False, default=str)
                )
                self.signals.chunk.emit(content)
                return content

        results, terminal_success, _ = (
            self._execute_calls(
                calls[:1]
            )
        )

        if not results:
            content = (
                "Apollo received no executable Module Factory result. "
                "No module was created."
            )
            self.signals.chunk.emit(content)
            return content

        name, tool_content, payload = (
            results[-1]
        )

        if payload.get("ok") and terminal_success:
            module_id = str(
                calls[0].get(
                    "arguments",
                    {},
                ).get(
                    "module_id",
                    "",
                )
            ).strip()

            validation = payload.get(
                "candidate_validation",
                {},
            )

            content = (
                f"Created real pending Apollo module `{module_id}` in "
                f"`pending_modules/{module_id}`. "
                "Validation passed. It is NOT installed or enabled yet; "
                "approve it from the Modules page when you are ready."
            )

            self.signals.chunk.emit(content)
            return content

        # If creation happened but validation failed, hand the real result back
        # to the normal guarded loop rather than claiming success.
        result_text = json.dumps(
            payload,
            ensure_ascii=False,
            default=str,
        )

        content = (
            "Apollo created a pending candidate, but validation did not pass, "
            "so it was not accepted. Real validation result:\n"
            + result_text
        )
        self.signals.chunk.emit(content)
        return content

    def _file_builder_tools(self):
        all_tools = (
            self.module_manager.ollama_tools()
            if self.module_manager
            else []
        )
        return [
            tool
            for tool in all_tools
            if str((tool.get("function", {}) or {}).get("name", "")).startswith("file_builder__")
        ]

    def _run_explicit_project_update(self):
        """Update the established real Workspace project rather than starting a generic tool loop."""
        update = self._explicit_project_update()
        if not update:
            return None
        if not self.module_manager:
            content = "Apollo cannot update the project because File Builder is unavailable. No files were changed."
            self.signals.chunk.emit(content)
            return content

        project = str(update["project"])
        request = str(update["request"])

        try:
            snapshot = self._project_source_snapshot(project)
        except Exception as exc:
            content = (
                f"Apollo understood this as an update to `{project}`, but could not inspect the real project: "
                f"{type(exc).__name__}: {exc}. No files were changed."
            )
            self.signals.chunk.emit(content)
            return content

        tools = self._file_builder_tools()
        tool_by_name = {
            str((tool.get("function", {}) or {}).get("name", "")): tool
            for tool in tools
        }
        write_name = "file_builder__write_files"
        if write_name not in tool_by_name:
            content = "Apollo's real File Builder is unavailable. No files were changed."
            self.signals.chunk.emit(content)
            return content

        allowed = {write_name}
        write_tool = [tool_by_name[write_name]]
        source_context = json.dumps(snapshot, ensure_ascii=False, default=str)
        system = (
            "APOLLO EXISTING PROJECT UPDATE MODE.\n"
            f"The real project is `workspace/{project}` and it already exists. "
            "Modify that project; do not create a new project and do not merely explain code. "
            "You MUST call file_builder__write_files. Return ONLY changed/new files in the files array; "
            "untouched files remain on disk. Preserve existing useful behavior unless the request requires changing it. "
            "Generated source and tool JSON are INTERNAL and must never be displayed to the user. "
            "Apollo will statically verify the whole existing project after writing."
        )
        conversation = [
            {"role": "system", "content": system},
            {
                "role": "user",
                "content": (
                    f"PROJECT: {project}\n"
                    f"USER UPDATE REQUEST:\n{request}\n\n"
                    f"CURRENT REAL PROJECT SNAPSHOT:\n{source_context}"
                ),
            },
        ]

        def get_call(messages, tools_arg):
            try:
                response = self.client.chat_once(messages, tools=tools_arg)
                message = response.get("message", {}) or {}
                calls = self._native_tool_calls(message, allowed)
                if not calls:
                    calls = self._extract_text_tool_calls(
                        str(message.get("content", "") or ""),
                        allowed,
                    )
                return calls
            except Exception:
                return []

        calls = get_call(conversation, write_tool)
        if not calls:
            retry = list(conversation)
            retry.append({
                "role": "system",
                "content": (
                    "The previous reply did not execute the update. Return ONLY one JSON tool object using "
                    "file_builder__write_files, project exactly `" + project + "`, and only changed/new files. "
                    "No Markdown and no explanation."
                ),
            })
            calls = get_call(retry, None)

        if not calls:
            content = (
                f"Apollo understood this as an update to `{project}`, but the selected model failed to produce "
                "a valid real File Builder update. No fake success was reported and no files were changed."
            )
            self.signals.chunk.emit(content)
            return content

        call = calls[0]
        arguments = call.setdefault("arguments", {})
        arguments["project"] = project
        arguments["overwrite"] = True
        calls = [call]

        last_payload = None
        for attempt in range(2):
            results, _terminal_success, _duplicate = self._execute_calls(calls)
            if not results:
                break
            _name, _tool_content, payload = results[-1]
            last_payload = payload
            if not payload.get("ok"):
                break

            result = payload.get("result") or {}
            verification = result.get("verification") or {}
            if verification.get("ok", True):
                changed = result.get("files") or []
                content = (
                    f"Done — `{project}` was updated in `workspace/{project}`. "
                    f"{len(changed)} file(s) were changed/written and static verification passed."
                )
                self.signals.chunk.emit(content)
                return content

            if attempt == 0:
                try:
                    fresh_snapshot = self._project_source_snapshot(project)
                except Exception:
                    fresh_snapshot = snapshot
                repair_messages = [
                    {"role": "system", "content": system},
                    {
                        "role": "user",
                        "content": (
                            f"Repair the existing `{project}` project after the attempted update.\n"
                            f"Original request: {request}\n\n"
                            f"STATIC VERIFICATION ERRORS:\n{json.dumps(verification, ensure_ascii=False, default=str)}\n\n"
                            f"CURRENT PROJECT AFTER FAILED WRITE:\n{json.dumps(fresh_snapshot, ensure_ascii=False, default=str)}"
                        ),
                    },
                ]
                calls = get_call(repair_messages, write_tool)
                if calls:
                    calls[0].setdefault("arguments", {})["project"] = project
                    calls[0]["arguments"]["overwrite"] = True
                    calls = calls[:1]
                    continue
            break

        content = (
            f"Apollo attempted the real update to `{project}`, but verification/execution did not pass. "
            "No fake success was reported. Result: "
            + json.dumps(last_payload or {}, ensure_ascii=False, default=str)[:3500]
        )
        self.signals.chunk.emit(content)
        return content

    def _run_explicit_file_build(self):
        """Force Chat/Coding/Workshop build requests to create real files, not narrated code fences."""
        request = self._explicit_file_request_body()
        if not request or self._looks_like_module_build_request(request):
            return None
        if not self.module_manager:
            content = "Apollo's file builder is unavailable. No files were created."
            self.signals.chunk.emit(content)
            return content

        tools = self._file_builder_tools()
        tool_by_name = {str((t.get("function", {}) or {}).get("name", "")): t for t in tools}
        write_name = "file_builder__write_files"
        if write_name not in tool_by_name:
            content = "Apollo's real file-builder tool is not installed/enabled. No files were created."
            self.signals.chunk.emit(content)
            return content

        write_tool = [tool_by_name[write_name]]
        allowed = {write_name}
        system = (
            "APOLLO REAL PROJECT BUILD MODE.\n"
            "The user requested REAL FILES, not Markdown code blocks. "
            "You MUST call file_builder__write_files. Do not merely print code. "
            "Generated source code and tool JSON are INTERNAL build payload and must never be shown in user chat. "
            "Create the complete project in ONE batch: every Python/HTML/CSS/JS/config/README file needed, "
            "with imports, relative paths, entrypoints and filenames that agree with each other. "
            "Prefer a small coherent project over disconnected snippets. Include a README with run instructions. "
            "Generated code is statically verified after writing and is never executed automatically."
        )
        conversation = [
            {"role": "system", "content": system},
            {"role": "user", "content": request},
        ]

        def get_call(messages, tools_arg):
            try:
                response = self.client.chat_once(messages, tools=tools_arg)
                msg = response.get("message", {}) or {}
                calls = self._native_tool_calls(msg, allowed)
                if not calls:
                    calls = self._extract_text_tool_calls(str(msg.get("content", "") or ""), allowed)
                return calls
            except Exception:
                return []

        calls = get_call(conversation, write_tool)
        if not calls:
            retry = list(conversation)
            retry.append({
                "role": "system",
                "content": (
                    "Your previous reply did not create files. Return ONLY one JSON tool object: "
                    '{"name":"file_builder__write_files","arguments":{"project":"...","files":[{"path":"...","content":"..."}],"overwrite":true}}. '
                    "No Markdown fences and no explanation."
                ),
            })
            calls = get_call(retry, None)

        if not calls:
            content = (
                "Apollo entered real project-build mode, but the selected model still failed to produce "
                "a valid file_builder call. No fake success was reported and no files were created."
            )
            self.signals.chunk.emit(content)
            return content

        # Allow one automatic repair pass if static verification finds a real integration/syntax problem.
        last_payload = None
        for attempt in range(2):
            results, terminal_success, _ = self._execute_calls(calls[:1])
            if not results:
                break
            _, _, payload = results[-1]
            last_payload = payload
            if payload.get("ok"):
                result = payload.get("result") or {}
                verification = result.get("verification") or {}
                if verification.get("ok", True):
                    project = result.get("project", "project")
                    files = result.get("files", [])
                    content = (
                        f"Done — `{project}` was created as real files in `workspace/{project}`. "
                        f"{len(files)} file(s) were written and static verification passed."
                    )
                    self.signals.chunk.emit(content)
                    return content

                if attempt == 0:
                    repair_messages = list(conversation)
                    repair_messages.append({"role": "system", "content": (
                        "The real files were written, but static verification found problems. "
                        "Repair the project in ONE replacement write_files call. Return only the tool call.\n"
                        + json.dumps(verification, ensure_ascii=False, default=str)
                    )})
                    calls = get_call(repair_messages, write_tool)
                    if not calls:
                        calls = get_call(repair_messages + [{"role": "system", "content": "Return only the JSON write_files tool object."}], None)
                    if calls:
                        continue
            break

        detail = json.dumps(last_payload or {}, ensure_ascii=False, default=str)
        content = (
            "Apollo wrote project files but could not get the project through static verification. "
            "It did not pretend the project was complete. Real result: " + detail[:5000]
        )
        self.signals.chunk.emit(content)
        return content

    def _select_tools(self, all_tools):
        """
        Qwen 7B behaves much more reliably when it is not shown dozens of tools
        that are irrelevant to the current task.
        """
        text = self._request_text()
        lower = text.lower()

        # Explicit Pile requests should never expose unrelated tools such as
        # self_awareness. V6.6.7 allowed Qwen to panic after a timeout and start
        # describing Apollo's project instead of continuing the knowledge task.
        pile_phrases = (
            "the pile",
            "pile online",
            "pile knowledge",
            "learn from pile",
            "learn about",
        )

        explicit_pile = (
            "pile" in lower
            and any(phrase in lower for phrase in pile_phrases)
        )

        if explicit_pile:
            selected = []
            for tool in all_tools:
                name = str(
                    (tool.get("function", {}) or {}).get("name", "")
                )
                if name.startswith("pile_knowledge__"):
                    selected.append(tool)

            return selected or all_tools

        if "apollo workshop request:" in lower:
            # Explicit Workshop full-capability mode is the OS-style surface.
            # Ordinary Chat remains filtered so a simple hello never sees the full tool catalog.
            return all_tools

        if "self improvement workshop request:" in lower:
            allowed_prefixes = (
                "self_awareness__",
                "module_factory__",
                "file_builder__",
                "memory_bank__",
            )
            selected = []
            for tool in all_tools:
                name = str((tool.get("function", {}) or {}).get("name", ""))
                if any(name.startswith(prefix) for prefix in allowed_prefixes):
                    selected.append(tool)
            return selected

        if "coding workspace request:" not in lower:
            # Ordinary conversation must stay ordinary. Showing every installed
            # tool to a small local model can make a simple "hello" turn into
            # requests for function names/arguments or fake JSON calls. Only expose
            # tool families when the newest request clearly asks for an action.
            prefixes = []

            if any(x in lower for x in (
                "search the web", "search web", "look up", "look online",
                "web search", "latest online", "current online",
            )):
                prefixes += ["web_explorer__", "training_module__"]

            if any(x in lower for x in (
                "memory bank", "remember this", "search memory", "forget memory",
                "list memories",
            )):
                prefixes += ["memory_bank__", "chat_memory_module__"]

            if any(x in lower for x in (
                "gpu", "graphics card", "vram",
            )):
                prefixes += ["gpu_monitor__"]

            if any(x in lower for x in (
                "your source", "your code", "your architecture", "how are you built",
                "inspect yourself", "self awareness",
            )):
                prefixes += ["self_awareness__"]

            if any(x in lower for x in (
                "train neural", "neural status", "predict label", "neural network",
            )):
                prefixes += ["neural_learning__"]

            if any(x in lower for x in (
                "speak aloud", "read aloud", "say this", "text to speech",
                "speech to text", "dictate", "microphone", "list voices",
            )):
                prefixes += ["text_to_speech__"]

            if any(x in lower for x in (
                "calculate", "calculator",
            )):
                prefixes += ["calculator__"]

            if not prefixes:
                return []

            selected = []
            for tool in all_tools:
                name = str((tool.get("function", {}) or {}).get("name", ""))
                if any(name.startswith(prefix) for prefix in prefixes):
                    selected.append(tool)

            return selected

        if self._is_apollo_module_request(text):
            allowed_prefixes = (
                "module_factory__",
                "self_awareness__",
            )
        else:
            allowed_prefixes = (
                "file_builder__",
                "self_awareness__",
            )

            # Let a visualization inspect Apollo's own neural subsystem if asked.
            if "neural" in lower or "nural" in lower:
                allowed_prefixes += ("neural_learning__",)

            if "gpu" in lower:
                allowed_prefixes += ("gpu_monitor__",)

        selected = []
        for tool in all_tools:
            name = str(
                (tool.get("function", {}) or {}).get("name", "")
            )
            if any(name.startswith(prefix) for prefix in allowed_prefixes):
                selected.append(tool)

        return selected or all_tools

    @staticmethod
    def _fingerprint(call):
        return (
            call.get("name", ""),
            json.dumps(
                call.get("arguments", {}),
                sort_keys=True,
                ensure_ascii=False,
                default=str,
            ),
        )

    def _final_summary_text(self):
        if not self._tool_history:
            return (
                "No Apollo tool action was executed for this request."
            )

        lines = []

        for entry in self._tool_history[-12:]:
            name = entry.get("tool", "tool")
            ok = entry.get("ok", False)

            if ok:
                result = entry.get("result")

                if name == "file_builder__write_files" and isinstance(result, dict):
                    files = result.get("files", [])
                    lines.append(
                        f"- {name}: created {len(files)} file(s): "
                        + ", ".join(str(x) for x in files[:12])
                    )

                elif name == "file_builder__write_file" and isinstance(result, dict):
                    lines.append(
                        f"- {name}: created {result.get('relative_path', result.get('path', 'file'))}"
                    )

                elif (
                    name == "pile_knowledge__learn_from_pile"
                    and isinstance(result, dict)
                ):
                    lines.append(
                        "- pile_knowledge__learn_from_pile: "
                        f"learned {result.get('chunks_added', 0)} chunk(s) "
                        f"from {result.get('documents_found', 0)} document(s); "
                        f"datasets: {', '.join(result.get('datasets_searched', []))}"
                    )

                elif name.startswith("module_factory__"):
                    validation = entry.get("candidate_validation")
                    if validation and validation.get("ok"):
                        lines.append(
                            f"- {name}: candidate passed validation and is waiting for approval."
                        )
                    else:
                        lines.append(f"- {name}: completed.")

                else:
                    lines.append(f"- {name}: completed.")
            else:
                lines.append(
                    f"- {name}: failed — {entry.get('error', 'unknown error')}"
                )

        return "\n".join(lines)

    def _force_final_answer(self, conversation, reason):
        """
        Final assistant turn with the tool catalog removed completely.

        Even if Qwen previously got trapped calling tools, it now has no callable
        tools and is explicitly told to summarise the real completed state.
        """
        summary = self._final_summary_text()

        final_messages = list(conversation)
        final_messages.append({
            "role": "system",
            "content": (
                "TOOL EXECUTION IS NOW FINISHED AND TOOLS ARE DISABLED FOR THIS TURN.\n"
                "Do NOT output a JSON tool call. Do NOT ask to call another tool.\n"
                "Give the user the final answer based only on actions that actually "
                "completed. If something is incomplete, say exactly what remains.\n\n"
                f"Reason tool execution ended: {reason}\n\n"
                "Completed tool history:\n"
                f"{summary}\n\n"
                "For file projects, confirm the real project location and verification result, but do NOT reproduce "
                "generated source code or internal tool-call JSON unless the user explicitly asks to see code. "
                "For Apollo modules that passed validation, say they are "
                "PENDING and still require the user's approval in Modules."
            ),
        })

        try:
            response = self.client.chat_once(final_messages, tools=None)
            content = str(
                (response.get("message", {}) or {}).get("content", "") or ""
            ).strip()
        except Exception:
            content = ""

        # If the model still prints another tool-shaped object even though tools
        # are disabled, don't expose another fake action. Return a deterministic
        # truthful summary from the actual execution history instead.
        allowed_names = set()
        if self.module_manager:
            allowed_names = self._allowed_tool_names(
                self.module_manager.ollama_tools()
            )

        fake_calls = (
            extract_text_tool_calls(content, allowed_names)
            if content and allowed_names
            else []
        )

        if not content or fake_calls:
            content = (
                "Apollo finished the automatic tool phase.\n\n"
                + summary
            )

        self.signals.chunk.emit(content)
        return content

    def _execute_calls(self, calls):
        results = []
        terminal_success = False
        duplicate_detected = False

        for call in calls[: self.MAX_TOOL_CALLS_PER_ROUND]:
            if self._cancelled:
                break

            if self._total_tool_calls >= self.MAX_TOTAL_TOOL_CALLS:
                break

            name = call["name"]
            arguments = call.get("arguments", {})
            fingerprint = self._fingerprint(call)

            self._call_counts[fingerprint] += 1

            if self._call_counts[fingerprint] > self.MAX_IDENTICAL_CALLS:
                duplicate_detected = True
                payload = {
                    "ok": False,
                    "tool": name,
                    "error": (
                        "Duplicate tool call blocked. Apollo already executed this "
                        "exact tool with these exact arguments. Inspect the previous "
                        "result instead of repeating it."
                    ),
                    "duplicate_blocked": True,
                }

                tool_content = json.dumps(
                    payload,
                    ensure_ascii=False,
                    default=str,
                )
                self.signals.tool_used.emit(name, tool_content)
                results.append((name, tool_content, payload))
                self._tool_history.append(payload)
                continue

            self._total_tool_calls += 1

            try:
                result = self.module_manager.execute_tool(name, arguments)
                payload = {
                    "ok": True,
                    "tool": name,
                    "result": result,
                }

                if (
                    name == "todo_list__achieve_to_do_list"
                    and isinstance(result, dict)
                ):
                    payload["next_action"] = (
                        "Achievement plan loaded. Work through returned open items "
                        "with real Apollo tools. After each real success, call "
                        "todo_list__complete_to_do_item with that item's id. "
                        "Do not mark manual, unsupported or failed work complete."
                    )

                # A successful Pile learning request is terminal. The knowledge is
                # already stored; do not let Qwen wander into unrelated tools afterward.
                if (
                    name == "pile_knowledge__learn_from_pile"
                    and isinstance(result, dict)
                ):
                    chunks_added = int(
                        result.get("chunks_added", 0) or 0
                    )

                    if chunks_added > 0:
                        terminal_success = True
                        payload["next_action"] = (
                            "Pile knowledge was stored successfully. STOP using tools "
                            "and tell the user what topic was learned, how many chunks "
                            "were added, and which Pile subset datasets were searched."
                        )

                # A batch project write is intentionally terminal. The whole point
                # is to avoid one tool round per file and endless "verify/rewrite".
                if name == "file_builder__write_files":
                    verification = (result or {}).get("verification", {}) if isinstance(result, dict) else {}
                    if verification.get("ok", True):
                        terminal_success = True
                        payload["next_action"] = (
                            "Project files were created and static integration checks passed. "
                            "Stop using tools and give the user the real file list/run instructions."
                        )
                    else:
                        payload["next_action"] = (
                            "The real files were written but static verification failed. "
                            "Repair only the reported syntax/local-integration problems; do not claim success yet."
                        )

                # Module candidates are automatically validated after creation/edit.
                if name in {
                    "module_factory__create_candidate",
                    "module_factory__update_candidate_file",
                }:
                    module_id = str(arguments.get("module_id", "")).strip()

                    if module_id:
                        self.module_manager.refresh_pending()
                        record = self.module_manager.get_pending(module_id)

                        if record is not None:
                            validation = self.module_manager.validate_folder(
                                record["folder"],
                                timeout=15,
                            )
                            record["validation"] = validation
                            payload["candidate_validation"] = validation

                            if validation.get("ok"):
                                terminal_success = True
                                payload["next_action"] = (
                                    "Candidate PASSED validation/tests. STOP calling "
                                    "tools. It is still pending and requires explicit "
                                    "user approval in Modules."
                                )
                            else:
                                payload["next_action"] = (
                                    "Candidate FAILED validation. Modify only the "
                                    "specific broken pending-module file(s), then let "
                                    "Apollo validate again. Do not recreate an identical "
                                    "candidate and do not use file_builder."
                                )

            except Exception as exc:
                payload = {
                    "ok": False,
                    "tool": name,
                    "error": f"{type(exc).__name__}: {exc}",
                }

                # This specific conflict used to create an infinite loop:
                # Coding page said file_builder while file_builder correctly blocked
                # Apollo module paths. Make the correction explicit.
                if (
                    name.startswith("file_builder__")
                    and "extension modules" in str(exc).lower()
                ):
                    payload["next_action"] = (
                        "This is an Apollo extension-module request. Use "
                        "module_factory__get_contract and module_factory__create_candidate. "
                        "Do not call file_builder again for this request."
                    )

            tool_content = json.dumps(
                payload,
                ensure_ascii=False,
                default=str,
            )

            self.signals.tool_used.emit(name, tool_content)
            results.append((name, tool_content, payload))
            self._tool_history.append(payload)

        return results, terminal_success, duplicate_detected

    def _run_with_modules(self):
        # Explicit module-build requests from Chat, Coding Workspace, Workshop or
        # Self-Improvement Workshop enter Module Factory mode deterministically. This
        # prevents the local model from narrating fake tool calls instead of writing
        # real pending files.
        direct_module = self._run_explicit_module_build()

        if direct_module is not None:
            return direct_module

        direct_project_update = self._run_explicit_project_update()
        if direct_project_update is not None:
            return direct_project_update

        direct_project = self._run_explicit_file_build()
        if direct_project is not None:
            return direct_project

        # Simple To-Do List management is deterministic so adding, removing and
        # ticking tasks does not depend on Qwen choosing the correct tool.
        direct_to_do = self._run_simple_to_do()

        if direct_to_do is not None:
            return direct_to_do

        # Explicit Pile requests bypass Qwen's tool-selection decision entirely.
        # This prevents a local model from answering from memory instead of
        # actually accessing the requested source.
        direct_pile = self._run_explicit_pile()

        if direct_pile is not None:
            return direct_pile

        achievement = self._prepare_to_do_achievement()

        if achievement is not None:
            if achievement.get("empty"):
                content = achievement.get(
                    "system",
                    "The To-Do List is complete.",
                )
                self.signals.chunk.emit(content)
                return content

            self.messages.append({
                "role": "system",
                "content": achievement.get(
                    "system",
                    "",
                ),
            })

        all_tools = (
            self.module_manager.ollama_tools()
            if self.module_manager
            else []
        )

        tools = self._select_tools(all_tools)

        if not tools:
            return self._normal_stream(self.messages)

        allowed_names = self._allowed_tool_names(tools)
        conversation = list(self.messages)
        used_any_tool = False

        for round_index in range(self.MAX_TOOL_ROUNDS):
            if self._cancelled:
                return ""

            try:
                response = self.client.chat_once(
                    conversation,
                    tools=tools,
                )
            except Exception:
                if not used_any_tool:
                    return self._normal_stream(self.messages)
                raise

            assistant_message = response.get("message", {}) or {}
            content = str(
                assistant_message.get("content", "") or ""
            )

            native_calls = self._native_tool_calls(
                assistant_message,
                allowed_names,
            )

            text_calls = []

            if not native_calls:
                text_calls = self._extract_text_tool_calls(
                    content,
                    allowed_names,
                )

            calls = native_calls or text_calls

            if not calls:
                if content and self._looks_like_unexecuted_tool_json(content):
                    conversation.append({
                        "role": "assistant",
                        "content": content,
                    })
                    return self._force_final_answer(
                        conversation,
                        (
                            "The model emitted internal tool-shaped JSON, but Apollo did not execute that call. "
                            "Do not repeat the JSON. Respond naturally, do not claim the action happened, and state "
                            "what actually happened or what is still required."
                        ),
                    )

                if content:
                    self.signals.chunk.emit(content)
                    return content

                if used_any_tool:
                    return self._force_final_answer(
                        conversation,
                        "The model returned no further tool call after completed work.",
                    )

                return self._normal_stream(self.messages)

            used_any_tool = True

            if native_calls:
                conversation.append(assistant_message)
            else:
                conversation.append({
                    "role": "assistant",
                    "content": content,
                })

            tool_results, terminal_success, duplicate_detected = (
                self._execute_calls(calls)
            )

            result_summary_lines = []

            for name, tool_content, payload in tool_results:
                conversation.append({
                    "role": "tool",
                    "tool_name": name,
                    "content": tool_content,
                })

                result_summary_lines.append(
                    f"{name}: {tool_content}"
                )

            if terminal_success:
                return self._force_final_answer(
                    conversation,
                    "The requested file/module operation completed successfully.",
                )

            if duplicate_detected:
                return self._force_final_answer(
                    conversation,
                    "A repeated identical tool call was detected and blocked.",
                )

            if self._total_tool_calls >= self.MAX_TOTAL_TOOL_CALLS:
                return self._force_final_answer(
                    conversation,
                    "The total automatic tool-call safety budget was reached.",
                )

            conversation.append({
                "role": "system",
                "content": (
                    "Apollo executed the tool call(s) above for real.\n"
                    + "\n".join(result_summary_lines)
                    + "\n\nUse the returned result, not assumptions. "
                    "Do not repeat an identical tool call. "
                    "For ordinary coding projects prefer ONE "
                    "file_builder__write_files batch call. "
                    "For Apollo extension modules use module_factory only. "
                    "If the work is already complete, answer the user now instead "
                    "of calling another inspection/verification tool."
                ),
            })

            # Near the end of the budget, stop the loop gracefully instead of
            # throwing away completed work with the old hard failure message.
            if round_index >= self.MAX_TOOL_ROUNDS - 2:
                return self._force_final_answer(
                    conversation,
                    "Apollo reached the automatic tool-round budget and preserved "
                    "the work already completed.",
                )

        return self._force_final_answer(
            conversation,
            "Apollo reached the automatic tool-round budget.",
        )

    @Slot()
    def run(self):
        try:
            full = self._run_with_modules()

            if not self._cancelled:
                self.signals.finished.emit(full)

        except Exception as exc:
            if not self._cancelled:
                self.signals.failed.emit(str(exc))

        finally:
            self.signals.completed.emit()


class ModuleRepairSignals(QObject):
    progress = Signal(str)
    finished = Signal(dict)
    failed = Signal(str)
    completed = Signal()


class ModuleRepairTask(QRunnable):
    """
    Background auto-repair for an EXISTING pending module.

    All GUI updates are emitted as signals. The repair engine itself may edit only
    pending_modules/<module_id>/ and never installs the module.
    """

    def __init__(self, engine, module_id, max_attempts=6):
        super().__init__()
        self.engine = engine
        self.module_id = module_id
        self.max_attempts = max_attempts
        self.signals = ModuleRepairSignals()
        self.setAutoDelete(True)

    @Slot()
    def run(self):
        try:
            result = self.engine.repair_pending(
                self.module_id,
                max_attempts=self.max_attempts,
                progress_callback=self.signals.progress.emit,
            )
            self.signals.finished.emit(result)
        except Exception as exc:
            self.signals.failed.emit(
                f"{type(exc).__name__}: {exc}"
            )
        finally:
            self.signals.completed.emit()



class ModuleActionSignals(QObject):
    finished = Signal(dict)
    failed = Signal(str)
    completed = Signal()


class ModuleActionTask(QRunnable):
    """Run one Apollo module action without blocking the GUI thread."""

    def __init__(self, module_manager, module_id, action, arguments=None):
        super().__init__()
        self.module_manager = module_manager
        self.module_id = module_id
        self.action = action
        self.arguments = arguments or {}
        self.signals = ModuleActionSignals()
        self.setAutoDelete(True)

    @Slot()
    def run(self):
        try:
            result = self.module_manager.execute(
                self.module_id,
                self.action,
                self.arguments,
            )
            if not isinstance(result, dict):
                result = {"result": result}
            self.signals.finished.emit(result)
        except Exception as exc:
            self.signals.failed.emit(
                f"{type(exc).__name__}: {exc}"
            )
        finally:
            self.signals.completed.emit()
