"""Prepare Apollo's persistent release-signing identity on the owner's PC.

Never upload the private key into Git, public releases or support chats.
This script is offline: it never connects to GitHub or trusts keys silently.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.serialization import (
    Encoding, PrivateFormat, PublicFormat, NoEncryption, load_pem_private_key
)


def _atomic_new(path, data):
    """Create a file only if absent, without replacing any existing identity."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(str(path), os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        with os.fdopen(fd, "wb") as target:
            target.write(data)
            target.flush()
            os.fsync(target.fileno())
    except BaseException:
        path.unlink(missing_ok=True)
        raise
    try:
        path.chmod(0o600)
    except OSError:
        pass


def prepare_identity(root):
    root = Path(root).expanduser().resolve()
    if not (root / "config.json").is_file() or not (root / "apollo_release.py").is_file():
        raise ValueError("This folder is not an Apollo application root: " + str(root))
    path = root / "storage" / "updates" / "keys"
    private_path = path / "release_private.pem"
    public_path = path / "release_public.pem"
    trust_path = root / "storage" / "updates" / "trust" / "release_public.pem"
    if private_path.exists():
        raw_private = private_path.read_bytes()
        key = load_pem_private_key(raw_private, password=None)
        if not isinstance(key, Ed25519PrivateKey):
            raise ValueError("Existing signing private key is not Ed25519")
        reused = True
    else:
        if public_path.exists():
            raise RuntimeError("Public key already exists but private key is missing. No new key generated: investigate the existing trust identity first.")
        if trust_path.exists():
            raise RuntimeError("An updater trust key already exists but no local signing key is present. Stop and verify the existing issuer before provisioning a new one.")
        key = Ed25519PrivateKey.generate()
        raw_private = key.private_bytes(Encoding.PEM, PrivateFormat.PKCS8, NoEncryption())
        _atomic_new(private_path, raw_private)
        reused = False

    public = key.public_key().public_bytes(Encoding.PEM, PublicFormat.SubjectPublicKeyInfo)
    if public_path.exists():
        if public_path.read_bytes() != public:
            raise RuntimeError("Existing public key does not match the private signing key; refusing to overwrite.")
    else:
        _atomic_new(public_path, public)

    if trust_path.exists() and trust_path.read_bytes() != public:
        raise RuntimeError("Apollo already trusts a DIFFERENT signing key. No trust changes made; manually investigate.")

    fingerprint = hashlib.sha256(public).hexdigest()
    record = path / "RELEASE_PUBLIC_SHA256.txt"
    if record.exists():
        old = record.read_text(encoding="ascii").strip().lower()
        if old != fingerprint:
            raise RuntimeError("Stored fingerprint differs; refusing to change a previously recorded signing identity.")
    else:
        _atomic_new(record, (fingerprint + "\n").encode("ascii"))

    return {
        "reused_existing_signing_key": reused,
        "private_key_file": str(private_path),
        "public_key_file": str(public_path),
        "fingerprint_file": str(record),
        "public_key_sha256": fingerprint,
        "already_trusted_by_apollo": trust_path.exists(),
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description="Offline one-time Apollo release signing identity setup")
    parser.add_argument("--root", required=True, help="Full path to Apollo's apollo_ui folder")
    args = parser.parse_args(argv)
    result = prepare_identity(args.root)
    print("\nAPOLLO RELEASE SIGNING IDENTITY")
    print("Key:", "existing key preserved" if result["reused_existing_signing_key"] else "new Ed25519 key generated locally")
    print("PUBLIC KEY SHA-256:")
    print(result["public_key_sha256"])
    print("\nPublic PEM:", result["public_key_file"])
    print("Private PEM (KEEP SECRET):", result["private_key_file"])
    print("Trust key already installed:", result["already_trusted_by_apollo"])
    print("\nNEXT ACTIONS (you must perform these; nothing has been uploaded):")
    print("1. BACK UP the private PEM securely outside your public Apollo/Git folders.")
    print("2. In GitHub repository Settings > Secrets and variables > Actions:")
    print("   New repository secret APOLLO_RELEASE_PRIVATE_PEM")
    print("   Value: complete contents of the local release_private.pem file.")
    print("3. Under Variables, create APOLLO_RELEASE_PUBLIC_SHA256")
    print("   Value: the exact 64-hex SHA-256 printed above.")
    print("4. In GitHub Actions, publish a verified signed stable/beta Apollo release.")
    print("   The workflow must pass current main-branch CI and confirmation PUBLISH.")
    print("5. In Apollo > Updates > Advanced options > Import Public Key File,")
    print("   choose the public PEM above, and check the fingerprint printed here.")
    print("6. Only then install signed releases. Never bypass signature verification.")
    print("\nPrivate signing material was NOT printed or transferred.")


if __name__ == "__main__":
    main()
