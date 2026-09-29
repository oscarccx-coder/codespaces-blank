from pathlib import Path
import hashlib
import shutil
from datetime import datetime


class PatchDocs:
    """Own Apollo patch-note paths and migrate old root-level patch documents."""

    def __init__(self, base_dir):
        self.base_dir = Path(base_dir).resolve()
        self.docs_dir = self.base_dir / "docs"
        self.patch_dir = self.docs_dir / "patch_notes"
        self.legacy_dir = self.patch_dir / "legacy_root_files"
        self.patch_notes_path = self.patch_dir / "PATCH_NOTES.md"

    @staticmethod
    def _same_file_bytes(a, b):
        try:
            return (
                hashlib.sha256(Path(a).read_bytes()).digest()
                == hashlib.sha256(Path(b).read_bytes()).digest()
            )
        except Exception:
            return False

    def _safe_legacy_target(self, source):
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        source = Path(source)
        candidate = self.legacy_dir / f"{source.stem}.root-{stamp}{source.suffix}"
        index = 1
        while candidate.exists():
            candidate = self.legacy_dir / (
                f"{source.stem}.root-{stamp}-{index}{source.suffix}"
            )
            index += 1
        return candidate

    def _migrate_one(self, source, target):
        source = Path(source)
        target = Path(target)
        if not source.exists():
            return {"source": str(source), "moved": False, "reason": "missing"}

        try:
            target.parent.mkdir(parents=True, exist_ok=True)
            self.legacy_dir.mkdir(parents=True, exist_ok=True)

            if not target.exists():
                shutil.move(str(source), str(target))
                return {
                    "source": str(source),
                    "target": str(target),
                    "moved": True,
                    "reason": "migrated",
                }

            if self._same_file_bytes(source, target):
                source.unlink()
                return {
                    "source": str(source),
                    "target": str(target),
                    "moved": True,
                    "reason": "duplicate_removed",
                }

            legacy = self._safe_legacy_target(source)
            shutil.move(str(source), str(legacy))
            return {
                "source": str(source),
                "target": str(legacy),
                "moved": True,
                "reason": "preserved_legacy_copy",
            }

        except Exception as exc:
            return {
                "source": str(source),
                "moved": False,
                "reason": f"{type(exc).__name__}: {exc}",
            }

    def ensure_layout(self):
        """Create docs layout and migrate legacy root patch files safely."""
        report = []
        try:
            self.patch_dir.mkdir(parents=True, exist_ok=True)
            self.legacy_dir.mkdir(parents=True, exist_ok=True)
        except Exception as exc:
            return {
                "ok": False,
                "error": f"{type(exc).__name__}: {exc}",
                "report": report,
            }

        report.append(
            self._migrate_one(
                self.base_dir / "PATCH_NOTES.md",
                self.patch_notes_path,
            )
        )

        for source in sorted(self.base_dir.glob("PATCH_README*.txt")):
            report.append(
                self._migrate_one(
                    source,
                    self.patch_dir / source.name,
                )
            )

        return {
            "ok": True,
            "patch_notes": str(self.patch_notes_path),
            "report": report,
        }
