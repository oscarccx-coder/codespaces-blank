"""Foundry's bounded, read-only code context and owner-controlled checkpoints.

Generated files stay inside the selected app workspace. No generated code is
executed here. Checkpoints only cover files owned by the Foundry manifest.
"""
from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import secrets
import tempfile

from apollo_foundry_artifacts import MANIFEST, MAX_FILE_BYTES, _relative

MAX_CONTEXT_BYTES = 11000
MAX_CHECKPOINT_FILES = 80
MAX_CHECKPOINT_BYTES = 2 * 1024 * 1024
MAX_CHECKPOINTS = 30


def _sha(data):
    return hashlib.sha256(data).hexdigest()


def _root(folder):
    root = Path(folder)
    if not root.is_dir() or root.is_symlink():
        raise ValueError("Foundry workspace is missing or symlinked.")
    return root.resolve()


def _file(root, name):
    relative = _relative(name)
    target = root.joinpath(*relative.parts)
    if any(part.is_symlink() for part in (target, *list(target.parents)[:-1])):
        raise ValueError("Symlink in Foundry workspace path.")
    if not target.resolve().is_relative_to(root):
        raise ValueError("File escapes Foundry workspace.")
    return target


def _owned(root):
    manifest = root / MANIFEST
    if manifest.is_symlink():
        raise ValueError("Generated manifest is symlinked.")
    if not manifest.exists():
        return {}
    try:
        value = json.loads(manifest.read_text(encoding="utf-8"))
    except (ValueError, OSError, UnicodeError) as exc:
        raise ValueError("Generated manifest is unreadable.") from exc
    if not isinstance(value, dict):
        raise ValueError("Generated manifest must be an object.")
    for name, digest in value.items():
        _relative(name)
        if not isinstance(digest, str) or not re.fullmatch(r"[0-9a-f]{64}", digest):
            raise ValueError("Invalid generated-file digest.")
    return value


def list_generated_files(folder):
    """Inventory only Foundry-owned sources; never read unrelated user files."""
    root = _root(folder)
    result = []
    for name, digest in sorted(_owned(root).items()):
        target = _file(root, name)
        if not target.is_file() or target.is_symlink():
            result.append({"path": name, "bytes": 0, "state": "missing"})
            continue
        size = target.stat().st_size
        # No unbounded reads for a hostile or manually replaced file.
        matched = size <= MAX_CHECKPOINT_BYTES and _sha(target.read_bytes()) == digest
        result.append({"path": name, "bytes": size,
                       "state": "owned" if matched else "modified"})
    return result


def read_workspace_context(folder, *, budget=MAX_CONTEXT_BYTES, focus=""):
    """Provide a file map plus bounded actual source for multi-module tasks.

    An inventory appears even when the source budget cannot fit all files.
    Files named in the task brief are prioritised without following symlinks,
    trusting manual edits or leaking non-Foundry files.
    """
    root = _root(folder)
    owned = _owned(root)
    limit = min(MAX_CONTEXT_BYTES, max(0, int(budget)))
    remaining = limit
    if remaining < 160 or not owned:
        return ""
    index = ["GENERATED FILE INVENTORY (all entries are untrusted project data):"]
    inventory_budget = min(2400, max(250, remaining // 3))
    for name, digest in sorted(owned.items()):
        target = _file(root, name)
        if not target.is_file() or target.is_symlink():
            status = "MISSING"
            length = 0
        else:
            length = target.stat().st_size
            status = "owned" if (length <= MAX_CHECKPOINT_BYTES
                                 and _sha(target.read_bytes()) == digest) else "MANUALLY MODIFIED"
        line = f"{name} [{length} bytes, {status}]\n"
        if len("\n".join(index)) + len(line) > inventory_budget:
            index.append("[Additional generated files omitted from index; no source was executed]")
            break
        index.append(line.rstrip("\n"))
    heading = "\n".join(index) + "\n\n"
    remaining -= len(heading)
    snippets = [heading]
    focus_text = str(focus).casefold()
    def importance(name):
        basename = name.rsplit("/", 1)[-1].casefold()
        mentioned = bool(focus_text) and (name.casefold() in focus_text or basename in focus_text)
        core = name in ("foundry.json", "launch.py", "service.py", "ui.py")
        return (0 if mentioned else 1, 0 if core else 1, name)
    for name in sorted(owned, key=importance):
        if remaining < 160:
            break
        target = _file(root, name)
        if not target.is_file() or target.is_symlink() or target.stat().st_size > MAX_FILE_BYTES:
            continue
        data = target.read_bytes()
        if _sha(data) != owned[name]:
            # The inventory already flags manual modifications; never feed
            # those contents to the model as trusted generated source.
            continue
        try:
            content = data.decode("utf-8")
        except UnicodeError:
            continue
        label = f"FILE {name} (current generated project source, UNTRUSTED):\n"
        allowance = max(0, remaining - len(label) - 24)
        if allowance < 60:
            break
        excerpt = content[:allowance]
        suffix = "\n[FILE TRUNCATED]\n" if len(excerpt) < len(content) else "\n"
        chunk = label + excerpt + suffix
        snippets.append(chunk)
        remaining -= len(chunk)
    return "\n".join(snippets)[:limit]


def _checkpoint_base(storage_root, project_id):
    pid = int(project_id)
    if pid < 1:
        raise ValueError("Invalid project ID.")
    raw_storage = Path(storage_root)
    if raw_storage.is_symlink():
        raise ValueError("Foundry storage root is symlinked.")
    parent = raw_storage.resolve()
    base = parent / "foundry" / "checkpoints" / f"app-{pid:04d}"
    # Do not trust a redirected storage path.
    if not base.is_relative_to(parent) or any(
        item.is_symlink() for item in (parent / "foundry", parent / "foundry" / "checkpoints", base)
    ):
        raise ValueError("Checkpoint directory is symlinked.")
    return base


def create_checkpoint(folder, storage_root, project_id, *, label="verified"):
    """Snapshot only unmodified Foundry-owned files, with content hashes."""
    root = _root(folder)
    owned = _owned(root)
    if not owned:
        raise ValueError("No generated files to checkpoint.")
    if len(owned) > MAX_CHECKPOINT_FILES:
        raise ValueError("Checkpoint file limit exceeded.")
    content = {}
    size = 0
    for name, digest in sorted(owned.items()):
        target = _file(root, name)
        if not target.is_file():
            raise ValueError("Missing generated file: " + name)
        data = target.read_bytes()
        if _sha(data) != digest:
            raise ValueError("Generated file was manually modified: " + name)
        size += len(data)
        if size > MAX_CHECKPOINT_BYTES:
            raise ValueError("Checkpoint size limit exceeded.")
        content[name] = data
    base = _checkpoint_base(storage_root, project_id)
    base.mkdir(parents=True, exist_ok=True)
    if len(list(base.glob("cp-*"))) >= MAX_CHECKPOINTS:
        raise ValueError("Checkpoint limit reached; archive older checkpoints manually.")
    checkpoint_id = "cp-" + secrets.token_hex(8)
    temp = Path(tempfile.mkdtemp(prefix=".pending-", dir=base))
    try:
        for name, data in content.items():
            target = temp.joinpath(*_relative(name).parts)
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(data)
        info = {
            "id": checkpoint_id,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "label": str(label)[:100],
            "files": {name: _sha(data) for name, data in content.items()},
        }
        (temp / "checkpoint.json").write_text(json.dumps(info, indent=2), encoding="utf-8")
        temp.rename(base / checkpoint_id)
        return info
    except BaseException:
        import shutil
        shutil.rmtree(temp, ignore_errors=True)
        raise


def list_checkpoints(storage_root, project_id):
    base = _checkpoint_base(storage_root, project_id)
    if not base.exists():
        return []
    result = []
    for folder in sorted(base.glob("cp-*"), reverse=True):
        if folder.is_symlink() or not folder.is_dir():
            continue
        try:
            info = json.loads((folder / "checkpoint.json").read_text(encoding="utf-8"))
            if info.get("id") == folder.name and isinstance(info.get("files"), dict):
                result.append(info)
        except (OSError, ValueError, AttributeError):
            continue
    return sorted(result, key=lambda item: item["created_at"], reverse=True)[:MAX_CHECKPOINTS]


def restore_checkpoint(folder, storage_root, project_id, checkpoint_id):
    """Restore an owner-selected checkpoint; refuse manual edits or unsafe paths.

    Retain generated files introduced since the snapshot. A pre-restore backup
    is created first, so an owner can undo the rollback.
    """
    if not isinstance(checkpoint_id, str) or not re.fullmatch(r"cp-[0-9a-f]{16}", checkpoint_id):
        raise ValueError("Invalid checkpoint ID.")
    root = _root(folder)
    base = _checkpoint_base(storage_root, project_id)
    selected = base / checkpoint_id
    if selected.is_symlink() or not selected.is_dir():
        raise ValueError("Checkpoint not found.")
    info = json.loads((selected / "checkpoint.json").read_text(encoding="utf-8"))
    if info.get("id") != checkpoint_id or not isinstance(info.get("files"), dict):
        raise ValueError("Invalid checkpoint manifest.")
    current = _owned(root)
    if not current:
        raise ValueError("Current generated-file manifest missing.")
    staged = {}
    for name, digest in info["files"].items():
        target = _file(root, name)
        source = _file(selected.resolve(), name)
        if name not in current or not isinstance(digest, str):
            raise ValueError("Checkpoint includes a file not currently owned by Foundry.")
        if not source.is_file() or _sha(source.read_bytes()) != digest:
            raise ValueError("Checkpoint integrity check failed: " + name)
        if not target.is_file() or _sha(target.read_bytes()) != current[name]:
            raise ValueError("Manual edits or missing file block rollback: " + name)
        staged[name] = source.read_bytes()
    if not staged:
        raise ValueError("Empty checkpoint.")
    backup = create_checkpoint(root, storage_root, project_id, label="before-restore")
    # All preflight checks and the recovery checkpoint are complete. Replace
    # only files in the snapshot, never delete later generated or manual files.
    for name, data in staged.items():
        target = _file(root, name)
        fd, tmp = tempfile.mkstemp(prefix=".foundry-restore-", dir=target.parent)
        try:
            with os.fdopen(fd, "wb") as handle:
                handle.write(data)
            os.replace(tmp, target)
        finally:
            if os.path.exists(tmp):
                os.unlink(tmp)
        current[name] = _sha(data)
    fd, tmp = tempfile.mkstemp(prefix=".foundry-manifest-", dir=root)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(current, handle, indent=2, sort_keys=True)
        os.replace(tmp, root / MANIFEST)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)
    return {"restored": sorted(staged), "backup_id": backup["id"]}
