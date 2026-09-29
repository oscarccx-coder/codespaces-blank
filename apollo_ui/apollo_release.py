from pathlib import Path
from datetime import datetime, timezone
import argparse
import base64
import hashlib
import json
import os
import zipfile

from apollo_storage import StorageLayout
from apollo_update import canonical_manifest_bytes


EXCLUDED_TOP_LEVEL = {
    "storage", "workspace", "pending_modules", "config.json",
    "ui_state.json", "modules_state.json", "apollo_memory.db",
    "apollo_error.log", "releases",
}


def sha_bytes(data):
    return hashlib.sha256(data).hexdigest()


def load_version(source):
    return str(json.loads((source / "config.json").read_text(encoding="utf-8")).get("version", "0"))


def ensure_signing_key(source):
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
    from cryptography.hazmat.primitives.serialization import Encoding, PrivateFormat, PublicFormat, NoEncryption

    storage = StorageLayout(source)
    storage.ensure_layout()
    key_dir = storage.updates / "keys"
    key_dir.mkdir(parents=True, exist_ok=True)
    private_path = key_dir / "release_private.pem"
    public_path = key_dir / "release_public.pem"

    if private_path.exists():
        from cryptography.hazmat.primitives.serialization import load_pem_private_key
        private = load_pem_private_key(private_path.read_bytes(), password=None)
    else:
        private = Ed25519PrivateKey.generate()
        private_path.write_bytes(private.private_bytes(Encoding.PEM, PrivateFormat.PKCS8, NoEncryption()))
    public_path.write_bytes(private.public_key().public_bytes(Encoding.PEM, PublicFormat.SubjectPublicKeyInfo))
    return private, private_path, public_path


def iter_release_files(source):
    for path in sorted(source.rglob("*")):
        if not path.is_file() or "__pycache__" in path.parts or path.suffix == ".pyc":
            continue
        rel = path.relative_to(source)
        if rel.parts and rel.parts[0] in EXCLUDED_TOP_LEVEL:
            continue
        if str(rel).replace("\\", "/") in EXCLUDED_TOP_LEVEL:
            continue
        yield path, rel


def publish(source, out_root, channel="development"):
    source = Path(source).resolve()
    out_root = Path(out_root).resolve()
    packages = out_root / "packages"
    packages.mkdir(parents=True, exist_ok=True)
    version = load_version(source)
    private, private_path, public_path = ensure_signing_key(source)

    files = []
    payloads = []
    for path, rel in iter_release_files(source):
        data = path.read_bytes()
        rel_text = str(rel).replace("\\", "/")
        files.append({"path": rel_text, "sha256": sha_bytes(data), "size": len(data)})
        payloads.append((rel_text, data))

    manifest = {
        "schema_version": 1,
        "product": "Apollo",
        "version": version,
        "channel": channel,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "files": files,
        "remove": [],
        "config_version_only": True,
    }
    manifest["signature"] = base64.b64encode(private.sign(canonical_manifest_bytes(manifest))).decode("ascii")

    package_name = f"apollo-{version}.zip"
    package_path = packages / package_name
    with zipfile.ZipFile(package_path, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("manifest.json", json.dumps(manifest, indent=2) + "\n")
        for rel, data in payloads:
            archive.writestr("payload/" + rel, data)

    public_target = out_root / "release_public.pem"
    public_target.write_bytes(public_path.read_bytes())

    index_path = out_root / "index.json"
    try:
        index = json.loads(index_path.read_text(encoding="utf-8"))
    except Exception:
        index = {"schema_version": 1, "channels": {}}
    index.setdefault("channels", {})[channel] = {
        "version": version,
        "package": f"packages/{package_name}",
        "published_at": manifest["created_at"],
    }
    index_path.write_text(json.dumps(index, indent=2) + "\n", encoding="utf-8")
    return {"package": str(package_path), "index": str(index_path), "public_key": str(public_target), "private_key": str(private_path), "version": version}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Publish a signed Apollo update release.")
    parser.add_argument("--source", default=".")
    parser.add_argument("--out", default="storage/updates/server")
    parser.add_argument("--channel", default="development", choices=["development", "beta", "stable", "pinned"])
    args = parser.parse_args()
    result = publish(args.source, args.out, args.channel)
    print(json.dumps(result, indent=2))
