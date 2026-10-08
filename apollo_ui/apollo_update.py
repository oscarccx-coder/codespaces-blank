from pathlib import Path
from datetime import datetime, timezone
import base64
import hashlib
import json
import os
import platform
import shutil
import subprocess
import sys
import urllib.parse
import urllib.request
import uuid
import zipfile

from apollo_storage import StorageLayout
from apollo_github_updates import REPOSITORY, latest_release, download_release_asset


def utc_now():
    return datetime.now(timezone.utc).isoformat()


def sha256_file(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def version_key(value):
    parts = []
    for token in str(value or "0").replace("-", ".").split("."):
        digits = "".join(ch for ch in token if ch.isdigit())
        parts.append(int(digits or 0))
    while len(parts) < 4:
        parts.append(0)
    return tuple(parts[:4])


def canonical_manifest_bytes(manifest):
    data = dict(manifest or {})
    data.pop("signature", None)
    return json.dumps(data, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def verify_manifest_signature(manifest, public_key_path):
    try:
        from cryptography.hazmat.primitives.serialization import load_pem_public_key
        signature = base64.b64decode(str(manifest.get("signature", "")))
        if not signature:
            return False, "manifest has no signature"
        key = load_pem_public_key(Path(public_key_path).read_bytes())
        key.verify(signature, canonical_manifest_bytes(manifest))
        return True, "signature valid"
    except Exception as exc:
        return False, f"{type(exc).__name__}: {exc}"


class UpdateService:
    """Signed Apollo release client suitable for one or many Apollo devices."""

    def __init__(self, base_dir):
        self.base = Path(base_dir).resolve()
        self.storage = StorageLayout(self.base)
        self.storage.ensure_layout()
        self.root = self.storage.updates
        self.config_dir = self.root / "config"
        self.device_dir = self.root / "device"
        self.trust_dir = self.root / "trust"
        self.staged_dir = self.root / "staged"
        self.download_dir = self.root / "downloads"
        self.logs_dir = self.root / "logs"
        for path in (self.config_dir, self.device_dir, self.trust_dir, self.staged_dir, self.download_dir, self.logs_dir):
            path.mkdir(parents=True, exist_ok=True)
        self.settings_path = self.config_dir / "settings.json"
        self.device_path = self.device_dir / "device.json"
        self.public_key_path = self.trust_dir / "release_public.pem"
        self._ensure_defaults()

    def _current_version(self):
        try:
            return str(json.loads((self.base / "config.json").read_text(encoding="utf-8")).get("version", "0"))
        except Exception:
            return "0"

    def _ensure_defaults(self):
        if not self.settings_path.exists():
            self.settings_path.write_text(json.dumps({
                "source": "github",
                "server_url": "",
                "channel": "stable",
                "auto_check": False,
                "allow_unsigned": False,
            }, indent=2) + "\n", encoding="utf-8")
        if not self.device_path.exists():
            self.device_path.write_text(json.dumps({
                "device_id": str(uuid.uuid4()),
                "device_name": platform.node() or "Apollo Device",
                "platform": platform.platform(),
                "created_at": utc_now(),
            }, indent=2) + "\n", encoding="utf-8")

    def settings(self):
        data = json.loads(self.settings_path.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            raise ValueError("Update settings must be an object.")
        # Existing local-server installs keep their configured transport.
        data.setdefault("source", "server" if data.get("server_url") else "github")
        data.setdefault("channel", "stable")
        return data

    def device(self):
        return json.loads(self.device_path.read_text(encoding="utf-8"))

    def configure(self, server_url=None, channel=None, auto_check=None, device_name=None, source=None):
        settings = self.settings()
        if source is not None:
            source = str(source).strip().lower()
            if source not in {"github", "server"}:
                raise ValueError("Update source must be github or server.")
            settings["source"] = source
        if server_url is not None:
            settings["server_url"] = str(server_url).strip().rstrip("/")
        if channel is not None:
            channel = str(channel).strip().lower()
            if channel not in {"development", "beta", "stable", "pinned"}:
                raise ValueError("channel must be development, beta, stable or pinned")
            settings["channel"] = channel
        if auto_check is not None:
            settings["auto_check"] = bool(auto_check)
        self.settings_path.write_text(json.dumps(settings, indent=2) + "\n", encoding="utf-8")

        if device_name is not None:
            device = self.device()
            device["device_name"] = str(device_name).strip() or device["device_name"]
            self.device_path.write_text(json.dumps(device, indent=2) + "\n", encoding="utf-8")
        return self.status()

    def import_trusted_key(self, source):
        source = Path(source).resolve()
        if not source.exists():
            raise FileNotFoundError(source)
        data = source.read_bytes()
        if b"PUBLIC KEY" not in data:
            raise ValueError("Not a PEM public key")
        self.public_key_path.write_bytes(data)
        return {"ok": True, "trusted_key": str(self.public_key_path)}

    def status(self):
        settings = self.settings()
        staged = []
        for folder in sorted(self.staged_dir.iterdir()) if self.staged_dir.exists() else []:
            if (folder / "manifest.json").exists():
                try:
                    staged.append(json.loads((folder / "manifest.json").read_text(encoding="utf-8")))
                except Exception:
                    pass
        return {
            "current_version": self._current_version(),
            "device": self.device(),
            "settings": settings,
            "trusted_key": self.public_key_path.exists(),
            "staged_versions": [str(item.get("version")) for item in staged],
            "github_repository": REPOSITORY,
            "last_install": self._latest_install(),
        }

    def _latest_install(self):
        try:
            logs = sorted(self.logs_dir.glob("installed-*.json"), key=lambda p: p.stat().st_mtime)
            rollbacks = sorted(self.logs_dir.glob("rollback-*.json"), key=lambda p: p.stat().st_mtime)
            recent = sorted(logs[-1:] + rollbacks[-1:], key=lambda p: p.stat().st_mtime)
            return json.loads(recent[-1].read_text(encoding="utf-8")) if recent else None
        except (OSError, ValueError, TypeError):
            return None

    @staticmethod
    def _url_join(base, relative):
        return urllib.parse.urljoin(base.rstrip("/") + "/", str(relative).lstrip("/"))

    @staticmethod
    def _read_url_json(url, timeout=10):
        request = urllib.request.Request(url, headers={"User-Agent": "Apollo-Updater/1"})
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return json.loads(response.read().decode("utf-8"))

    def check_for_updates(self):
        settings = self.settings()
        channel = str(settings.get("channel", "stable"))
        current = self._current_version()
        if settings["source"] == "github":
            release = latest_release(channel)
            if release is None:
                return {
                    "ok": True, "available": False, "current_version": current,
                    "source": "github", "repository": REPOSITORY,
                    "reason": f"No matching {channel} GitHub Release with a signed Apollo ZIP asset.",
                }
            return {
                "ok": True,
                "available": version_key(release["version"]) > version_key(current),
                "current_version": current, "release": release,
                "source": "github", "repository": REPOSITORY,
            }

        server = str(settings.get("server_url", "")).strip()
        if not server:
            return {"ok": False, "error": "No update server URL is configured."}
        if not server.startswith(("https://", "http://127.0.0.1:", "http://localhost:")):
            return {"ok": False, "error": "Use HTTPS or localhost for an update server."}
        index_url = self._url_join(server, "index.json")
        index = self._read_url_json(index_url)
        release = (index.get("channels") or {}).get(channel)
        if not isinstance(release, dict):
            return {"ok": True, "available": False, "reason": f"No {channel} release published."}
        version = str(release.get("version", "0"))
        return {
            "ok": True, "available": version_key(version) > version_key(current),
            "current_version": current, "release": release,
            "index_url": index_url, "source": "server",
        }

    def _verify_package(self, package_path):
        package_path = Path(package_path).resolve()
        if not package_path.exists():
            return False, "package missing", None
        try:
            with zipfile.ZipFile(package_path, "r") as archive:
                manifest = json.loads(archive.read("manifest.json").decode("utf-8"))
                if not self.public_key_path.exists():
                    return False, "No trusted release public key is installed.", manifest
                sig_ok, sig_detail = verify_manifest_signature(manifest, self.public_key_path)
                if not sig_ok:
                    return False, sig_detail, manifest
                for item in manifest.get("files", []):
                    rel = str(item.get("path", ""))
                    member = "payload/" + rel.replace("\\", "/")
                    data = archive.read(member)
                    digest = hashlib.sha256(data).hexdigest()
                    if digest != str(item.get("sha256", "")):
                        return False, f"Hash mismatch: {rel}", manifest
            return True, "verified", manifest
        except Exception as exc:
            return False, f"{type(exc).__name__}: {exc}", None

    def stage_local_package(self, package_path, expected_version=None, expected_channel=None):
        """Signature-check and unpack only explicitly signed, safe file paths."""
        from apollo_updater import safe_relative
        import re
        package_path = Path(package_path).resolve()
        ok, detail, manifest = self._verify_package(package_path)
        if not ok:
            return {"ok": False, "error": detail}
        if manifest.get("product") != "Apollo":
            return {"ok": False, "error": "This is not an Apollo release."}
        version = str(manifest.get("version", "")).strip()
        if not re.fullmatch(r"\d+(?:\.\d+){1,4}", version):
            return {"ok": False, "error": "Malformed signed release version."}
        if expected_version and version != str(expected_version):
            return {"ok": False, "error": "GitHub release version and signed version do not match."}
        if expected_channel and manifest.get("channel") != expected_channel:
            return {"ok": False, "error": "GitHub release channel and signed channel do not match."}
        if version_key(version) <= version_key(self._current_version()):
            return {"ok": False, "error": "Release is not newer than this Apollo installation."}
        items = manifest.get("files")
        if not isinstance(items, list) or not items or len(items) > 4000:
            return {"ok": False, "error": "Invalid signed release file list."}
        seen = set()
        validated = []
        try:
            for item in items:
                if not isinstance(item, dict):
                    raise ValueError("Malformed file entry")
                rel = safe_relative(item.get("path"))
                key = str(rel).casefold()
                if key in seen:
                    raise ValueError("Duplicate signed path")
                seen.add(key)
                validated.append(rel)
            for path in manifest.get("remove", []):
                safe_relative(path)
        except (ValueError, TypeError) as exc:
            return {"ok": False, "error": f"Unsafe release manifest: {exc}"}

        # No extractall(): extracting arbitrary ZIP members invites path traversal.
        # Write only the signed payload list to a temporary staging directory.
        temporary = self.staged_dir / (version + ".incoming")
        destination = self.staged_dir / version
        if temporary.exists():
            shutil.rmtree(temporary)
        temporary.mkdir(parents=True)
        try:
            with zipfile.ZipFile(package_path) as archive:
                (temporary / "manifest.json").write_text(
                    json.dumps(manifest, indent=2) + "\n", encoding="utf-8"
                )
                for rel in validated:
                    member = "payload/" + rel.as_posix()
                    staged = temporary / "payload" / rel
                    staged.parent.mkdir(parents=True, exist_ok=True)
                    with archive.open(member) as inp, staged.open("wb") as out:
                        shutil.copyfileobj(inp, out, length=1024 * 1024)
            if destination.exists():
                shutil.rmtree(destination)
            temporary.rename(destination)
        except Exception as exc:
            shutil.rmtree(temporary, ignore_errors=True)
            return {"ok": False, "error": f"Could not stage signed release: {exc}"}
        return {"ok": True, "version": version, "stage_dir": str(destination),
                "manifest": manifest}

    def stage_update(self, progress=None):
        if not self.public_key_path.exists():
            return {"ok": False, "error": "No trusted signing key. Import the release public key once before installing updates."}
        check = self.check_for_updates()
        if not check.get("ok") or not check.get("available"):
            return check
        release = check["release"]
        version = str(release.get("version"))
        package_path = self.download_dir / f"apollo-{version}.zip"

        if check.get("source") == "github":
            result = download_release_asset(release["package_url"], package_path, progress)
            staged = self.stage_local_package(
                package_path, expected_version=version,
                expected_channel=release["channel"]
            )
            staged["package_url"] = release["package_url"]
            staged["downloaded_bytes"] = result["bytes"]
            return staged

        server = self.settings()["server_url"]
        package_url = self._url_join(server, release.get("package"))
        request = urllib.request.Request(package_url, headers={"User-Agent": "Apollo-Updater/1"})
        temporary = package_path.with_suffix(".zip.part")
        try:
            with urllib.request.urlopen(request, timeout=60) as response, temporary.open("wb") as out:
                shutil.copyfileobj(response, out)
            temporary.replace(package_path)
        finally:
            if temporary.exists():
                temporary.unlink()
        result = self.stage_local_package(package_path, expected_version=version)
        result["package_url"] = package_url
        return result

    def launch_installer(self, version=None, restart=True):
        if version is None:
            versions = []
            for folder in self.staged_dir.iterdir():
                manifest_path = folder / "manifest.json"
                if manifest_path.exists():
                    try:
                        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
                        versions.append((version_key(manifest.get("version")), folder, manifest))
                    except Exception:
                        pass
            if not versions:
                return {"ok": False, "error": "No staged update is available."}
            _, stage, manifest = sorted(versions, key=lambda item: item[0])[-1]
        else:
            stage = self.staged_dir / str(version)
            manifest = json.loads((stage / "manifest.json").read_text(encoding="utf-8"))
        args = [
            sys.executable,
            str(self.base / "apollo_updater.py"),
            "--target", str(self.base),
            "--stage", str(stage),
            "--wait-pid", str(os.getpid()),
        ]
        if restart:
            args.append("--restart")
        subprocess.Popen(args, cwd=str(self.base), close_fds=True)
        return {"ok": True, "version": manifest.get("version"), "installer_started": True}
