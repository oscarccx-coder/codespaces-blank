"""Raspberry Pi signed GitHub update control, no Qt or Windows process launch.

By default this only checks. Applying files requires the systemd unit to be
stopped by pi/update_pi.sh, and an independently verified pinned signing key.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import socket
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from apollo_update import UpdateService
from apollo_updater import apply_update


def import_key(service, key_path, expected_sha256):
    expected = str(expected_sha256 or "").strip().lower()
    if not re.fullmatch(r"[0-9a-f]{64}", expected):
        raise ValueError("Supply the trusted 64-digit Ed25519 public-key SHA-256 fingerprint")
    key = Path(key_path).resolve()
    data = key.read_bytes()
    actual = hashlib.sha256(data).hexdigest()
    if actual != expected:
        raise ValueError("Signing public key fingerprint does not match independent expectation")
    result = service.import_trusted_key(key)
    if os.name != "nt":
        service.public_key_path.chmod(0o600)
    return {"trusted": True, "fingerprint": actual, **result}


def can_apply_update():
    if os.getenv("APOLLO_PI_OFFLINE_UPDATE") != "1":
        return False, "Use bash pi/update_pi.sh to stop and restart the service safely"
    # Refuse a manual update if the server is still running on its normal port.
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        probe.settimeout(0.25)
        if probe.connect_ex(("127.0.0.1", 8766)) == 0:
            return False, "Apollo Pi HTTP service is still running; stop it before updating"
    return True, ""


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--check", action="store_true")
    group.add_argument("--apply", action="store_true")
    group.add_argument("--trust-key", metavar="PEM")
    group.add_argument("--status", action="store_true")
    parser.add_argument("--fingerprint", default="")
    parser.add_argument("--channel", choices=["stable", "beta"], default=None)
    args = parser.parse_args(argv)

    service = UpdateService(ROOT)
    if args.trust_key:
        print(json.dumps(import_key(service, args.trust_key, args.fingerprint), indent=2))
        return 0
    if args.channel:
        service.configure(source="github", channel=args.channel)
    if args.status:
        print(json.dumps(service.status(), indent=2))
        return 0
    if args.apply:
        allowed, reason = can_apply_update()
        if not allowed:
            print(json.dumps({"ok": False, "error": reason}), file=sys.stderr)
            return 2
        if not service.public_key_path.is_file():
            print("No trusted release public key installed. Import and independently verify it first.", file=sys.stderr)
            return 2

    result = service.check_for_updates()
    if args.check or not result.get("ok") or not result.get("available"):
        print(json.dumps(result, indent=2))
        return 0 if result.get("ok") else 1
    stage = service.stage_update()
    if not stage.get("ok"):
        print(json.dumps(stage, indent=2), file=sys.stderr)
        return 1
    # NO GUI restart. The calling shell handles the systemd user service.
    applied = apply_update(ROOT, stage["stage_dir"], restart=False)
    print(json.dumps(applied, indent=2))
    return 0 if applied.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
