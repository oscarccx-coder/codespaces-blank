"""Independent, read-only assessment before a signed Apollo self-install.

No model output, GitHub issue, Foundry draft or plain "test passed" flag can
authorise code installation. Only a correctly signed, hash-checked staged
release, safe source parsing and a feasible rollback backup pass this gate.
The external installer independently repeats the same assessment immediately
before installing. No code is executed by this assessment.
"""
from __future__ import annotations

import ast
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import shutil

from apollo_storage import StorageLayout
from apollo_update import verify_manifest_signature, version_key
from apollo_updater import preflight_manifest

MAX_FILES = 4000
MAX_MANIFEST_BYTES = 1024 * 1024
MIN_FREE_HEADROOM = 16 * 1024 * 1024


def _time():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class AssessmentFailure(ValueError):
    pass


class AssessedUpdate:
    def __init__(self, target):
        self.target = Path(target).resolve()
        self.layout = StorageLayout(self.target)
        self.root = self.layout.updates
        self.report_dir = self.root / "assessments"

    def _stage(self, stage):
        staged = Path(stage).resolve()
        parent = (self.root / "staged").resolve()
        if staged.parent != parent or not staged.is_dir() or staged.is_symlink():
            raise AssessmentFailure("Use one staged update inside Apollo's own signed-release directory.")
        return staged

    def assess(self, stage, *, save=True):
        """Return a bounded evidence record without touching installed source.

        Assessment reports are advisory, not trusted authorisations. Installer
        MUST recompute the signature, all hashes and every gate itself.
        """
        report = {
            "schema": 1, "ok": False, "assessed_at": _time(),
            "assessment_kind": "signed-source-preflight-not-runtime-tests",
            "target_version": None, "current_version": None,
            "manifest_sha256": None,
            "checks": [], "changed": 0, "removed": 0,
            "static_python_checked": 0, "json_checked": 0,
            "estimated_core_backup_bytes": 0,
            "runtime_tests_executed": False,
            "manual_release_approval_required": True,
            "reason": "",
        }
        def check(name, detail):
            report["checks"].append({"check": name, "passed": True, "detail": str(detail)[:250]})

        try:
            stage = self._stage(stage)
            manifest_path = stage / "manifest.json"
            if manifest_path.is_symlink() or manifest_path.stat().st_size > MAX_MANIFEST_BYTES:
                raise AssessmentFailure("Missing, symlinked or excessive signed release manifest.")
            raw = manifest_path.read_bytes()
            manifest = json.loads(raw.decode("utf-8"))
            if not isinstance(manifest, dict):
                raise AssessmentFailure("Release manifest must be an object.")
            report["manifest_sha256"] = hashlib.sha256(raw).hexdigest()
            if manifest.get("product") != "Apollo":
                raise AssessmentFailure("Not an Apollo signed release.")
            version = str(manifest.get("version", ""))
            if not re.fullmatch(r"\d+(?:\.\d+){1,4}", version):
                raise AssessmentFailure("Invalid signed release version.")
            if stage.name != version:
                raise AssessmentFailure("Staging directory does not match signed release version.")
            report["target_version"] = version

            key = self.root / "trust" / "release_public.pem"
            if not key.is_file() or key.is_symlink():
                raise AssessmentFailure("A pinned trusted signing key is required.")
            ok, _detail = verify_manifest_signature(manifest, key)
            if not ok:
                raise AssessmentFailure("Ed25519 release signature is not trusted.")
            check("trusted_release", "Manifest signature verified against locally trusted key.")

            config_path = self.target / "config.json"
            if not config_path.is_file() or config_path.is_symlink():
                raise AssessmentFailure("Existing Apollo config must be a regular file.")
            current = json.loads(config_path.read_text(encoding="utf-8"))
            if not isinstance(current, dict):
                raise AssessmentFailure("Existing Apollo config is invalid.")
            existing_version = str(current.get("version", "0"))
            report["current_version"] = existing_version
            if version_key(version) <= version_key(existing_version):
                raise AssessmentFailure("Refusing a same-version or older release.")
            check("version_forward_only", existing_version + " -> " + version)

            entries = manifest.get("files")
            if not isinstance(entries, list) or not 1 <= len(entries) <= MAX_FILES:
                raise AssessmentFailure("Signed release has an invalid source file count.")
            files, removed = preflight_manifest(stage, self.target, manifest)
            report["changed"], report["removed"] = len(files), len(removed)
            check("signed_file_hashes", "%d source file digests verified." % len(files))
            check("safe_paths", "%d signed removals checked; private storage protected." % len(removed))

            # AST checking does not import/execute source, and is bounded by
            # the signed manifest's size/copy limits from staging.
            for rel, source in files:
                if source.is_symlink():
                    raise AssessmentFailure("Symlinked candidate source is forbidden.")
                if source.suffix.lower() in {".py", ".pyw"}:
                    try:
                        ast.parse(source.read_text(encoding="utf-8"), filename=rel.as_posix())
                    except (SyntaxError, UnicodeError, ValueError) as exc:
                        raise AssessmentFailure(
                            "Staged Python syntax failed: %s (%s)" %
                            (rel.as_posix(), type(exc).__name__)) from exc
                    report["static_python_checked"] += 1
                elif source.suffix.lower() == ".json":
                    try:
                        json.loads(source.read_text(encoding="utf-8"))
                    except (ValueError, UnicodeError) as exc:
                        raise AssessmentFailure("Staged JSON invalid: " + rel.as_posix()) from exc
                    report["json_checked"] += 1
            check("static_integrity", "%d Python and %d JSON files parsed, without execution." %
                  (report["static_python_checked"], report["json_checked"]))

            affected = {rel.as_posix(): rel for rel, _ in files}
            affected.update({rel.as_posix(): rel for rel in removed})
            reserve = config_path.stat().st_size
            for rel in affected.values():
                old = self.target / rel
                if old.exists():
                    if not old.is_file() or old.is_symlink():
                        raise AssessmentFailure("Existing update destination is not a normal file.")
                    reserve += old.stat().st_size
            report["estimated_core_backup_bytes"] = reserve

            # Rollback holds only replaced/removed source and config. User
            # memory, models and workspace are never replaced by signed updates.
            free = shutil.disk_usage(self.root).free
            if free < reserve * 2 + MIN_FREE_HEADROOM:
                raise AssessmentFailure("Not enough free disk space for a rollback backup and safe source replacement.")
            check("backup_feasibility",
                  "Core rollback estimated at %d bytes; free space checked." % reserve)
            report["ok"] = True
            report["reason"] = "Signed update assessed. Owner may approve backup and installation."
        except (AssessmentFailure, OSError, KeyError, TypeError, ValueError) as exc:
            report["reason"] = str(exc)[:400]

        if save:
            self.report_dir.mkdir(parents=True, exist_ok=True)
            marker = (report.get("manifest_sha256") or "rejected")[:24]
            receipt = self.report_dir / ("assessment-" + marker + ".json")
            tmp = receipt.with_suffix(".json.tmp")
            tmp.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
            tmp.replace(receipt)
            report["report_path"] = str(receipt)
        return report

    def require(self, stage, expected_manifest_sha256):
        """External install gate. Reruns every check; never trusts saved JSON."""
        if (not isinstance(expected_manifest_sha256, str) or
                not re.fullmatch(r"[0-9a-f]{64}", expected_manifest_sha256)):
            raise AssessmentFailure("Installer requires a valid reviewed assessment digest.")
        result = self.assess(stage, save=False)
        if not result["ok"]:
            raise AssessmentFailure(result["reason"])
        if result["manifest_sha256"] != expected_manifest_sha256:
            raise AssessmentFailure("Signed update changed since the owner assessment.")
        return result
