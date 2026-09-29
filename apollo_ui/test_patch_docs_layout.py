from pathlib import Path
import tempfile
import shutil

from apollo_docs import PatchDocs

root = Path(tempfile.mkdtemp(prefix="apollo_docs_test_"))
try:
    (root / "PATCH_NOTES.md").write_text("old notes", encoding="utf-8")
    (root / "PATCH_README_V1.txt").write_text("old readme", encoding="utf-8")

    docs = PatchDocs(root)
    result = docs.ensure_layout()
    assert result["ok"]
    assert not (root / "PATCH_NOTES.md").exists()
    assert not (root / "PATCH_README_V1.txt").exists()
    assert (root / "docs" / "patch_notes" / "PATCH_NOTES.md").read_text() == "old notes"
    assert (root / "docs" / "patch_notes" / "PATCH_README_V1.txt").read_text() == "old readme"

    # Conflicting old root copy must be preserved, not destroyed.
    (root / "PATCH_NOTES.md").write_text("different legacy notes", encoding="utf-8")
    docs.ensure_layout()
    assert not (root / "PATCH_NOTES.md").exists()
    legacy = list((root / "docs" / "patch_notes" / "legacy_root_files").glob("PATCH_NOTES.root-*.md"))
    assert legacy
    assert legacy[-1].read_text(encoding="utf-8") == "different legacy notes"

    print("Patch docs layout tests passed.")
finally:
    shutil.rmtree(root, ignore_errors=True)
