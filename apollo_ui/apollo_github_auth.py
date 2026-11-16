"""Owner-only GitHub PAT onboarding through Windows Git Credential Manager.

Never persist a token in an Apollo file, Git remote URL, command argument,
environment variable, log, repository or model-visible tool response.
Public Apollo read-only updates do not require any token.
"""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
from urllib.error import HTTPError, URLError
from urllib.request import Request, build_opener, HTTPRedirectHandler

_API = "https://api.github.com/user"
_NAME = re.compile(r"^[A-Za-z0-9](?:[A-Za-z0-9-]{0,37}[A-Za-z0-9])?$")


class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, request, fp, code, msg, headers, newurl):
        return None


def vault_ready() -> dict:
    """Non-secret check; never asks a credential helper to reveal a token."""
    if sys.platform != "win32":
        return {"ready": False, "reason": "GitHub token setup requires Windows Credential Manager."}
    if not shutil.which("git"):
        return {"ready": False, "reason": "Git for Windows is missing."}
    try:
        result = subprocess.run(["git", "credential-manager", "--version"],
                                stdin=subprocess.DEVNULL, capture_output=True,
                                check=False, timeout=8)
    except (OSError, subprocess.TimeoutExpired):
        return {"ready": False, "reason": "Git Credential Manager is not available."}
    if result.returncode:
        return {"ready": False, "reason": "Update Git for Windows to include Git Credential Manager."}
    return {"ready": True, "storage": "Windows Credential Manager",
            "note": "No GitHub token is needed to download Apollo's public repository."}


def verify_token(token: str) -> str:
    """Verify an owner-pasted GitHub PAT without reflecting it in errors."""
    if not isinstance(token, str) or not (12 <= len(token) <= 1024):
        raise ValueError("Enter a GitHub personal access token.")
    if token != token.strip() or any(c.isspace() or ord(c) < 33 for c in token):
        raise ValueError("Token contains whitespace or control characters.")
    request = Request(_API,
                      headers={"Authorization": "Bearer " + token,
                               "Accept": "application/vnd.github+json",
                               "User-Agent": "Apollo-Windows-Connect",
                               "X-GitHub-Api-Version": "2022-11-28"})
    try:
        with build_opener(_NoRedirect).open(request, timeout=12) as response:
            if response.status != 200:
                raise ValueError("GitHub did not accept this token.")
            payload = response.read(65537)
            if len(payload) > 65536:
                raise ValueError("GitHub identity response is too large.")
        account = json.loads(payload.decode("utf-8")).get("login", "")
    except HTTPError as exc:
        if exc.code == 401:
            raise ValueError("GitHub rejected the token. Check expiration and access.") from None
        if exc.code == 403:
            raise ValueError("GitHub refused the request. Check access/rate limits.") from None
        raise ValueError("GitHub identity check failed (HTTP status %d)." % exc.code) from None
    except (URLError, TimeoutError, OSError):
        raise RuntimeError("Could not securely reach api.github.com; check internet access.") from None
    except (UnicodeError, json.JSONDecodeError, AttributeError):
        raise ValueError("GitHub returned an invalid account response.") from None
    if not isinstance(account, str) or not _NAME.fullmatch(account):
        raise ValueError("GitHub identity response had no valid account name.")
    return account


def connect_token(token: str) -> dict:
    """Store verified token via the encrypted Windows vault, owner UI only."""
    status = vault_ready()
    if not status["ready"]:
        raise RuntimeError(status["reason"])
    account = verify_token(token)
    # GCM store accepts a password via stdin. Never put it in argv or Git config.
    payload = ("protocol=https\nhost=github.com\nusername=" + account
               + "\npassword=" + token + "\n\n")
    env = os.environ.copy()
    for key in list(env):
        if key.upper().startswith(("GIT_TRACE", "GCM_TRACE")) or key.upper() in {
            "GIT_CURL_VERBOSE", "GIT_TRACE_CURL", "GIT_TRACE_PACKET",
        }:
            env.pop(key, None)
    env["GCM_CREDENTIAL_STORE"] = "wincredman"
    env["GCM_INTERACTIVE"] = "never"
    try:
        result = subprocess.run(["git", "credential-manager", "store"],
                                input=payload, text=True, capture_output=True,
                                check=False, timeout=18, env=env)
    except (OSError, subprocess.TimeoutExpired):
        raise RuntimeError("Windows Credential Manager could not store the token.") from None
    finally:
        # The UI also clears the masked input field immediately on completion.
        payload = None
    if result.returncode:
        raise RuntimeError("Git Credential Manager refused to save the token. No Apollo config was changed.")
    return {"ok": True, "account": account, "credential_store": "Windows Credential Manager",
            "token": "never returned", "note": "Git can reuse this credential for authorized HTTPS requests."}
