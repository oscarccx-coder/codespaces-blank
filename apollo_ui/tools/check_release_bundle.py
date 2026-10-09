"""Exercise the full source ZIP with an ephemeral test key; NEVER publish.

Run from apollo_ui after unit tests. CI verifies the Raspberry Pi deployment
files are actually present in the signed cross-platform code package and that
personal runtime/model files have been excluded.
"""
from pathlib import Path
import json
import os
import sys
import tempfile
import zipfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from apollo_release import publish
from apollo_github_updates import MAX_PACKAGE_BYTES
from tools.release_ci import verify_release
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.serialization import Encoding, PrivateFormat, NoEncryption

NEEDED = {
    "apollo_pi.py", "pi/install_pi.sh", "pi/update_pi.py", "pi/update_pi.sh",
    "apollo_updater.py", "apollo_release.py", "apollo_update.py",
    "ollama_client.py", "memory.py",
}
FORBIDDEN = ("storage/", "Audio/", "models/", "workspace/",
             "pending_modules/", ".venv/", ".venv-pi/", "venv/")


def main():
    original = os.environ.get("APOLLO_RELEASE_PRIVATE_PEM")
    ephemeral = Ed25519PrivateKey.generate().private_bytes(
        Encoding.PEM, PrivateFormat.PKCS8, NoEncryption()
    ).decode("ascii")
    try:
        os.environ["APOLLO_RELEASE_PRIVATE_PEM"] = ephemeral
        with tempfile.TemporaryDirectory(prefix="apollo_package_test_") as temp:
            package = publish(ROOT, Path(temp), "beta")
            manifest = verify_release(package["package"], package["public_key"])
            paths = {item["path"] for item in manifest["files"]}
            missing = NEEDED - paths
            if missing:
                raise AssertionError(f"Pi/update sources absent from signed release: {sorted(missing)}")
            forbidden = [p for p in paths if p.startswith(FORBIDDEN)]
            if forbidden:
                raise AssertionError(f"Private directories included in release: {forbidden[:10]}")
            size = Path(package["package"]).stat().st_size
            if size > MAX_PACKAGE_BYTES:
                raise AssertionError("Release exceeds client's package size cap")
            print(json.dumps({"result": "full signed package PASS",
                              "version": manifest["version"], "files": len(paths),
                              "compressed_bytes": size, "contains_pi": True}))
    finally:
        if original is None:
            os.environ.pop("APOLLO_RELEASE_PRIVATE_PEM", None)
        else:
            os.environ["APOLLO_RELEASE_PRIVATE_PEM"] = original


if __name__ == "__main__":
    main()
