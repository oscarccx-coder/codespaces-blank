"""Publish a SIGNED Apollo application ZIP to GitHub Releases (developer only).

Requires GitHub CLI (gh) authenticated to the repository. The private signing
key is kept locally under storage/updates/keys/ and MUST NEVER be uploaded.
Usage: python tools/publish_github_release.py --channel stable --publish

Run this only after verifying the Windows build and bumping config.json version.
"""
import argparse
from pathlib import Path
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from apollo_github_updates import REPOSITORY
from apollo_release import publish


def publish_to_github(channel, confirmed=False):
    if channel not in {"stable", "beta", "development"}:
        raise ValueError("Publish to stable, beta or development.")
    if not shutil.which("gh"):
        raise RuntimeError("Install GitHub CLI and sign in with: gh auth login")
    branch = subprocess.run(
        ["git", "branch", "--show-current"], cwd=ROOT,
        check=True, text=True, capture_output=True
    ).stdout.strip()
    if channel == "stable" and branch != "main":
        raise RuntimeError("Stable releases must be built from main after verification.")

    result = publish(ROOT, ROOT / "storage" / "updates" / "server", channel)
    version = result["version"]
    if not version or version == "0":
        raise ValueError("Set a valid, incremented app version in config.json.")
    suffix = "" if channel == "stable" else ("-beta" if channel == "beta" else "-dev")
    tag = f"v{version}{suffix}"
    package = Path(result["package"])
    public_key = Path(result["public_key"])
    if not confirmed:
        return {
            "published": False, "tag": tag, "channel": channel,
            "signed_zip": str(package), "public_key": str(public_key),
            "note": "No GitHub Release created. Add --publish after testing."
        }

    args = [
        "gh", "release", "create", tag, str(package), str(public_key),
        "--repo", REPOSITORY, "--target", branch,
        "--title", f"Apollo {version} ({channel})",
        "--notes", (
            "Signed Apollo code-only update. Personal storage and the local XTTS "
            "voice model are excluded. Verify signing key fingerprint from "
            "a separate trusted source before the first install."
        ),
    ]
    if channel != "stable":
        args.append("--prerelease")
    subprocess.run(args, cwd=ROOT, check=True)
    return {"published": True, "tag": tag, "channel": channel, "release": f"https://github.com/{REPOSITORY}/releases/tag/{tag}"}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--channel", choices=["stable", "beta", "development"], default="stable")
    parser.add_argument("--publish", action="store_true",
                        help="Actually create the public GitHub release; omit to prepare only.")
    args = parser.parse_args()
    print(publish_to_github(args.channel, args.publish))
