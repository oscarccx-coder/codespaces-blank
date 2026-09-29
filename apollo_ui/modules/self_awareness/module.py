from pathlib import Path


ALLOWED_EXTENSIONS = {
    ".py", ".json", ".md", ".txt", ".bat", ".toml", ".yaml", ".yml"
}

DENIED_NAMES = {
    ".env", "apollo_memory.db", "modules_state.json"
}

SKIP_DIRS = {
    "__pycache__", ".git", ".venv", "venv", "workspace"
}


class Module:
    def __init__(self, context=None):
        context = context or {}
        self.base_dir = Path(context.get("base_dir", ".")).resolve()

    def tools(self):
        return [
            {
                "name": "describe_project",
                "description": (
                    "Inspect Apollo's own project structure, including source files "
                    "and installed module folders. Read-only."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {}
                }
            },
            {
                "name": "list_source_files",
                "description": (
                    "List Apollo source/config files. Use this before reading a file "
                    "when you need to understand Apollo's own implementation."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "subdir": {
                            "type": "string",
                            "description": "Optional relative directory inside Apollo."
                        }
                    }
                }
            },
            {
                "name": "read_source_file",
                "description": (
                    "Read a text source/config file from Apollo's own project. "
                    "This tool is deliberately read-only."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "path": {
                            "type": "string",
                            "description": "Relative path inside the Apollo project."
                        },
                        "max_chars": {
                            "type": "integer",
                            "description": "Maximum characters to return."
                        }
                    },
                    "required": ["path"]
                }
            },
            {
                "name": "search_source",
                "description": (
                    "Search Apollo's source code for a word or phrase and return "
                    "matching file names and line numbers."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "query": {"type": "string"},
                        "max_matches": {"type": "integer"}
                    },
                    "required": ["query"]
                }
            }
        ]

    def _safe_path(self, relative):
        relative = str(relative or "").strip().replace("\\", "/")
        target = (self.base_dir / relative).resolve()

        if target != self.base_dir and self.base_dir not in target.parents:
            raise PermissionError("Path escapes the Apollo project.")

        if target.name in DENIED_NAMES:
            raise PermissionError("That file is intentionally not exposed.")

        if any(part in SKIP_DIRS for part in target.parts):
            raise PermissionError("That directory is intentionally not exposed.")

        if target.is_file() and target.suffix.lower() not in ALLOWED_EXTENSIONS:
            raise PermissionError("Only source/config text files may be read.")

        return target

    def _iter_files(self, root):
        count = 0
        for p in sorted(root.rglob("*")):
            if count >= 400:
                break
            if not p.is_file():
                continue
            if any(part in SKIP_DIRS for part in p.parts):
                continue
            if p.name in DENIED_NAMES:
                continue
            if p.suffix.lower() not in ALLOWED_EXTENSIONS:
                continue
            count += 1
            yield p

    def self_test(self):
        assert self.base_dir.exists()
        assert self._safe_path("main.py").name == "main.py"
        return "Read-only project path validation passed."

    def run(self, action, arguments):
        arguments = arguments or {}

        if action == "describe_project":
            top = []
            for p in sorted(self.base_dir.iterdir()):
                if p.name in {"__pycache__", ".git", "workspace"}:
                    continue
                top.append({
                    "name": p.name,
                    "type": "directory" if p.is_dir() else "file"
                })

            modules_dir = self.base_dir / "modules"
            modules = []
            if modules_dir.exists():
                modules = [
                    p.name for p in sorted(modules_dir.iterdir())
                    if p.is_dir() and not p.name.startswith("_")
                ]

            return {
                "project_root": str(self.base_dir),
                "top_level": top,
                "installed_module_folders": modules,
                "note": "Self-awareness access is read-only."
            }

        if action == "list_source_files":
            subdir = arguments.get("subdir", "")
            root = self._safe_path(subdir)
            if not root.exists():
                raise FileNotFoundError(subdir)
            if root.is_file():
                return [str(root.relative_to(self.base_dir))]
            return [
                str(p.relative_to(self.base_dir)).replace("\\", "/")
                for p in self._iter_files(root)
            ]

        if action == "read_source_file":
            rel = arguments.get("path", "")
            target = self._safe_path(rel)
            if not target.exists() or not target.is_file():
                raise FileNotFoundError(rel)

            max_chars = int(arguments.get("max_chars", 50000))
            max_chars = max(1000, min(max_chars, 120000))
            text = target.read_text(encoding="utf-8", errors="replace")

            return {
                "path": str(target.relative_to(self.base_dir)).replace("\\", "/"),
                "content": text[:max_chars],
                "truncated": len(text) > max_chars,
                "characters": len(text),
            }

        if action == "search_source":
            query = str(arguments.get("query", "")).strip()
            if not query:
                raise ValueError("query is required.")

            max_matches = max(1, min(int(arguments.get("max_matches", 40)), 100))
            q = query.lower()
            matches = []

            for p in self._iter_files(self.base_dir):
                rel = str(p.relative_to(self.base_dir)).replace("\\", "/")
                try:
                    lines = p.read_text(
                        encoding="utf-8", errors="replace"
                    ).splitlines()
                except Exception:
                    continue

                for number, line in enumerate(lines, 1):
                    if q in line.lower():
                        matches.append({
                            "file": rel,
                            "line": number,
                            "text": line[:300]
                        })
                        if len(matches) >= max_matches:
                            return matches

            return matches

        raise KeyError(action)
