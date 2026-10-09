"""GitHub Actions signed-release gate.

No implicit publish: CI requires a pre-existing Ed25519 signing key in
APOLLO_RELEASE_PRIVATE_PEM and an independently pinned public-key fingerprint
in APOLLO_RELEASE_PUBLIC_SHA256. Never log or upload the signing secret.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import zipfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from apollo_release import publish
from apollo_update import verify_manifest_signature
from apollo_github_updates import REPOSITORY

CHANNELS = ("stable", "beta")
VERSION = re.compile(r"^\d+(?:\.\d+){2,4}$")
FINGERPRINT = re.compile(r"^[0-9a-f]{64}$")


def tag_for(version, channel):
    if not VERSION.fullmatch(str(version)) or channel not in CHANNELS:
        raise ValueError("Invalid release version/channel")
    return f"v{version}" + ("-beta" if channel == "beta" else "")


def verify_release(package, public_key):
    """Check every signed manifest entry against the ZIP before publishing."""
    with zipfile.ZipFile(package, "r") as zip_file:
        manifest = json.loads(zip_file.read("manifest.json"))
        valid, reason = verify_manifest_signature(manifest, public_key)
        if not valid:
            raise ValueError("Signature check failed: " + reason)
        files = manifest.get("files", [])
        if not isinstance(files, list) or not files:
            raise ValueError("Release is empty")
        if len({v.get("path") for v in files if isinstance(v, dict)}) != len(files):
            raise ValueError("Duplicate or malformed file entries")
        for entry in files:
            name = entry["path"]
            if not isinstance(name, str) or name.startswith("/") or ".." in name.split("/"):
                raise ValueError("Unsafe package path")
            data = zip_file.read("payload/" + name)
            if len(data) != entry.get("size"):
                raise ValueError("Invalid package file size: " + name)
            if hashlib.sha256(data).hexdigest() != entry.get("sha256"):
                raise ValueError("Invalid package file hash: " + name)
        return manifest


def prepare(channel, expected_sha, fingerprint):
    if channel not in CHANNELS:
        raise ValueError("Only beta and stable releases may be published")
    if not os.environ.get("APOLLO_RELEASE_PRIVATE_PEM"):
        raise RuntimeError("Missing GitHub Actions signing secret APOLLO_RELEASE_PRIVATE_PEM")
    if not FINGERPRINT.fullmatch(str(fingerprint or "").lower()):
        raise RuntimeError("Configure 64-hex APOLLO_RELEASE_PUBLIC_SHA256 repository variable")
    actual_sha = subprocess.check_output(
        ["git", "-C", str(ROOT), "rev-parse", "HEAD"], text=True
    ).strip()
    if not re.fullmatch(r"[0-9a-f]{40}", expected_sha or "") or actual_sha != expected_sha:
        raise RuntimeError("Refusing release: checkout does not match verified commit")
    built = publish(ROOT, ROOT / "storage" / "updates" / "server", channel)
    published_fingerprint = hashlib.sha256(Path(built["public_key"]).read_bytes()).hexdigest()
    if published_fingerprint != fingerprint.lower():
        raise RuntimeError("Release signing key fingerprint mismatch. STOP; do not rotate keys silently.")
    manifest = verify_release(built["package"], built["public_key"])
    if manifest.get("channel") != channel or manifest.get("version") != built["version"]:
        raise RuntimeError("Signed package metadata does not match requested release")
    tag = tag_for(built["version"], channel)
    checksum = ROOT / "storage" / "updates" / "server" / "SHA256SUMS.txt"
    checksum.write_text(
        f"{hashlib.sha256(Path(built['package']).read_bytes()).hexdigest()}  "
        f"{Path(built['package']).name}\n", encoding="ascii"
    )
    return {"tag": tag, "channel": channel, "sha": expected_sha,
            "package": built["package"], "public_key": built["public_key"],
            "checksum": str(checksum), "fingerprint": published_fingerprint}


def publish_to_github(bundle, skip_existing=False):
    tag = bundle["tag"]
    # Existing releases are immutable for us. No asset replacement, ever.
    already = subprocess.run(
        ["gh", "release", "view", tag, "--repo", REPOSITORY],
        capture_output=True, text=True, check=False
    ).returncode == 0
    if already:
        if skip_existing:
            return {"published": False, "skipped": True, "tag": tag}
        raise RuntimeError(f"Release {tag} already exists; increment version first")
    cmd = [
        "gh", "release", "create", tag,
        bundle["package"], bundle["public_key"], bundle["checksum"],
        "--repo", REPOSITORY, "--target", bundle["sha"],
        "--title", f"Apollo {tag[1:]} ({bundle['channel']})",
        "--notes", (
            "Signed Apollo code update for Windows and the Raspberry Pi ARM64 "
            "headless companion. Keeps local models, recordings, settings and "
            "databases on each device. Verify the Ed25519 public-key SHA-256 "
            "fingerprint independently before the first update."
        )
    ]
    if bundle["channel"] == "beta":
        cmd.append("--prerelease")
    subprocess.run(cmd, check=True)
    return {"published": True, "tag": tag,
            "url": f"https://github.com/{REPOSITORY}/releases/tag/{tag}"}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--channel", choices=CHANNELS, required=True)
    parser.add_argument("--commit", required=True)
    parser.add_argument("--skip-existing", action="store_true")
    args = parser.parse_args(argv)
    bundle = prepare(args.channel, args.commit, os.getenv("APOLLO_RELEASE_PUBLIC_SHA256", ""))
    result = publish_to_github(bundle, skip_existing=args.skip_existing)
    print(json.dumps({"result": result, "public_key_sha256": bundle["fingerprint"]},
                     indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
