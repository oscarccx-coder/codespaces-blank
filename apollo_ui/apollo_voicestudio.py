"""Local VoiceStudio speech bridge. No VoiceStudio dependency in Apollo's venv.

VoiceStudio is a separate owner-launched service. Apollo can reach loopback
only; it never launches third-party Git source or discovers remote services.
"""
from __future__ import annotations

import json
from pathlib import Path
import os
import urllib.error
import urllib.parse
import urllib.request
import uuid
import wave

MAX_WAV_BYTES = 64 * 1024 * 1024
MAX_TEXT = 4096


def _endpoint(base_url: str, route: str) -> str:
    parts = urllib.parse.urlsplit(str(base_url or ""))
    if (parts.scheme != "http" or parts.hostname not in {"localhost", "127.0.0.1", "::1"}
            or parts.username or parts.password or parts.query or parts.fragment
            or parts.path.rstrip("/") not in {"", "/v1"}):
        raise ValueError("VoiceStudio URL must be an HTTP loopback origin (for example http://127.0.0.1:3900).")
    if not parts.port or not (1 <= parts.port <= 65535):
        raise ValueError("VoiceStudio URL must include a port.")
    host = "[" + parts.hostname + "]" if ":" in parts.hostname else parts.hostname
    return f"http://{host}:{parts.port}{route}"


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, request, fp, code, msg, headers, newurl):
        raise ValueError("VoiceStudio requested an unexpected redirect.")


def _open(request, timeout):
    return urllib.request.build_opener(_NoRedirect).open(request, timeout=timeout)


def probe(base_url: str, timeout: int = 4) -> dict:
    request = urllib.request.Request(_endpoint(base_url, "/health"),
                                     headers={"Accept": "application/json"})
    try:
        with _open(request, timeout) as response:
            if response.status != 200:
                raise RuntimeError(f"VoiceStudio health status {response.status}")
            info = json.loads(response.read(8192).decode("utf-8"))
        if not isinstance(info, dict) or info.get("status") != "ok":
            raise RuntimeError("VoiceStudio health response is not ready.")
        return {"ok": True, "status": info.get("status"), "device": info.get("device", ""),
                "version": info.get("version", "")}
    except (urllib.error.URLError, TimeoutError) as exc:
        raise RuntimeError("VoiceStudio is not running on the configured local address.") from exc


def synthesize(base_url: str, text: str, destination: str | Path, *,
               voice: str = "default", model: str = "tts-1",
               timeout: int = 120, cancelled=None) -> dict:
    text = str(text or "").strip()
    if not text or len(text) > MAX_TEXT:
        raise ValueError("VoiceStudio speech must contain 1 to 4096 characters.")
    voice, model = str(voice or "default").strip(), str(model or "tts-1").strip()
    if len(voice) > 200 or len(model) > 100 or not voice or not model:
        raise ValueError("Invalid VoiceStudio voice or model.")
    endpoint = _endpoint(base_url, "/v1/audio/speech")
    destination = Path(destination)
    if destination.suffix.lower() != ".wav":
        raise ValueError("VoiceStudio output must be a WAV file.")
    destination.parent.mkdir(parents=True, exist_ok=True)
    tmp = destination.with_name(destination.name + "." + uuid.uuid4().hex + ".part")
    request = urllib.request.Request(endpoint, data=json.dumps({
        "model": model, "voice": voice, "input": text,
        "response_format": "wav",
    }).encode("utf-8"), method="POST", headers={
        "Content-Type": "application/json", "Accept": "audio/wav",
        "Authorization": "Bearer local",
    })
    try:
        with _open(request, timeout=timeout) as response:
            if response.status != 200:
                raise RuntimeError(f"VoiceStudio returned HTTP {response.status}")
            count = 0
            with tmp.open("wb") as stream:
                while True:
                    if cancelled is not None and cancelled():
                        raise RuntimeError("VoiceStudio speech request cancelled.")
                    chunk = response.read(256 * 1024)
                    if not chunk:
                        break
                    count += len(chunk)
                    if count > MAX_WAV_BYTES:
                        raise ValueError("VoiceStudio audio exceeds the 64 MiB limit.")
                    stream.write(chunk)
        with wave.open(str(tmp), "rb") as audio:
            frames, rate = audio.getnframes(), audio.getframerate()
            if not frames or not rate:
                raise ValueError("VoiceStudio generated an empty WAV.")
            seconds = frames / rate
        if cancelled is not None and cancelled():
            raise RuntimeError("VoiceStudio speech request cancelled.")
        os.replace(tmp, destination)
        return {"ok": True, "saved": True, "engine": "VoiceStudio",
                "file": str(destination), "seconds": seconds, "voice": voice, "model": model}
    finally:
        tmp.unlink(missing_ok=True)
