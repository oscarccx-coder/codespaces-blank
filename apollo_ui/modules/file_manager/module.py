import json
import os
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path


TEXT_EXTENSIONS = {
    ".py", ".pyw", ".txt", ".md", ".json", ".jsonl", ".yaml", ".yml",
    ".toml", ".ini", ".cfg", ".csv", ".html", ".css", ".js", ".ts",
    ".bat", ".ps1", ".vbs", ".xml", ".sql", ".log",
}


class Module:
    PROTECTED = {
        "main.py", "workers.py", "module_manager.py", "module_validator.py",
        "module_repair_engine.py", "apollo_runtime.py", "ollama_client.py",
        "memory.py", "launch_apollo.pyw", "apollo_storage.py", "apollo_update.py", "apollo_updater.py", "apollo_release.py", "apollo_health_check.py", "config.json",
        "requirements.txt", "version_info.txt",
    }

    def __init__(self, context=None):
        context = context or {}
        self.base = Path(context.get("base_dir", ".")).resolve()
        self.runtime = context.get("runtime")
        self.trash = self.base / "storage" / "trash" / "files"
        self.trash.mkdir(parents=True, exist_ok=True)
        self.roots = {
            "apollo": self.base,
            "workspace": self.base / "workspace",
            "storage": self.base / "storage",
            "modules": self.base / "modules",
            "pending_modules": self.base / "pending_modules",
        }
        for path in self.roots.values():
            path.mkdir(parents=True, exist_ok=True)

    def tools(self):
        return [
            {
                "name": "list_roots",
                "description": "List Apollo file-manager roots and real OS paths.",
                "parameters": {"type": "object", "properties": {}},
            },
            {
                "name": "list_directory",
                "description": "List a real directory directly from disk.",
                "parameters": {
                    "type": "object",
                    "properties": {"root": {"type": "string"}, "path": {"type": "string"}},
                },
            },
            {
                "name": "read_text",
                "description": "Read a text/code file.",
                "parameters": {
                    "type": "object",
                    "properties": {"root": {"type": "string"}, "path": {"type": "string"}},
                    "required": ["root", "path"],
                },
            },
            {
                "name": "write_text",
                "description": "Write a text file; Apollo root is protected.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "root": {"type": "string"},
                        "path": {"type": "string"},
                        "content": {"type": "string"},
                    },
                    "required": ["root", "path", "content"],
                },
            },
            {
                "name": "move_item",
                "description": "Move a real file/folder between Apollo roots; Windows changes immediately.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "source_root": {"type": "string"},
                        "source_path": {"type": "string"},
                        "destination_root": {"type": "string"},
                        "destination_path": {"type": "string"},
                    },
                    "required": ["source_root", "source_path", "destination_root", "destination_path"],
                },
            },
            {
                "name": "copy_item",
                "description": "Copy a real file/folder between Apollo roots without changing the source.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "source_root": {"type": "string"},
                        "source_path": {"type": "string"},
                        "destination_root": {"type": "string"},
                        "destination_path": {"type": "string"},
                    },
                    "required": ["source_root", "source_path", "destination_root", "destination_path"],
                },
            },
            {
                "name": "import_external",
                "description": "Copy explicitly supplied Windows/OS files or folders into an Apollo-managed location.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "source_paths": {"type": "array", "items": {"type": "string"}},
                        "destination_root": {"type": "string"},
                        "destination_path": {"type": "string"},
                        "conflict_policy": {"type": "string", "enum": ["rename", "skip", "error"]},
                    },
                    "required": ["source_paths", "destination_root"],
                },
            },
            {
                "name": "rename_item",
                "description": "Rename a real file/folder in place.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "root": {"type": "string"}, "path": {"type": "string"}, "new_name": {"type": "string"}
                    },
                    "required": ["root", "path", "new_name"],
                },
            },
            {
                "name": "create_folder",
                "description": "Create a real folder.",
                "parameters": {
                    "type": "object",
                    "properties": {"root": {"type": "string"}, "path": {"type": "string"}},
                    "required": ["root", "path"],
                },
            },
            {
                "name": "trash_item",
                "description": "Move a real item into recoverable Apollo trash.",
                "parameters": {
                    "type": "object",
                    "properties": {"root": {"type": "string"}, "path": {"type": "string"}},
                    "required": ["root", "path"],
                },
            },
            {
                "name": "list_trash",
                "description": "List recoverable Apollo trash.",
                "parameters": {"type": "object", "properties": {}},
            },
            {
                "name": "restore_trash",
                "description": "Restore a trash entry to its original path.",
                "parameters": {
                    "type": "object",
                    "properties": {"trash_id": {"type": "string"}},
                    "required": ["trash_id"],
                },
            },
            {
                "name": "find_files",
                "description": "Find files by partial name across Apollo roots.",
                "parameters": {
                    "type": "object",
                    "properties": {"query": {"type": "string"}, "root": {"type": "string"}},
                    "required": ["query"],
                },
            },
            {
                "name": "scan_misplaced",
                "description": "Detect likely misplaced projects/modules/code without moving anything.",
                "parameters": {"type": "object", "properties": {}},
            },
            {
                "name": "reveal_in_explorer",
                "description": "Reveal a real Apollo file/folder in Windows Explorer.",
                "parameters": {
                    "type": "object",
                    "properties": {"root": {"type": "string"}, "path": {"type": "string"}},
                    "required": ["root", "path"],
                },
            },
        ]

    def _root(self, name):
        name = str(name or "workspace").lower().strip()
        if name not in self.roots:
            raise KeyError("Unknown file root: " + name)
        return self.roots[name].resolve()

    def _resolve(self, root, relative=""):
        base = self._root(root)
        relative = str(relative or "").replace("\\", "/").strip("/")
        path = (base / relative).resolve()
        if path != base and base not in path.parents:
            raise PermissionError("Path escaped selected root")
        return path

    def _rel(self, path):
        try:
            return str(Path(path).resolve().relative_to(self.base)).replace("\\", "/")
        except Exception:
            return str(path)

    def _protected(self, path):
        path = Path(path).resolve()
        return (
            path.parent == self.base
            and path.name.lower() in {x.lower() for x in self.PROTECTED}
        )

    def _mutable(self, path):
        path = Path(path).resolve()
        if path == self.base or self._protected(path):
            raise PermissionError(
                "Protected Apollo core path; use Self-Improvement proposal/approval path"
            )

    def _publish(self, topic, payload):
        if self.runtime:
            try:
                self.runtime.publish(topic, "file_manager", payload)
            except Exception:
                pass

    def _idx(self):
        return self.trash / "index.json"

    def _load_idx(self):
        try:
            value = json.loads(self._idx().read_text(encoding="utf-8"))
            return value if isinstance(value, list) else []
        except Exception:
            return []

    def _save_idx(self, rows):
        temp = self._idx().with_suffix(".tmp")
        temp.write_text(json.dumps(rows, indent=2), encoding="utf-8")
        temp.replace(self._idx())

    @staticmethod
    def _joined(relative_folder, name):
        folder = str(relative_folder or "").replace("\\", "/").strip("/")
        name = str(name).replace("\\", "/").strip("/")
        return "/".join(x for x in [folder, name] if x)

    @staticmethod
    def _conflict_free(path):
        if not path.exists():
            return path
        stem = path.stem if path.is_file() or path.suffix else path.name
        suffix = path.suffix if path.is_file() or path.suffix else ""
        parent = path.parent
        counter = 2
        while True:
            candidate = parent / f"{stem}_copy_{counter}{suffix}"
            if not candidate.exists():
                return candidate
            counter += 1

    def run(self, action, arguments):
        x = arguments or {}

        if action == "list_roots":
            return {
                "roots": [
                    {"name": name, "path": str(path.resolve())}
                    for name, path in self.roots.items()
                ]
            }

        if action == "list_directory":
            root = str(x.get("root", "workspace"))
            path = self._resolve(root, x.get("path", ""))
            if not path.is_dir():
                raise NotADirectoryError(str(path))
            items = []
            for item in sorted(path.iterdir(), key=lambda z: (not z.is_dir(), z.name.lower())):
                try:
                    stat = item.stat()
                    size = stat.st_size if item.is_file() else None
                    modified = datetime.fromtimestamp(stat.st_mtime).isoformat(timespec="seconds")
                except Exception:
                    size = None
                    modified = ""
                items.append({
                    "name": item.name,
                    "is_dir": item.is_dir(),
                    "size": size,
                    "modified": modified,
                    "relative_path": str(item.relative_to(self._root(root))).replace("\\", "/"),
                    "os_path": str(item),
                })
                if len(items) >= 3000:
                    break
            return {
                "root": root,
                "path": "" if path == self._root(root) else str(path.relative_to(self._root(root))).replace("\\", "/"),
                "os_path": str(path),
                "items": items,
            }

        if action == "read_text":
            path = self._resolve(x["root"], x["path"])
            if not path.is_file():
                raise FileNotFoundError(str(path))
            if path.suffix.lower() not in TEXT_EXTENSIONS and path.stat().st_size > 500000:
                raise ValueError("Large/binary file not opened as text")
            text = path.read_text(encoding="utf-8", errors="replace")
            return {
                "path": self._rel(path),
                "content": text[:500000],
                "truncated": len(text) > 500000,
            }

        if action == "write_text":
            root = str(x["root"]).lower()
            path = self._resolve(root, x["path"])
            self._mutable(path)
            if root == "apollo":
                raise PermissionError("Direct Apollo-root editing is disabled")
            content = str(x.get("content", ""))
            if len(content.encode("utf-8")) > 3000000:
                raise ValueError("Text file exceeds 3 MB")
            path.parent.mkdir(parents=True, exist_ok=True)
            temp = path.with_suffix(path.suffix + ".apollo_tmp")
            temp.write_text(content, encoding="utf-8")
            temp.replace(path)
            self._publish("file.written", {"path": self._rel(path)})
            return {"written": True, "path": self._rel(path), "os_path": str(path)}

        if action == "move_item":
            source = self._resolve(x["source_root"], x["source_path"])
            destination = self._resolve(x["destination_root"], x["destination_path"])
            self._mutable(source)
            if not source.exists():
                raise FileNotFoundError(str(source))
            if destination.exists():
                raise FileExistsError(str(destination))
            if source == destination:
                return {"moved": False, "reason": "same_path", "path": self._rel(source)}
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(source), str(destination))
            self._publish("file.moved", {"from": self._rel(source), "to": self._rel(destination)})
            return {"moved": True, "from": self._rel(source), "to": self._rel(destination), "os_path": str(destination)}

        if action == "copy_item":
            source = self._resolve(x["source_root"], x["source_path"])
            destination = self._resolve(x["destination_root"], x["destination_path"])
            if not source.exists():
                raise FileNotFoundError(str(source))
            if destination.exists():
                raise FileExistsError(str(destination))
            destination.parent.mkdir(parents=True, exist_ok=True)
            if source.is_dir():
                shutil.copytree(source, destination)
            else:
                shutil.copy2(source, destination)
            self._publish("file.copied", {"from": self._rel(source), "to": self._rel(destination)})
            return {"copied": True, "from": self._rel(source), "to": self._rel(destination), "os_path": str(destination)}

        if action == "import_external":
            source_paths = [Path(str(p)).expanduser().resolve() for p in (x.get("source_paths") or [])]
            if not source_paths:
                raise ValueError("source_paths is required")
            destination_root = str(x["destination_root"])
            destination_folder = self._resolve(destination_root, x.get("destination_path", ""))
            destination_folder.mkdir(parents=True, exist_ok=True)
            if not destination_folder.is_dir():
                raise NotADirectoryError(str(destination_folder))
            policy = str(x.get("conflict_policy", "rename")).lower()
            if policy not in {"rename", "skip", "error"}:
                raise ValueError("conflict_policy must be rename, skip or error")
            imported = []
            skipped = []
            for source in source_paths:
                if not source.exists():
                    skipped.append({"source": str(source), "reason": "not_found"})
                    continue
                target = destination_folder / source.name
                if target.exists():
                    if policy == "skip":
                        skipped.append({"source": str(source), "reason": "exists"})
                        continue
                    if policy == "error":
                        raise FileExistsError(str(target))
                    target = self._conflict_free(target)
                if source.is_dir():
                    shutil.copytree(source, target)
                else:
                    shutil.copy2(source, target)
                imported.append({"source": str(source), "destination": str(target)})
            self._publish("file.external_import", {"count": len(imported), "destination": str(destination_folder)})
            return {"imported": imported, "skipped": skipped, "count": len(imported)}

        if action == "rename_item":
            path = self._resolve(x["root"], x["path"])
            self._mutable(path)
            new_name = Path(str(x["new_name"]).strip()).name
            if not new_name or new_name in {".", ".."}:
                raise ValueError("Invalid new name")
            destination = path.with_name(new_name)
            if destination.exists():
                raise FileExistsError(str(destination))
            path.rename(destination)
            self._publish("file.renamed", {"from": self._rel(path), "to": self._rel(destination)})
            return {"renamed": True, "path": self._rel(destination), "os_path": str(destination)}

        if action == "create_folder":
            path = self._resolve(x["root"], x["path"])
            self._mutable(path)
            path.mkdir(parents=True, exist_ok=True)
            self._publish("folder.created", {"path": self._rel(path)})
            return {"created": True, "path": self._rel(path), "os_path": str(path)}

        if action == "trash_item":
            path = self._resolve(x["root"], x["path"])
            self._mutable(path)
            if not path.exists():
                raise FileNotFoundError(str(path))
            trash_id = datetime.now().strftime("%Y%m%d_%H%M%S_%f") + "_" + path.name
            destination = self.trash / trash_id
            original = self._rel(path)
            shutil.move(str(path), str(destination))
            rows = self._load_idx()
            rows.append({
                "trash_id": trash_id,
                "original": original,
                "trashed_at": datetime.now().isoformat(timespec="seconds"),
            })
            self._save_idx(rows)
            self._publish("file.trashed", {"original": original, "trash_id": trash_id})
            return {"trashed": True, "trash_id": trash_id, "original": original}

        if action == "list_trash":
            return {"trash": list(reversed(self._load_idx()))}

        if action == "restore_trash":
            trash_id = str(x["trash_id"])
            rows = self._load_idx()
            row = next((item for item in rows if item.get("trash_id") == trash_id), None)
            if not row:
                raise KeyError("Trash entry not found")
            source = self.trash / trash_id
            destination = (self.base / row["original"]).resolve()
            if destination.exists():
                raise FileExistsError(str(destination))
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(source), str(destination))
            self._save_idx([item for item in rows if item.get("trash_id") != trash_id])
            return {"restored": True, "path": self._rel(destination), "os_path": str(destination)}

        if action == "find_files":
            query = str(x["query"]).lower()
            root_names = [str(x["root"]).lower()] if x.get("root") else list(self.roots)
            hits = []
            seen = set()
            for root_name in root_names:
                base = self._root(root_name)
                for path in base.rglob("*"):
                    if len(hits) >= 300:
                        break
                    resolved = str(path.resolve())
                    if not path.is_file() or resolved in seen:
                        continue
                    seen.add(resolved)
                    if query in path.name.lower():
                        hits.append({
                            "root": root_name,
                            "path": str(path.relative_to(base)).replace("\\", "/"),
                            "os_path": str(path),
                        })
            return {"hits": hits}

        if action == "scan_misplaced":
            suggestions = []
            workspace = self.roots["workspace"]
            storage = self.roots["storage"]
            ignored = {"databases", "state", "cache", "media", "models", "training", "environments", "reports", "backups", "trash", "updates", "logs", "legacy_conflicts"}
            for folder in workspace.iterdir():
                if folder.is_dir():
                    names = {p.name.lower() for p in folder.iterdir() if p.is_file()}
                    if {"manifest.json", "module.py"}.issubset(names):
                        suggestions.append({
                            "kind": "module_in_workspace",
                            "current": self._rel(folder),
                            "suggested_root": "pending_modules",
                            "suggested_path": folder.name,
                            "reason": "Looks like an Apollo module candidate",
                        })
            for path in storage.iterdir():
                if path.name.lower() in ignored:
                    continue
                if path.is_dir() and sum(1 for _ in path.rglob("*.py")) >= 2:
                    suggestions.append({
                        "kind": "project_in_storage",
                        "current": self._rel(path),
                        "suggested_root": "workspace",
                        "suggested_path": path.name,
                        "reason": "Multi-file code project found under storage",
                    })
                elif path.is_file() and path.suffix.lower() in {".py", ".pyw", ".html", ".js"}:
                    suggestions.append({
                        "kind": "code_file_in_storage",
                        "current": self._rel(path),
                        "suggested_root": "workspace",
                        "suggested_path": "Inbox/" + path.name,
                        "reason": "Authored code file found under storage",
                    })
            known = {x.lower() for x in self.PROTECTED}
            for path in self.base.iterdir():
                if path.is_file() and path.suffix.lower() in {".py", ".pyw"} and path.name.lower() not in known:
                    suggestions.append({
                        "kind": "loose_code_in_apollo_root",
                        "current": self._rel(path),
                        "suggested_root": "workspace",
                        "suggested_path": "Inbox/" + path.name,
                        "reason": "Loose non-core Python file in Apollo root",
                    })
            return {"suggestions": suggestions, "count": len(suggestions), "moved": False}

        if action == "reveal_in_explorer":
            path = self._resolve(x["root"], x["path"])
            if not path.exists():
                raise FileNotFoundError(str(path))
            if os.name == "nt":
                if path.is_file():
                    subprocess.Popen(["explorer.exe", "/select,", str(path)])
                else:
                    os.startfile(str(path))
            else:
                subprocess.Popen([
                    "open" if sys.platform == "darwin" else "xdg-open",
                    str(path if path.is_dir() else path.parent),
                ])
            return {"opened": True, "os_path": str(path)}

        raise KeyError(action)

    def self_test(self):
        assert self._resolve("workspace", "demo").parent == self.roots["workspace"]
        assert self._protected(self.base / "main.py")
        names = {tool["name"] for tool in self.tools()}
        assert "move_item" in names
        assert "copy_item" in names
        assert "import_external" in names
        return "OS-backed dual-pane File Manager contracts passed"

    def build_ui(self, parent=None, ui_context=None):
        from PySide6.QtCore import Qt, QMimeData, QUrl
        from PySide6.QtGui import QDrag
        from PySide6.QtWidgets import (
            QWidget, QVBoxLayout, QHBoxLayout, QComboBox, QLineEdit, QPushButton,
            QTreeWidget, QTreeWidgetItem, QTextEdit, QLabel, QMessageBox,
            QInputDialog, QSplitter, QAbstractItemView, QFrame,
        )

        MIME_TYPE = "application/x-apollo-file-items"
        page = QWidget(parent)
        outer = QVBoxLayout(page)

        title = QLabel("Apollo File Manager — dual live filesystem")
        title.setStyleSheet("font-size:22px;font-weight:800;")
        outer.addWidget(title)

        note = QLabel(
            "Both panes are independent real filesystem views. Drag Apollo files between panes to MOVE them. "
            "Drop files from Windows Explorer into either pane to COPY/import them. Drag from Apollo out to Explorer "
            "as a normal OS file drag. Core Apollo files remain protected."
        )
        note.setWordWrap(True)
        outer.addWidget(note)

        status = QLabel()
        status.setWordWrap(True)

        pane_state = {}
        shared_state = {"active": "left", "editing": None}

        class FileTree(QTreeWidget):
            def __init__(self, pane_id, parent=None):
                super().__init__(parent)
                self.pane_id = pane_id
                self.setHeaderLabels(["Name", "Type", "Size", "Modified"])
                self.setSelectionMode(QAbstractItemView.ExtendedSelection)
                self.setDragEnabled(True)
                self.setAcceptDrops(True)
                self.setDropIndicatorShown(True)
                self.setDragDropMode(QAbstractItemView.DragDrop)
                self.setDefaultDropAction(Qt.MoveAction)

            def startDrag(self, supported_actions):
                pane = pane_state[self.pane_id]
                selected = []
                urls = []
                for item in self.selectedItems():
                    data = item.data(0, Qt.UserRole)
                    if not isinstance(data, dict):
                        continue
                    selected.append({
                        "path": data["relative_path"],
                        "name": data["name"],
                        "is_dir": bool(data["is_dir"]),
                    })
                    if data.get("os_path"):
                        urls.append(QUrl.fromLocalFile(data["os_path"]))
                if not selected:
                    return
                payload = {
                    "source_pane": self.pane_id,
                    "root": pane["root"].currentText(),
                    "items": selected,
                }
                mime = QMimeData()
                mime.setData(MIME_TYPE, json.dumps(payload).encode("utf-8"))
                if urls:
                    mime.setUrls(urls)
                drag = QDrag(self)
                drag.setMimeData(mime)
                drag.exec(Qt.CopyAction | Qt.MoveAction, Qt.CopyAction)

            def dragEnterEvent(self, event):
                if event.mimeData().hasFormat(MIME_TYPE) or event.mimeData().hasUrls():
                    event.acceptProposedAction()
                else:
                    event.ignore()

            def dragMoveEvent(self, event):
                if event.mimeData().hasFormat(MIME_TYPE) or event.mimeData().hasUrls():
                    event.acceptProposedAction()
                else:
                    event.ignore()

            def dropEvent(self, event):
                item = self.itemAt(event.position().toPoint())
                handle_drop(self.pane_id, event, item)

        def pane_current_root(pane_id):
            return pane_state[pane_id]["root"].currentText()

        def pane_current_path(pane_id):
            return pane_state[pane_id]["path"].text().strip().replace("\\", "/").strip("/")

        def join_path(folder, name):
            folder = str(folder or "").replace("\\", "/").strip("/")
            name = str(name or "").replace("\\", "/").strip("/")
            return "/".join(x for x in [folder, name] if x)

        def selected_item(pane_id):
            item = pane_state[pane_id]["tree"].currentItem()
            return item.data(0, Qt.UserRole) if item else None

        def destination_folder(pane_id, target_item=None):
            folder = pane_current_path(pane_id)
            if target_item is not None:
                data = target_item.data(0, Qt.UserRole)
                if isinstance(data, dict) and data.get("is_dir"):
                    folder = data["relative_path"]
            return folder

        def reload_pane(pane_id, keep_selection_name=None):
            pane = pane_state[pane_id]
            tree = pane["tree"]
            tree.clear()
            try:
                data = self.run(
                    "list_directory",
                    {"root": pane_current_root(pane_id), "path": pane_current_path(pane_id)},
                )
                pane["path"].setText(data["path"])
                for entry in data["items"]:
                    row = QTreeWidgetItem([
                        entry["name"],
                        "Folder" if entry["is_dir"] else "File",
                        "" if entry["size"] is None else str(entry["size"]),
                        entry["modified"],
                    ])
                    row.setData(0, Qt.UserRole, entry)
                    tree.addTopLevelItem(row)
                    if keep_selection_name and entry["name"] == keep_selection_name:
                        row.setSelected(True)
                        tree.setCurrentItem(row)
                pane["where"].setText(data["os_path"])
            except Exception as exc:
                pane["where"].setText(str(exc))

        def reload_both():
            reload_pane("left")
            reload_pane("right")

        def set_active(pane_id):
            shared_state["active"] = pane_id
            pane_state["left"]["frame"].setProperty("activePane", pane_id == "left")
            pane_state["right"]["frame"].setProperty("activePane", pane_id == "right")
            for pid in ("left", "right"):
                frame = pane_state[pid]["frame"]
                frame.style().unpolish(frame)
                frame.style().polish(frame)

        def open_item(pane_id, item, _column=0):
            set_active(pane_id)
            data = item.data(0, Qt.UserRole)
            if not isinstance(data, dict):
                return
            if data["is_dir"]:
                pane_state[pane_id]["path"].setText(data["relative_path"])
                reload_pane(pane_id)
                return
            try:
                result = self.run(
                    "read_text",
                    {"root": pane_current_root(pane_id), "path": data["relative_path"]},
                )
                editor.setPlainText(result["content"])
                shared_state["editing"] = {
                    "pane": pane_id,
                    "root": pane_current_root(pane_id),
                    "path": data["relative_path"],
                }
                editor_title.setText("Editing: " + result["path"])
                status.setText("Opened " + result["path"])
            except Exception as exc:
                shared_state["editing"] = None
                editor.clear()
                editor_title.setText("Preview / text editor")
                status.setText(str(exc))

        def go_up(pane_id):
            current = Path(pane_current_path(pane_id))
            if str(current) in {"", "."}:
                parent = ""
            else:
                parent = str(current.parent).replace("\\", "/")
                if parent == ".":
                    parent = ""
            pane_state[pane_id]["path"].setText(parent)
            reload_pane(pane_id)

        def handle_drop(target_pane, event, target_item):
            set_active(target_pane)
            mime = event.mimeData()
            target_root = pane_current_root(target_pane)
            target_folder = destination_folder(target_pane, target_item)

            if mime.hasFormat(MIME_TYPE):
                try:
                    payload = json.loads(bytes(mime.data(MIME_TYPE)).decode("utf-8"))
                    source_pane = payload.get("source_pane")
                    source_root = str(payload["root"])
                    moved = 0
                    failures = []
                    for entry in payload.get("items", []):
                        source_path = str(entry["path"])
                        destination_path = join_path(target_folder, entry["name"])
                        if source_root == target_root and source_path == destination_path:
                            continue
                        try:
                            result = self.run(
                                "move_item",
                                {
                                    "source_root": source_root,
                                    "source_path": source_path,
                                    "destination_root": target_root,
                                    "destination_path": destination_path,
                                },
                            )
                            if result.get("moved"):
                                moved += 1
                        except Exception as exc:
                            failures.append(f"{entry.get('name')}: {exc}")
                    if source_pane in pane_state:
                        reload_pane(source_pane)
                    reload_pane(target_pane)
                    if failures:
                        QMessageBox.warning(
                            page,
                            "Apollo Files",
                            f"Moved {moved} item(s).\n\nCould not move:\n" + "\n".join(failures[:12]),
                        )
                    else:
                        status.setText(f"Moved {moved} item(s) on the real filesystem.")
                    event.setDropAction(Qt.MoveAction)
                    event.accept()
                    return
                except Exception as exc:
                    QMessageBox.warning(page, "Apollo Files", str(exc))
                    event.ignore()
                    return

            if mime.hasUrls():
                paths = [url.toLocalFile() for url in mime.urls() if url.isLocalFile()]
                if paths:
                    try:
                        result = self.run(
                            "import_external",
                            {
                                "source_paths": paths,
                                "destination_root": target_root,
                                "destination_path": target_folder,
                                "conflict_policy": "rename",
                            },
                        )
                        reload_pane(target_pane)
                        status.setText(
                            f"Imported {result.get('count', 0)} item(s) from the OS into "
                            f"{target_root}:{target_folder or '/'}"
                        )
                        event.setDropAction(Qt.CopyAction)
                        event.accept()
                        return
                    except Exception as exc:
                        QMessageBox.warning(page, "Apollo Files", str(exc))
            event.ignore()

        def create_pane(pane_id, initial_root):
            frame = QFrame()
            frame.setProperty("activePane", pane_id == "left")
            frame.setStyleSheet(
                "QFrame[activePane='true']{border:1px solid #35e1c6;border-radius:12px;background:#071b1c;}"
                "QFrame[activePane='false']{border:1px solid #135a53;border-radius:12px;background:#07191a;}"
            )
            layout = QVBoxLayout(frame)
            layout.setContentsMargins(10, 10, 10, 10)

            head = QHBoxLayout()
            root_box = QComboBox()
            root_box.addItems(list(self.roots))
            root_box.setCurrentText(initial_root)
            path_box = QLineEdit()
            path_box.setPlaceholderText("Relative folder path")
            up_button = QPushButton("↑")
            up_button.setToolTip("Up one folder")
            refresh_button = QPushButton("Refresh")
            head.addWidget(root_box)
            head.addWidget(path_box, 1)
            head.addWidget(up_button)
            head.addWidget(refresh_button)
            layout.addLayout(head)

            where = QLabel()
            where.setWordWrap(True)
            where.setStyleSheet("color:#6da59d;font-size:10px;")
            layout.addWidget(where)

            tree = FileTree(pane_id)
            layout.addWidget(tree, 1)

            pane_state[pane_id] = {
                "frame": frame,
                "root": root_box,
                "path": path_box,
                "tree": tree,
                "where": where,
            }

            root_box.currentTextChanged.connect(
                lambda _value, pid=pane_id: (path_box.setText(""), reload_pane(pid))
            )
            path_box.returnPressed.connect(lambda pid=pane_id: reload_pane(pid))
            up_button.clicked.connect(lambda _checked=False, pid=pane_id: go_up(pid))
            refresh_button.clicked.connect(lambda _checked=False, pid=pane_id: reload_pane(pid))
            tree.itemDoubleClicked.connect(lambda item, column, pid=pane_id: open_item(pid, item, column))
            tree.itemClicked.connect(lambda _item, _column, pid=pane_id: set_active(pid))
            tree.currentItemChanged.connect(lambda _current, _previous, pid=pane_id: set_active(pid))
            return frame

        # Two fully independent location panes.
        pane_splitter = QSplitter(Qt.Horizontal)
        left_frame = create_pane("left", "workspace")
        right_frame = create_pane("right", "pending_modules")
        pane_splitter.addWidget(left_frame)
        pane_splitter.addWidget(right_frame)
        pane_splitter.setSizes([650, 650])

        editor_host = QWidget()
        editor_layout = QVBoxLayout(editor_host)
        editor_layout.setContentsMargins(0, 0, 0, 0)
        editor_head = QHBoxLayout()
        editor_title = QLabel("Preview / text editor")
        editor_title.setStyleSheet("font-weight:700;color:#9ff7e5;")
        save_button = QPushButton("Save Text")
        editor_head.addWidget(editor_title, 1)
        editor_head.addWidget(save_button)
        editor_layout.addLayout(editor_head)
        editor = QTextEdit()
        editor_layout.addWidget(editor, 1)

        vertical = QSplitter(Qt.Vertical)
        vertical.addWidget(pane_splitter)
        vertical.addWidget(editor_host)
        vertical.setSizes([650, 260])
        outer.addWidget(vertical, 1)

        action_row = QHBoxLayout()
        move_left = QPushButton("← Move to Left")
        move_right = QPushButton("Move to Right →")
        copy_left = QPushButton("← Copy to Left")
        copy_right = QPushButton("Copy to Right →")
        new_folder = QPushButton("New Folder")
        rename = QPushButton("Rename")
        trash = QPushButton("Trash")
        reveal = QPushButton("Reveal in Explorer")
        scan = QPushButton("Scan Misplaced")
        for button in (
            move_left, move_right, copy_left, copy_right,
            new_folder, rename, trash, reveal, scan,
        ):
            action_row.addWidget(button)
        outer.addLayout(action_row)
        outer.addWidget(status)

        def transfer(source_pane, target_pane, copy=False):
            entries = []
            for item in pane_state[source_pane]["tree"].selectedItems():
                data = item.data(0, Qt.UserRole)
                if isinstance(data, dict):
                    entries.append(data)
            if not entries:
                status.setText("Select one or more files/folders first.")
                return
            target_folder = pane_current_path(target_pane)
            failures = []
            count = 0
            for entry in entries:
                try:
                    action = "copy_item" if copy else "move_item"
                    self.run(
                        action,
                        {
                            "source_root": pane_current_root(source_pane),
                            "source_path": entry["relative_path"],
                            "destination_root": pane_current_root(target_pane),
                            "destination_path": join_path(target_folder, entry["name"]),
                        },
                    )
                    count += 1
                except Exception as exc:
                    failures.append(f"{entry['name']}: {exc}")
            reload_pane(source_pane)
            reload_pane(target_pane)
            verb = "Copied" if copy else "Moved"
            status.setText(f"{verb} {count} item(s).")
            if failures:
                QMessageBox.warning(page, "Apollo Files", "\n".join(failures[:12]))

        def active_selected():
            pane_id = shared_state["active"]
            return pane_id, selected_item(pane_id)

        def do_new_folder():
            pane_id = shared_state["active"]
            name, ok = QInputDialog.getText(page, "New Folder", "Folder name:")
            if ok and name.strip():
                try:
                    self.run(
                        "create_folder",
                        {
                            "root": pane_current_root(pane_id),
                            "path": join_path(pane_current_path(pane_id), name.strip()),
                        },
                    )
                    reload_pane(pane_id, name.strip())
                except Exception as exc:
                    QMessageBox.warning(page, "Apollo Files", str(exc))

        def do_rename():
            pane_id, data = active_selected()
            if not data:
                return
            name, ok = QInputDialog.getText(page, "Rename", "New name:", text=data["name"])
            if ok and name.strip():
                try:
                    self.run(
                        "rename_item",
                        {"root": pane_current_root(pane_id), "path": data["relative_path"], "new_name": name.strip()},
                    )
                    reload_pane(pane_id, name.strip())
                except Exception as exc:
                    QMessageBox.warning(page, "Apollo Files", str(exc))

        def do_trash():
            pane_id = shared_state["active"]
            selected = []
            for item in pane_state[pane_id]["tree"].selectedItems():
                data = item.data(0, Qt.UserRole)
                if isinstance(data, dict):
                    selected.append(data)
            if not selected:
                return
            if QMessageBox.question(
                page,
                "Apollo Files",
                f"Move {len(selected)} selected item(s) to recoverable Apollo trash?",
            ) != QMessageBox.Yes:
                return
            failures = []
            for data in selected:
                try:
                    self.run("trash_item", {"root": pane_current_root(pane_id), "path": data["relative_path"]})
                except Exception as exc:
                    failures.append(f"{data['name']}: {exc}")
            reload_pane(pane_id)
            if failures:
                QMessageBox.warning(page, "Apollo Files", "\n".join(failures[:12]))

        def do_reveal():
            pane_id, data = active_selected()
            relative = data["relative_path"] if data else pane_current_path(pane_id)
            try:
                self.run("reveal_in_explorer", {"root": pane_current_root(pane_id), "path": relative})
            except Exception as exc:
                QMessageBox.warning(page, "Apollo Files", str(exc))

        def do_scan():
            try:
                result = self.run("scan_misplaced", {})
                editor.setPlainText(json.dumps(result, indent=2))
                shared_state["editing"] = None
                editor_title.setText("Misplaced-file scan")
                status.setText(f"{result['count']} suggestion(s); nothing moved automatically.")
            except Exception as exc:
                status.setText(str(exc))

        def save_editor():
            editing = shared_state.get("editing")
            if not editing:
                return
            try:
                self.run(
                    "write_text",
                    {"root": editing["root"], "path": editing["path"], "content": editor.toPlainText()},
                )
                reload_pane(editing["pane"])
                status.setText("Saved to disk: " + editing["path"])
            except Exception as exc:
                QMessageBox.warning(page, "Apollo Files", str(exc))

        move_left.clicked.connect(lambda: transfer("right", "left", copy=False))
        move_right.clicked.connect(lambda: transfer("left", "right", copy=False))
        copy_left.clicked.connect(lambda: transfer("right", "left", copy=True))
        copy_right.clicked.connect(lambda: transfer("left", "right", copy=True))
        new_folder.clicked.connect(do_new_folder)
        rename.clicked.connect(do_rename)
        trash.clicked.connect(do_trash)
        reveal.clicked.connect(do_reveal)
        scan.clicked.connect(do_scan)
        save_button.clicked.connect(save_editor)

        reload_both()
        set_active("left")
        status.setText(
            "Drag between panes to MOVE. Drop from Windows Explorer to COPY/import. "
            "Both panes can stay in different folders at the same time."
        )
        return page
