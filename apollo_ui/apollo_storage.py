from pathlib import Path
from datetime import datetime
import hashlib
import json
import shutil


class StorageLayout:
    """Canonical Apollo persistent-data layout plus safe legacy migration."""

    DIRECTORY_MAP = {
        "shell": "state/shell",
        "roadmap": "state/roadmap",
        "pile_cache": "cache/pile",
        "dictation_temp": "cache/dictation_temp",
        "file_trash": "trash/files",
        "screenshots": "media/screenshots",
        "voice_imprint": "media/voice_imprint",
        "voice_models": "models/voice",
        "tts_audio": "media/tts/audio",
        "voice_dataset": "training/voice_dataset",
        "venvs": "environments/venvs",
        "benchmarks": "reports/benchmarks",
        "training_module": "training/research",
        "module_upgrade_backups": "backups/module_upgrades",
        "recovery": "backups/recovery",
    }

    FILE_MAP = {
        "apollo_runtime.db": "databases/apollo_runtime.db",
        "chat_memory_module.db": "databases/chat_memory_module.db",
        "memory_bank.db": "databases/memory_bank.db",
        "knowledge_graph.db": "databases/knowledge_graph.db",
        "task_engine.db": "databases/task_engine.db",
        "to_do_list.db": "databases/to_do_list.db",
        "compiled_knowledge.db": "databases/compiled_knowledge.db",
        "active_project.json": "state/active_project.json",
        "model_roles.json": "state/model_roles.json",
        "neural_learning_state.json": "state/neural_learning_state.json",
        "upgrade_history.jsonl": "state/upgrade_history.jsonl",
        "voice_agent.json": "state/voice_agent.json",
        "automations.json": "state/automations.json",
        "speech_voice_profile.json": "state/speech_voice_profile.json",
        "apollo_running.flag": "state/apollo_running.flag",
    }

    ROOT_FILE_MAP = {
        "apollo_memory.db": "databases/apollo_memory.db",
        "ui_state.json": "state/ui_state.json",
        "modules_state.json": "state/modules_state.json",
        "apollo_error.log": "logs/apollo_error.log",
    }

    CATEGORY_DIRS = (
        "databases", "state", "cache", "media", "models", "training",
        "environments", "reports", "backups", "trash", "updates", "logs",
        "legacy_conflicts",
    )

    def __init__(self, base_dir):
        self.base_dir = Path(base_dir).resolve()
        self.root = self.base_dir / "storage"
        self.databases = self.root / "databases"
        self.state = self.root / "state"
        self.cache = self.root / "cache"
        self.media = self.root / "media"
        self.models = self.root / "models"
        self.training = self.root / "training"
        self.environments = self.root / "environments"
        self.reports = self.root / "reports"
        self.backups = self.root / "backups"
        self.trash = self.root / "trash"
        self.updates = self.root / "updates"
        self.logs = self.root / "logs"
        self.legacy_conflicts = self.root / "legacy_conflicts"

    @staticmethod
    def _same_file(a, b):
        try:
            return hashlib.sha256(Path(a).read_bytes()).digest() == hashlib.sha256(Path(b).read_bytes()).digest()
        except Exception:
            return False

    def _conflict_target(self, relative):
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        relative = Path(relative)
        target = self.legacy_conflicts / stamp / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        index = 1
        original = target
        while target.exists():
            target = original.with_name(f"{original.stem}-{index}{original.suffix}")
            index += 1
        return target

    def _merge_directory(self, source, target, report):
        source = Path(source)
        target = Path(target)
        target.mkdir(parents=True, exist_ok=True)
        for child in list(source.iterdir()):
            destination = target / child.name
            if child.is_dir():
                self._merge_directory(child, destination, report)
                try:
                    child.rmdir()
                except OSError:
                    pass
                continue
            if not destination.exists():
                destination.parent.mkdir(parents=True, exist_ok=True)
                shutil.move(str(child), str(destination))
                report.append({"source": str(child), "target": str(destination), "status": "moved"})
            elif self._same_file(child, destination):
                child.unlink()
                report.append({"source": str(child), "target": str(destination), "status": "duplicate_removed"})
            else:
                conflict = self._conflict_target(child.relative_to(self.root))
                shutil.move(str(child), str(conflict))
                report.append({"source": str(child), "target": str(conflict), "status": "conflict_preserved"})
        try:
            source.rmdir()
        except OSError:
            pass

    def _migrate_file(self, source, target, report):
        source = Path(source)
        target = Path(target)
        if not source.exists():
            return
        target.parent.mkdir(parents=True, exist_ok=True)
        if not target.exists():
            shutil.move(str(source), str(target))
            report.append({"source": str(source), "target": str(target), "status": "moved"})
        elif self._same_file(source, target):
            source.unlink()
            report.append({"source": str(source), "target": str(target), "status": "duplicate_removed"})
        else:
            relative = source.relative_to(self.base_dir) if self.base_dir in source.parents else Path(source.name)
            conflict = self._conflict_target(relative)
            shutil.move(str(source), str(conflict))
            report.append({"source": str(source), "target": str(conflict), "status": "conflict_preserved"})

    def ensure_layout(self):
        self.root.mkdir(parents=True, exist_ok=True)
        for name in self.CATEGORY_DIRS:
            (self.root / name).mkdir(parents=True, exist_ok=True)

        report = []
        for old_name, new_rel in self.ROOT_FILE_MAP.items():
            self._migrate_file(self.base_dir / old_name, self.root / new_rel, report)

        for old_name, new_rel in self.FILE_MAP.items():
            self._migrate_file(self.root / old_name, self.root / new_rel, report)

        for old_name, new_rel in self.DIRECTORY_MAP.items():
            source = self.root / old_name
            target = self.root / new_rel
            if source.exists() and source.is_dir() and source.resolve() != target.resolve():
                self._merge_directory(source, target, report)

        layout_note = self.root / "README.txt"
        if not layout_note.exists():
            layout_note.write_text(
                "Apollo persistent storage\n\n"
                "databases/    SQLite knowledge, memory and runtime databases\n"
                "state/        Small persistent JSON/state files and Hub layout\n"
                "cache/        Rebuildable caches and temporary working data\n"
                "media/        Screenshots, generated audio and voice profiles\n"
                "models/       Local model assets managed by Apollo\n"
                "training/     Training datasets and research material\n"
                "environments/ Isolated Python environments\n"
                "reports/      Benchmarks and generated reports\n"
                "backups/      Recovery and update/module backups\n"
                "trash/        Recoverable deleted files\n"
                "updates/      Update client/server state, staged releases and logs\n"
                "logs/         Runtime/error logs\n"
                "legacy_conflicts/ Preserved conflicts found during migration\n",
                encoding="utf-8",
            )

        return {"ok": True, "migrated": len(report), "report": report}

    def database(self, name):
        return self.databases / str(name)

    def state_file(self, name):
        return self.state / str(name)

    def summary(self):
        result = {}
        for name in self.CATEGORY_DIRS:
            path = self.root / name
            files = [p for p in path.rglob("*") if p.is_file()] if path.exists() else []
            result[name] = {
                "files": len(files),
                "bytes": sum(p.stat().st_size for p in files if p.exists()),
            }
        return result
