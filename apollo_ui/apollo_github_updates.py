"""GitHub Releases transport for signed Apollo application updates.

GitHub is a download transport, never a trust authority: packages must still
pass Apollo's pinned Ed25519 manifest signature and per-file SHA-256 checks.
"""
import json
import re
import shutil
import urllib.parse
import urllib.request
from pathlib import Path

REPOSITORY = "oscarccx-coder/codespaces-blank"
API = f"https://api.github.com/repos/{REPOSITORY}/releases?per_page=100"
MAX_PACKAGE_BYTES = 512 * 1024 * 1024
MAX_INDEX_BYTES = 2 * 1024 * 1024
USER_AGENT = "Apollo-GitHub-Updates/1"


def _segment_tokens(value):
    return [piece for piece in re.split(r"[^a-z0-9]+", str(value).lower()) if piece]


def _matching_channel(release, channel):
    """Stable uses GitHub stable releases; pre-releases need explicit labels."""
    if release.get("draft"):
        return False
    prerelease = bool(release.get("prerelease"))
    if channel == "stable":
        return not prerelease
    if channel not in {"beta", "development"} or not prerelease:
        return False
    tokens = _segment_tokens(str(release.get("tag_name", "")))
    return bool(set(tokens) & ({"dev", "development"} if channel == "development" else {"beta"}))


def _version_from_tag(tag):
    match = re.search(r"(?:^|[^0-9])v?(\d+(?:\.\d+){1,4})(?=$|[^0-9])", str(tag), re.I)
    return match.group(1) if match else ""


def _asset_url(url):
    """Do not follow an arbitrary URL supplied by a GitHub release record."""
    parsed = urllib.parse.urlsplit(str(url))
    prefix = f"/{REPOSITORY}/releases/download/"
    if parsed.scheme != "https" or parsed.netloc.lower() != "github.com":
        raise ValueError("Update asset must be served from github.com over HTTPS.")
    if not parsed.path.startswith(prefix) or parsed.username or parsed.password or parsed.query or parsed.fragment:
        raise ValueError("Unexpected GitHub Release asset URL.")
    return str(url)


def _read_releases():
    request = urllib.request.Request(API, headers={
        "User-Agent": USER_AGENT, "Accept": "application/vnd.github+json",
    })
    with urllib.request.urlopen(request, timeout=12) as response:
        payload = response.read(MAX_INDEX_BYTES + 1)
    if len(payload) > MAX_INDEX_BYTES:
        raise ValueError("GitHub Releases index is too large.")
    data = json.loads(payload.decode("utf-8"))
    if not isinstance(data, list):
        raise ValueError("Unexpected GitHub Releases response.")
    return data


def latest_release(channel, releases=None):
    """Find newest matching signed-package candidate, without trusting it yet."""
    from apollo_update import version_key
    if channel == "pinned":
        return None
    releases = _read_releases() if releases is None else releases
    matches = []
    for entry in releases:
        if not isinstance(entry, dict) or not _matching_channel(entry, channel):
            continue
        version = _version_from_tag(entry.get("tag_name"))
        if not version:
            continue
        assets = entry.get("assets")
        if not isinstance(assets, list):
            continue
        wanted = f"apollo-{version}.zip"
        asset = next((a for a in assets
                      if isinstance(a, dict) and a.get("name") == wanted), None)
        if asset is None:
            continue
        try:
            address = _asset_url(asset.get("browser_download_url"))
            asset_size = int(asset.get("size", 0))
            if not 0 < asset_size <= MAX_PACKAGE_BYTES:
                continue
        except (TypeError, ValueError):
            continue
        key_asset = next((a for a in assets
                          if isinstance(a, dict) and a.get("name") == "release_public.pem"
                          and 0 < int(a.get("size") or 0) <= 65536), None)
        key_url = None
        if key_asset:
            try:
                key_url = _asset_url(key_asset.get("browser_download_url"))
            except ValueError:
                pass
        matches.append({
            "key_url": key_url,
            "version": version,
            "package_url": address,
            "size": asset_size,
            "channel": channel,
            "tag_name": str(entry.get("tag_name")),
            "published_at": str(entry.get("published_at", "")),
            "html_url": f"https://github.com/{REPOSITORY}/releases",
        })
    return max(matches, key=lambda item: version_key(item["version"])) if matches else None


def download_release_asset(url, destination, progress=None, max_bytes=MAX_PACKAGE_BYTES):
    """Bounded atomic download; redirects may only end on GitHub's asset CDN."""
    url = _asset_url(url)
    destination = Path(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)
    tmp = destination.with_name(destination.name + ".part")
    try:
        request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
        with urllib.request.urlopen(request, timeout=60) as response:
            final = urllib.parse.urlsplit(response.geturl())
            if (final.scheme != "https" or final.hostname not in {
                "github.com", "release-assets.githubusercontent.com", "objects.githubusercontent.com"
            }):
                raise ValueError("GitHub asset redirect left the allowed HTTPS hosts.")
            length = response.headers.get("Content-Length")
            if length and int(length) > max_bytes:
                raise ValueError("GitHub update package exceeds the download limit.")
            amount = 0
            with tmp.open("wb") as output:
                while True:
                    chunk = response.read(1024 * 1024)
                    if not chunk:
                        break
                    amount += len(chunk)
                    if amount > max_bytes:
                        raise ValueError("GitHub update package exceeds the download limit.")
                    output.write(chunk)
                    if progress:
                        progress(amount, int(length) if length else 0)
        if not amount:
            raise ValueError("GitHub release asset was empty.")
        tmp.replace(destination)
        return {"file": str(destination), "bytes": amount}
    finally:
        if tmp.exists():
            tmp.unlink()
