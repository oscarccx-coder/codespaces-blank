from pathlib import Path
import tempfile, shutil
from apollo_storage import StorageLayout

root = Path(tempfile.mkdtemp(prefix="apollo_storage_test_"))
try:
    (root / "storage").mkdir()
    (root / "apollo_memory.db").write_text("memory", encoding="utf-8")
    (root / "ui_state.json").write_text("{}", encoding="utf-8")
    (root / "storage" / "memory_bank.db").write_text("bank", encoding="utf-8")
    (root / "storage" / "shell").mkdir()
    (root / "storage" / "shell" / "hub_layout.json").write_text("{}", encoding="utf-8")
    (root / "storage" / "screenshots").mkdir()
    (root / "storage" / "screenshots" / "a.png").write_bytes(b"png")

    layout = StorageLayout(root)
    result = layout.ensure_layout()
    assert result["ok"]
    assert (layout.databases / "apollo_memory.db").read_text() == "memory"
    assert (layout.databases / "memory_bank.db").read_text() == "bank"
    assert (layout.state / "ui_state.json").exists()
    assert (layout.state / "shell" / "hub_layout.json").exists()
    assert (layout.media / "screenshots" / "a.png").exists()
    assert not (root / "apollo_memory.db").exists()
    assert not (root / "storage" / "shell").exists()
    # Idempotent second run.
    assert layout.ensure_layout()["ok"]
    print("Storage layout tests passed.")
finally:
    shutil.rmtree(root, ignore_errors=True)
