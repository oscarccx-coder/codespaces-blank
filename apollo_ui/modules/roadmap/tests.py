from pathlib import Path
import json
import tempfile
import shutil

from module import Module

root = Path(tempfile.mkdtemp(prefix="apollo_roadmap2_"))
try:
    storage = root / "storage" / "state" / "roadmap"
    storage.mkdir(parents=True)
    (storage / "roadmap.json").write_text(json.dumps({
        "updated_at": "legacy",
        "items": [
            {
                "version": "7.5.13",
                "title": "Old title",
                "status": "in_progress",
                "summary": "Keep my progress"
            }
        ]
    }), encoding="utf-8")

    source_blueprints = Path(__file__).resolve().parents[2] / "blueprints" / "future_features"
    shutil.copytree(source_blueprints, root / "blueprints" / "future_features")

    module = Module({"base_dir": str(root)})
    assert module.self_test()

    data = module.run("roadmap_status", {})
    ids = {item["id"] for item in data["items"]}
    assert "image_core" in ids
    assert "compute_broker" in ids
    assert "apollo_os_preview" in ids

    migrated = next(item for item in data["items"] if item["version"] == "7.5.13")
    assert migrated["status"] == "in_progress"
    assert migrated["summary"] == "Keep my progress"

    placeholders = module.run("feature_placeholders", {})
    assert len(placeholders["features"]) >= 20

    image_core = module.run("feature_placeholder", {"feature_id": "image_core"})
    assert "generate_image" in image_core["planned_tools"]

    print("Roadmap 2.0 tests passed.")
finally:
    shutil.rmtree(root, ignore_errors=True)
