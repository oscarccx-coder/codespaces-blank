"""Local VoiceStudio speech bridge. No VoiceStudio dependency in Apollo's venv.

VoiceStudio runs in its own environment. Apollo contacts loopback only.
An owner-approved local source checkout may be launched by the separate runtime manager.
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



def list_voices(base_url: str, timeout: int = 8) -> dict:
    """Discover installed VoiceStudio engines, presets, and saved cloned voices."""
    request = urllib.request.Request(_endpoint(base_url, "/v1/audio/voices"),
                                     headers={"Accept": "application/json", "Authorization": "Bearer local"})
    with _open(request, timeout) as response:
        if response.status != 200:
            raise RuntimeError(f"VoiceStudio voices status {response.status}")
        raw = response.read(1024 * 1024 + 1)
    if len(raw) > 1024 * 1024:
        raise ValueError("VoiceStudio voice catalogue exceeds 1 MiB.")
    result = json.loads(raw.decode("utf-8"))
    if not isinstance(result, dict):
        raise ValueError("Invalid VoiceStudio voice catalogue response.")
    voices = result.get("voices", [])
    engines = result.get("engines", [])
    if not isinstance(voices, list) or not isinstance(engines, list):
        raise ValueError("VoiceStudio returned an invalid voice or engine list.")
    return {"ok": True, "voices": voices[:500], "engines": engines[:100]}


def transcribe(base_url: str, path: str | Path, *, language: str = "",
               model: str = "whisper-1", timeout: int = 120) -> str:
    """Send a bounded audio sample to the loopback-only VoiceStudio ASR endpoint."""
    source = Path(path).resolve()
    extensions = {".wav": "audio/wav", ".mp3": "audio/mpeg", ".flac": "audio/flac",
                  ".ogg": "audio/ogg", ".m4a": "audio/mp4"}
    if source.suffix.lower() not in extensions:
        raise ValueError("VoiceStudio only accepts an audio file (WAV, MP3, FLAC, OGG, M4A).")
    if not source.is_file() or source.stat().st_size > 24 * 1024 * 1024:
        raise ValueError("VoiceStudio transcription audio is missing or exceeds 24 MiB.")
    if not 1 <= len(str(model)) <= 100:
        raise ValueError("Invalid VoiceStudio transcription model.")
    boundary = "ApolloVS" + uuid.uuid4().hex
    def field(name: str, value: str) -> bytes:
        return (f"--{boundary}\r\nContent-Disposition: form-data; name=\"{name}\"\r\n"
                f"\r\n{value}\r\n").encode("utf-8")
    body = bytearray()
    body.extend(field("model", str(model)))
    body.extend(field("response_format", "json"))
    if language:
        lang = str(language).lower().split("-")[0]
        if not lang.isascii() or not lang.isalpha() or len(lang) not in {2, 3}:
            raise ValueError("Invalid transcription language.")
        body.extend(field("language", lang))
    body.extend((f"--{boundary}\r\nContent-Disposition: form-data; "
                 f"name=\"file\"; filename=\"speech{source.suffix.lower()}\"\r\n"
                 f"Content-Type: {extensions[source.suffix.lower()]}\r\n\r\n").encode("ascii"))
    body.extend(source.read_bytes())
    body.extend(f"\r\n--{boundary}--\r\n".encode("ascii"))
    request = urllib.request.Request(_endpoint(base_url, "/v1/audio/transcriptions"),
                                     method="POST", data=bytes(body), headers={
        "Content-Type": f"multipart/form-data; boundary={boundary}",
        "Accept": "application/json", "Authorization": "Bearer local",
    })
    with _open(request, timeout) as response:
        if response.status != 200:
            raise RuntimeError(f"VoiceStudio transcription status {response.status}")
        raw = response.read(512 * 1024 + 1)
    if len(raw) > 512 * 1024:
        raise ValueError("VoiceStudio transcription result exceeds 512 KiB.")
    result = json.loads(raw.decode("utf-8"))
    if not isinstance(result, dict) or not isinstance(result.get("text"), str):
        raise RuntimeError("VoiceStudio transcription returned no text.")
    return result["text"]



def create_clone(base_url: str, sample: str | Path, name: str, *,
                 transcript: str = "", language: str = "en",
                 consent_confirmed: bool = False, timeout: int = 150) -> dict:
    """Create a locally stored clone from a user-authorized recording.

    The consumer UI must require separate explicit voice-owner consent. The
    reference clip is never automatically copied into Apollo's Git checkout.
    """
    if not consent_confirmed:
        raise PermissionError("Explicit consent is required to clone this voice.")
    source = Path(sample).resolve()
    extensions = {".wav": "audio/wav", ".mp3": "audio/mpeg", ".flac": "audio/flac",
                  ".ogg": "audio/ogg", ".m4a": "audio/mp4"}
    media_type = extensions.get(source.suffix.lower())
    if not media_type:
        raise ValueError("Choose a WAV, MP3, FLAC, OGG or M4A reference clip.")
    if not source.is_file() or not (1000 <= source.stat().st_size <= 32 * 1024 * 1024):
        raise ValueError("Reference recording must be 1 KiB to 32 MiB.")
    name = " ".join(str(name).split())
    if not 1 <= len(name) <= 80 or any(ord(x) < 32 for x in name):
        raise ValueError("Voice profile name must be 1 to 80 printable characters.")
    if len(transcript) > 4000:
        raise ValueError("Reference transcript is too long.")
    boundary = "ApolloClone" + uuid.uuid4().hex
    def field(field_name: str, value: str) -> bytes:
        return (f"--{boundary}\r\nContent-Disposition: form-data; name=\"{field_name}\"\r\n"
                f"\r\n{value}\r\n").encode("utf-8")
    body = bytearray()
    body.extend(field("name", name))
    body.extend(field("kind", "clone"))
    body.extend(field("ref_text", transcript))
    body.extend(field("language", language))
    body.extend((f"--{boundary}\r\nContent-Disposition: form-data; "
                 f"name=\"ref_audio\"; filename=\"reference{source.suffix.lower()}\"\r\n"
                 f"Content-Type: {media_type}\r\n\r\n").encode("ascii"))
    body.extend(source.read_bytes())
    body.extend(f"\r\n--{boundary}--\r\n".encode("ascii"))
    request = urllib.request.Request(_endpoint(base_url, "/profiles"),
                                     method="POST", data=bytes(body), headers={
        "Content-Type": f"multipart/form-data; boundary={boundary}",
        "Accept": "application/json", "Authorization": "Bearer local",
    })
    with _open(request, timeout) as response:
        if response.status != 200:
            raise RuntimeError(f"VoiceStudio clone status {response.status}")
        raw = response.read(512 * 1024 + 1)
    if len(raw) > 512 * 1024:
        raise ValueError("VoiceStudio clone response too large.")
    result = json.loads(raw.decode("utf-8"))
    if not isinstance(result, dict) or not result.get("id"):
        raise RuntimeError("VoiceStudio did not return the new voice profile ID.")
    return {"ok": True, "id": str(result["id"]), "name": result.get("name", name)}
