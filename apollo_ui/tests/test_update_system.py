from pathlib import Path
import tempfile, shutil, json, zipfile
from apollo_release import publish
from apollo_update import UpdateService
from apollo_updater import apply_update
from apollo_storage import StorageLayout
import os
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.serialization import Encoding, PrivateFormat, NoEncryption

# Tests always use a random in-memory key, never a production CI secret.
_original_signing_key = os.environ.get("APOLLO_RELEASE_PRIVATE_PEM")
os.environ["APOLLO_RELEASE_PRIVATE_PEM"] = Ed25519PrivateKey.generate().private_bytes(
    Encoding.PEM, PrivateFormat.PKCS8, NoEncryption()
).decode("ascii")

root = Path(tempfile.mkdtemp(prefix="apollo_update_test_"))
try:
    source = root / "source"
    target = root / "target"
    releases = root / "releases"
    source.mkdir(); target.mkdir()

    # Minimal source release.
    (source / "config.json").write_text(json.dumps({"version":"1.1.0","name":"Apollo"}), encoding="utf-8")
    (source / "main.py").write_text("VALUE = 2\n", encoding="utf-8")
    (source / "apollo_health_check.py").write_text((Path(__file__).with_name("apollo_health_check.py")).read_text(encoding="utf-8"), encoding="utf-8")
    (source / "launch_apollo.pyw").write_text("print('launch')\n", encoding="utf-8")

    published = publish(source, releases, "development")

    # Existing device with user state that must survive.
    (target / "config.json").write_text(json.dumps({"version":"1.0.0","name":"Apollo","model":"keep-me"}), encoding="utf-8")
    (target / "main.py").write_text("VALUE = 1\n", encoding="utf-8")
    (target / "apollo_health_check.py").write_text((Path(__file__).with_name("apollo_health_check.py")).read_text(encoding="utf-8"), encoding="utf-8")
    (target / "launch_apollo.pyw").write_text("print('old launch')\n", encoding="utf-8")
    layout = StorageLayout(target); layout.ensure_layout()
    (target / "workspace").mkdir(); (target / "workspace" / "user.txt").write_text("KEEP", encoding="utf-8")
    (layout.state / "ui_state.json").write_text("KEEPSTATE", encoding="utf-8")

    service = UpdateService(target)
    service.import_trusted_key(releases / "release_public.pem")
    staged = service.stage_local_package(Path(published["package"]))
    assert staged["ok"]
    applied = apply_update(target, staged["stage_dir"], restart=False)
    assert applied["ok"], applied
    assert (target / "main.py").read_text() == "VALUE = 2\n"
    config = json.loads((target / "config.json").read_text())
    assert config["version"] == "1.1.0" and config["model"] == "keep-me"
    assert (target / "workspace" / "user.txt").read_text() == "KEEP"
    assert (layout.state / "ui_state.json").read_text() == "KEEPSTATE"

    # Build a bad signed release; health check must rollback.
    (source / "config.json").write_text(json.dumps({"version":"1.2.0","name":"Apollo"}), encoding="utf-8")
    (source / "main.py").write_text("def broken(:\n", encoding="utf-8")
    bad = publish(source, releases, "development")
    staged_bad = service.stage_local_package(Path(bad["package"]))
    assert staged_bad["ok"]
    rolled = apply_update(target, staged_bad["stage_dir"], restart=False)
    assert not rolled["ok"] and rolled.get("restored")
    assert (target / "main.py").read_text() == "VALUE = 2\n"
    assert json.loads((target / "config.json").read_text())["version"] == "1.1.0"

    print("Update system tests passed.")
finally:
    shutil.rmtree(root, ignore_errors=True)
    if _original_signing_key is None:
        os.environ.pop("APOLLO_RELEASE_PRIVATE_PEM", None)
    else:
        os.environ["APOLLO_RELEASE_PRIVATE_PEM"] = _original_signing_key
