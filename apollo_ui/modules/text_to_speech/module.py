import html
import json
import os
import re
import subprocess
import sys
import threading
import time
import uuid
import wave
from pathlib import Path


_SAFE_FILENAME = re.compile(r"^[A-Za-z0-9_. -]+$")

EMOTION_PRESETS = {
    "neutral": {
        "pitch": 0,
        "rate_percent": 0,
        "volume_delta": 0,
        "label": "Neutral",
    },
    "warm": {
        "pitch": -1,
        "rate_percent": -6,
        "volume_delta": -4,
        "label": "Warm",
    },
    "calm": {
        "pitch": -2,
        "rate_percent": -16,
        "volume_delta": -10,
        "label": "Calm",
    },
    "confident": {
        "pitch": -2,
        "rate_percent": 5,
        "volume_delta": 0,
        "label": "Confident",
    },
    "friendly": {
        "pitch": 1,
        "rate_percent": 8,
        "volume_delta": -3,
        "label": "Friendly",
    },
    "excited": {
        "pitch": 3,
        "rate_percent": 22,
        "volume_delta": 0,
        "label": "Excited",
    },
    "serious": {
        "pitch": -3,
        "rate_percent": -10,
        "volume_delta": -5,
        "label": "Serious",
    },
    "sad": {
        "pitch": -3,
        "rate_percent": -22,
        "volume_delta": -18,
        "label": "Sad",
    },
    "angry": {
        "pitch": -1,
        "rate_percent": 20,
        "volume_delta": 0,
        "label": "Angry / Intense",
    },
    "dramatic": {
        "pitch": -2,
        "rate_percent": -5,
        "volume_delta": 0,
        "label": "Dramatic",
    },
    "robotic": {
        "pitch": -4,
        "rate_percent": -6,
        "volume_delta": -8,
        "label": "Robotic",
    },
}


ACCENT_LABELS = {
    "en-GB": "British English (UK)",
    "en-US": "American English (US)",
    "en-AU": "Australian English",
    "en-CA": "Canadian English",
    "en-IE": "Irish English",
    "en-IN": "Indian English",
    "en-NZ": "New Zealand English",
    "en-ZA": "South African English",
}

ACCENT_ALIASES = {
    "": "",
    "auto": "",
    "automatic": "",
    "system": "",
    "default": "",
    "british": "en-GB",
    "uk": "en-GB",
    "english uk": "en-GB",
    "british english": "en-GB",
    "american": "en-US",
    "us": "en-US",
    "usa": "en-US",
    "american english": "en-US",
    "australian": "en-AU",
    "australian english": "en-AU",
    "canadian": "en-CA",
    "canadian english": "en-CA",
    "irish": "en-IE",
    "irish english": "en-IE",
    "indian": "en-IN",
    "indian english": "en-IN",
    "new zealand": "en-NZ",
    "new zealand english": "en-NZ",
    "south african": "en-ZA",
    "south african english": "en-ZA",
}


DEFAULT_PROFILE = {
    "voice": "",
    "gender": "any",
    "accent": "",
    "emotion": "neutral",
    "delivery": "natural",
    "depth": 0,
    "pitch": 0,
    "rate": 0,
    "volume": 100,
    "save_dictation": True,
    "skip_code": True,
}


class Module:
    def __init__(self, context=None):
        context = context or {}
        self.base_dir = Path(context.get("base_dir", ".")).resolve()
        self.validation = bool(context.get("validation", False))
        self.runtime = context.get("runtime")
        self.storage_dir = (self.base_dir / "storage").resolve()
        self.output_dir = (self.storage_dir / "media" / "tts" / "audio").resolve()
        self.profile_path = (self.storage_dir / "state" / "speech_voice_profile.json").resolve()
        self.voice_dataset_dir = (self.storage_dir / "training" / "voice_dataset").resolve()
        self.voice_recordings_dir = (self.voice_dataset_dir / "recordings").resolve()
        self.voice_manifest_path = (self.voice_dataset_dir / "manifest.jsonl").resolve()
        self._lock = threading.RLock()
        self._speech_process = None
        self._imprint_worker_lock = threading.RLock()
        self._imprint_worker_thread = None
        self._imprint_pending = None
        self._imprint_last_error = ""
        self._imprint_generation = 0
        self._imprint_status = {"state": "idle", "job_id": None, "updated_at": time.time()}
        self._imprint_active_cache = (0, False)
        self.profile = self._load_profile()

    def tools(self):
        return [
            {
                "name": "speak_text",
                "description": (
                    "Speak Apollo text aloud asynchronously using the saved Voice Studio "
                    "profile. Optional arguments can temporarily override voice, gender, "
                    "accent, emotion, depth, pitch, rate or volume."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "text": {"type": "string"},
                        "voice": {"type": "string"},
                        "gender": {
                            "type": "string",
                            "enum": ["any", "male", "female"],
                        },
                        "accent": {
                            "type": "string",
                            "description": (
                                "Preferred installed Windows voice culture/accent, "
                                "for example en-GB, en-US or en-AU. Common names "
                                "such as British or American are also accepted."
                            ),
                        },
                        "emotion": {
                            "type": "string",
                            "enum": list(EMOTION_PRESETS.keys()),
                        },
                        "depth": {
                            "type": "integer",
                            "minimum": -100,
                            "maximum": 100,
                        },
                        "pitch": {
                            "type": "integer",
                            "minimum": -12,
                            "maximum": 12,
                        },
                        "rate": {
                            "type": "integer",
                            "minimum": -10,
                            "maximum": 10,
                        },
                        "volume": {
                            "type": "integer",
                            "minimum": 0,
                            "maximum": 100,
                        },
                    },
                    "required": ["text"],
                },
            },
            {
                "name": "stop_speaking",
                "description": "Immediately stop the speech process started by Apollo.",
                "parameters": {"type": "object", "properties": {}},
            },
            {
                "name": "speech_status",
                "description": "Inspect the current speech job and last voice error.",
                "parameters": {"type": "object", "properties": {}},
            },
            {
                "name": "save_wav",
                "description": (
                    "Render text to a local WAV using the saved or temporarily "
                    "overridden Voice Studio profile."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "text": {"type": "string"},
                        "filename": {"type": "string"},
                        "voice": {"type": "string"},
                        "gender": {
                            "type": "string",
                            "enum": ["any", "male", "female"],
                        },
                        "accent": {
                            "type": "string",
                            "description": (
                                "Preferred installed Windows voice culture/accent, "
                                "for example en-GB, en-US or en-AU. Common names "
                                "such as British or American are also accepted."
                            ),
                        },
                        "emotion": {
                            "type": "string",
                            "enum": list(EMOTION_PRESETS.keys()),
                        },
                        "depth": {
                            "type": "integer",
                            "minimum": -100,
                            "maximum": 100,
                        },
                        "pitch": {
                            "type": "integer",
                            "minimum": -12,
                            "maximum": 12,
                        },
                        "rate": {
                            "type": "integer",
                            "minimum": -10,
                            "maximum": 10,
                        },
                        "volume": {
                            "type": "integer",
                            "minimum": 0,
                            "maximum": 100,
                        },
                    },
                    "required": ["text"],
                },
            },
            {
                "name": "list_voices",
                "description": "List installed Windows text-to-speech voice names.",
                "parameters": {"type": "object", "properties": {}},
            },
            {
                "name": "list_voice_profiles",
                "description": (
                    "List installed Windows voices with gender, age and culture metadata."
                ),
                "parameters": {"type": "object", "properties": {}},
            },
            {
                "name": "get_voice_profile",
                "description": "Get Apollo's saved Voice Studio profile.",
                "parameters": {"type": "object", "properties": {}},
            },
            {
                "name": "set_voice_profile",
                "description": (
                    "Persist Apollo's default voice modulation profile for future replies."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "voice": {"type": "string"},
                        "gender": {
                            "type": "string",
                            "enum": ["any", "male", "female"],
                        },
                        "accent": {
                            "type": "string",
                            "description": (
                                "Preferred installed Windows voice culture/accent, "
                                "for example en-GB, en-US or en-AU. Common names "
                                "such as British or American are also accepted."
                            ),
                        },
                        "emotion": {
                            "type": "string",
                            "enum": list(EMOTION_PRESETS.keys()),
                        },
                        "depth": {
                            "type": "integer",
                            "minimum": -100,
                            "maximum": 100,
                        },
                        "pitch": {
                            "type": "integer",
                            "minimum": -12,
                            "maximum": 12,
                        },
                        "rate": {
                            "type": "integer",
                            "minimum": -10,
                            "maximum": 10,
                        },
                        "volume": {
                            "type": "integer",
                            "minimum": 0,
                            "maximum": 100,
                        },
                    },
                },
            },
            {
                "name": "reset_voice_profile",
                "description": "Reset Voice Studio to the neutral defaults.",
                "parameters": {"type": "object", "properties": {}},
            },
            {
                "name": "preview_voice",
                "description": (
                    "Preview text using a temporary voice profile without changing the "
                    "saved profile."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "text": {"type": "string"},
                        "voice": {"type": "string"},
                        "gender": {
                            "type": "string",
                            "enum": ["any", "male", "female"],
                        },
                        "accent": {
                            "type": "string",
                            "description": (
                                "Preferred installed Windows voice culture/accent, "
                                "for example en-GB, en-US or en-AU. Common names "
                                "such as British or American are also accepted."
                            ),
                        },
                        "emotion": {
                            "type": "string",
                            "enum": list(EMOTION_PRESETS.keys()),
                        },
                        "depth": {
                            "type": "integer",
                            "minimum": -100,
                            "maximum": 100,
                        },
                        "pitch": {
                            "type": "integer",
                            "minimum": -12,
                            "maximum": 12,
                        },
                        "rate": {
                            "type": "integer",
                            "minimum": -10,
                            "maximum": 10,
                        },
                        "volume": {
                            "type": "integer",
                            "minimum": 0,
                            "maximum": 100,
                        },
                    },
                    "required": ["text"],
                },
            },
            {
                "name": "record_dictation",
                "description": (
                    "Record one microphone utterance, transcribe it offline with Windows speech recognition, "
                    "and when Voice Studio saving is enabled keep the WAV + transcript as future TinyVoice training data."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "timeout_seconds": {"type": "integer", "minimum": 3, "maximum": 30},
                        "culture": {"type": "string"}
                    }
                },
            },
            {
                "name": "voice_dataset_stats",
                "description": "Return saved dictation recording count, approved count and total recorded seconds.",
                "parameters": {"type": "object", "properties": {}}
            },
            {
                "name": "list_voice_dataset",
                "description": "List saved voice-training samples and transcripts.",
                "parameters": {"type": "object", "properties": {"limit": {"type": "integer"}}}
            },
            {
                "name": "set_voice_sample_quality",
                "description": "Mark a saved voice sample good/bad and approve/unapprove it for future voice training.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "id": {"type": "string"},
                        "quality": {"type": "string", "enum": ["good", "bad", "unrated"]},
                        "approved_for_training": {"type": "boolean"}
                    },
                    "required": ["id"]
                }
            },
            {
                "name": "delete_voice_sample",
                "description": "Delete one saved dictation WAV and its manifest record.",
                "parameters": {"type": "object", "properties": {"id": {"type": "string"}}, "required": ["id"]}
            },
            {
                "name": "listen_once",
                "description": (
                    "Listen to the default microphone once and return offline Windows "
                    "speech-recognition text. Intended for Apollo's Dictate button."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "timeout_seconds": {
                            "type": "integer",
                            "minimum": 3,
                            "maximum": 30,
                        },
                        "culture": {
                            "type": "string",
                            "description": "Optional recognizer culture such as en-GB.",
                        },
                    },
                },
            },
            {
                "name": "list_recognizers",
                "description": "List installed Windows offline speech recognizers.",
                "parameters": {"type": "object", "properties": {}},
            },
        ]

    @staticmethod
    def _bounded_int(value, low, high, default):
        try:
            value = int(value)
        except (TypeError, ValueError):
            value = default
        return max(low, min(high, value))

    @staticmethod
    def _clean_gender(value):
        value = str(value or "any").strip().lower()
        return value if value in {"any", "male", "female"} else "any"

    @staticmethod
    def _clean_accent(value):
        raw = str(value or "").strip()
        key = raw.lower()

        if key in ACCENT_ALIASES:
            return ACCENT_ALIASES[key]

        # Accept normal BCP-47-style language/culture tags such as en-GB.
        match = re.fullmatch(
            r"([A-Za-z]{2,3})(?:[-_]([A-Za-z]{2,4}))?",
            raw,
        )

        if not match:
            return ""

        language = match.group(1).lower()
        region = match.group(2)

        if not region:
            return language

        return (
            language
            + "-"
            + (
                region.upper()
                if len(region) == 2
                else region.title()
            )
        )

    @staticmethod
    def _clean_emotion(value):
        value = str(value or "neutral").strip().lower()
        return value if value in EMOTION_PRESETS else "neutral"

    @staticmethod
    def _text(arguments):
        text = str((arguments or {}).get("text", "") or "").strip()
        if not text:
            raise ValueError("Text is required.")
        if len(text) > 12000:
            raise ValueError("Text is too long. Maximum is 12000 characters per call.")
        return text

    def _normalise_profile(self, source=None):
        source = source if isinstance(source, dict) else {}
        return {
            "voice": str(source.get("voice", "") or "").strip(),
            "gender": self._clean_gender(source.get("gender", "any")),
            "accent": self._clean_accent(source.get("accent", "")),
            "emotion": self._clean_emotion(source.get("emotion", "neutral")),
            "delivery": str(source.get("delivery", "natural") or "natural").strip().lower()
                if str(source.get("delivery", "natural") or "natural").strip().lower() in {"precise", "natural", "expressive"}
                else "natural",
            "depth": self._bounded_int(source.get("depth", 0), -100, 100, 0),
            "pitch": self._bounded_int(source.get("pitch", 0), -12, 12, 0),
            "rate": self._bounded_int(source.get("rate", 0), -10, 10, 0),
            "volume": self._bounded_int(source.get("volume", 100), 0, 100, 100),
            "save_dictation": bool(source.get("save_dictation", True)),
            "skip_code": bool(source.get("skip_code", True)),
        }

    def _load_profile(self):
        if not self.profile_path.exists():
            return dict(DEFAULT_PROFILE)
        try:
            raw = json.loads(self.profile_path.read_text(encoding="utf-8"))
            return self._normalise_profile(raw)
        except Exception:
            return dict(DEFAULT_PROFILE)

    def _save_profile(self, profile):
        profile = self._normalise_profile(profile)
        self.profile = profile

        if not self.validation:
            self.storage_dir.mkdir(parents=True, exist_ok=True)
            temp = self.profile_path.with_suffix(".json.tmp")
            temp.write_text(
                json.dumps(profile, indent=2, ensure_ascii=False) + "\n",
                encoding="utf-8",
            )
            temp.replace(self.profile_path)

        return profile

    def _merged_profile(self, overrides=None):
        merged = dict(self.profile)
        overrides = overrides if isinstance(overrides, dict) else {}

        for key in DEFAULT_PROFILE:
            if key in overrides and overrides.get(key) is not None:
                merged[key] = overrides.get(key)

        return self._normalise_profile(merged)

    def _resolved_modulation(self, profile):
        profile = self._normalise_profile(profile)
        preset = EMOTION_PRESETS[profile["emotion"]]

        # "Depth" is a synthetic tonal-body control:
        # positive = deeper/slower, negative = lighter/brighter.
        depth_pitch = round(-profile["depth"] * 0.06)
        depth_rate = round(-profile["depth"] * 0.05)

        pitch = self._bounded_int(
            profile["pitch"] + preset["pitch"] + depth_pitch,
            -12,
            12,
            0,
        )
        rate_percent = self._bounded_int(
            (profile["rate"] * 5)
            + preset["rate_percent"]
            + depth_rate,
            -50,
            80,
            0,
        )
        volume = self._bounded_int(
            profile["volume"] + preset["volume_delta"],
            0,
            100,
            100,
        )

        return {
            **profile,
            "resolved_pitch_semitones": pitch,
            "resolved_rate_percent": rate_percent,
            "resolved_volume": volume,
            "emotion_label": preset["label"],
        }

    @staticmethod
    def _require_windows():
        if sys.platform != "win32":
            raise RuntimeError(
                "Speech I/O uses Windows System.Speech and can only run on Windows."
            )

    @staticmethod
    def _creationflags():
        return getattr(subprocess, "CREATE_NO_WINDOW", 0)

    def _run_powershell(self, script, extra_env=None, timeout=120):
        self._require_windows()
        env = dict(os.environ)
        if extra_env:
            env.update({str(k): str(v) for k, v in extra_env.items()})
        proc = subprocess.run(
            [
                "powershell.exe",
                "-NoProfile",
                "-NonInteractive",
                "-ExecutionPolicy",
                "Bypass",
                "-Command",
                script,
            ],
            capture_output=True,
            text=True,
            timeout=timeout,
            env=env,
            creationflags=self._creationflags(),
        )
        if proc.returncode != 0:
            detail = (proc.stderr or proc.stdout or "Unknown PowerShell error").strip()
            raise RuntimeError(detail[-4000:])
        return (proc.stdout or "").strip()

    def _start_powershell(self, script, extra_env=None):
        self._require_windows()
        env = dict(os.environ)
        if extra_env:
            env.update({str(k): str(v) for k, v in extra_env.items()})
        return subprocess.Popen(
            [
                "powershell.exe",
                "-NoProfile",
                "-NonInteractive",
                "-ExecutionPolicy",
                "Bypass",
                "-Command",
                script,
            ],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            env=env,
            creationflags=self._creationflags(),
        )

    @staticmethod
    def _conversationalise(text):
        replacements = [
            (r"\bI am\b", "I'm"), (r"\bI will\b", "I'll"), (r"\bI have\b", "I've"),
            (r"\byou are\b", "you're"), (r"\byou will\b", "you'll"), (r"\bwe are\b", "we're"),
            (r"\bwe will\b", "we'll"), (r"\bit is\b", "it's"), (r"\bthat is\b", "that's"),
            (r"\bthere is\b", "there's"), (r"\bdo not\b", "don't"), (r"\bdoes not\b", "doesn't"),
            (r"\bdid not\b", "didn't"), (r"\bcannot\b", "can't"), (r"\bwill not\b", "won't"),
            (r"\bshould not\b", "shouldn't"), (r"\bwould not\b", "wouldn't"),
        ]
        for pattern, repl in replacements:
            text = re.sub(pattern, repl, text, flags=re.I)
        return text

    def _speech_friendly_text(self, text, profile):
        text = str(text or "")
        delivery = profile.get("delivery", "natural")
        skip_code = bool(profile.get("skip_code", True))
        if delivery == "precise":
            return re.sub(r"\s+", " ", text).strip()

        if skip_code:
            text = re.sub(
                r"```(?:[^\n`]*)\n?.*?```",
                " I've put the code below. [[APOLLO_BREAK]] ",
                text,
                flags=re.S,
            )
        else:
            text = text.replace("```", " ")

        text = re.sub(r"\[([^\]]+)\]\([^\)]+\)", r"\1", text)
        text = re.sub(r"https?://\S+", "the link shown on screen", text)
        text = re.sub(r"`([^`]+)`", r"\1", text)
        text = re.sub(r"^\s{0,3}#{1,6}\s*", "", text, flags=re.M)
        text = re.sub(r"^\s*[-*+]\s+", "", text, flags=re.M)
        text = re.sub(r"^\s*\d+[.)]\s+", "", text, flags=re.M)
        text = re.sub(r"[*_>]", "", text)
        text = text.replace("°C", " degrees Celsius").replace("°F", " degrees Fahrenheit")
        text = self._conversationalise(text)

        # Preserve sentence/paragraph rhythm instead of collapsing everything into one metronomic line.
        text = re.sub(r"\n\s*\n+", " [[APOLLO_LONG_BREAK]] ", text)
        text = re.sub(r"\n+", " [[APOLLO_BREAK]] ", text)
        text = re.sub(r"(?<=[.!?])\s+(?=[A-Z0-9])", " [[APOLLO_BREAK]] ", text)
        text = re.sub(r"\s+", " ", text).strip()
        return text

    @staticmethod
    def _detect_emotion(text):
        lower = str(text or "").lower()
        if any(x in lower for x in ("warning", "danger", "critical", "do not", "don't do")):
            return "serious"
        if "!" in str(text) and any(x in lower for x in ("great", "yes", "done", "working", "success")):
            return "excited"
        if any(x in lower for x in ("sorry", "unfortunately", "failed", "sad")):
            return "calm"
        if "?" in str(text):
            return "friendly"
        return "neutral"

    def _dataset_records(self):
        if not self.voice_manifest_path.exists():
            return []
        records = []
        for line in self.voice_manifest_path.read_text(encoding="utf-8", errors="replace").splitlines():
            try:
                item = json.loads(line)
                if isinstance(item, dict): records.append(item)
            except Exception:
                continue
        return records

    def _write_dataset_records(self, records):
        self.voice_dataset_dir.mkdir(parents=True, exist_ok=True)
        temp = self.voice_manifest_path.with_suffix('.jsonl.tmp')
        temp.write_text("".join(json.dumps(x, ensure_ascii=False) + "\n" for x in records), encoding="utf-8")
        temp.replace(self.voice_manifest_path)

    def _append_dataset_record(self, record):
        with self._lock:
            records = self._dataset_records()
            records.append(record)
            self._write_dataset_records(records)

    def _record_microphone(self, target, timeout_seconds):
        try:
            import numpy as np
            import sounddevice as sd
        except Exception as exc:
            raise RuntimeError(
                "Microphone recording needs the sounddevice and numpy packages. "
                "Run install.bat again after applying this patch."
            ) from exc

        samplerate = 16000
        blocksize = 800
        threshold = 420.0
        max_initial_silence = min(4.0, float(timeout_seconds))
        trailing_silence = 1.15
        chunks = []
        start = time.monotonic()
        last_voice = None
        speech_started = False

        with sd.InputStream(samplerate=samplerate, channels=1, dtype='int16', blocksize=blocksize) as stream:
            while time.monotonic() - start < timeout_seconds:
                data, _overflowed = stream.read(blocksize)
                mono = data[:, 0].copy()
                chunks.append(mono)
                rms = float(np.sqrt(np.mean(mono.astype(np.float64) ** 2))) if len(mono) else 0.0
                now = time.monotonic()
                if rms >= threshold:
                    speech_started = True
                    last_voice = now
                elif speech_started and last_voice is not None and now - last_voice >= trailing_silence:
                    break
                elif not speech_started and now - start >= max_initial_silence:
                    break

        if not chunks:
            raise RuntimeError('No microphone audio was captured.')
        audio = np.concatenate(chunks).astype('<i2', copy=False)
        target.parent.mkdir(parents=True, exist_ok=True)
        with wave.open(str(target), 'wb') as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(samplerate)
            wf.writeframes(audio.tobytes())
        duration = len(audio) / float(samplerate)
        return duration

    def _recognize_wave_file(self, wav_path, timeout_seconds=30, culture=""):
        env = {
            "APOLLO_STT_WAV": str(wav_path),
            "APOLLO_STT_CULTURE": str(culture or ""),
        }
        script = (
            "Add-Type -AssemblyName System.Speech; "
            "$infos = @([System.Speech.Recognition.SpeechRecognitionEngine]::InstalledRecognizers()); "
            "if ($infos.Count -eq 0) { throw 'No Windows speech recognizer is installed.' }; "
            "$wanted = $env:APOLLO_STT_CULTURE; $info = $null; "
            "if ($wanted) { $info = $infos | Where-Object { $_.Culture.Name -eq $wanted } | Select-Object -First 1 }; "
            "if ($null -eq $info) { $ui = [System.Globalization.CultureInfo]::CurrentUICulture.Name; "
            "$info = $infos | Where-Object { $_.Culture.Name -eq $ui } | Select-Object -First 1 }; "
            "if ($null -eq $info) { $info = $infos | Select-Object -First 1 }; "
            "$r = New-Object System.Speech.Recognition.SpeechRecognitionEngine($info); "
            "$g = New-Object System.Speech.Recognition.DictationGrammar; $r.LoadGrammar($g); "
            "$r.SetInputToWaveFile($env:APOLLO_STT_WAV); $result = $r.Recognize(); "
            "if ($null -ne $result) { Write-Output $result.Text }; $r.Dispose();"
        )
        return self._run_powershell(script, env, timeout=max(30, int(timeout_seconds) + 15)).strip()

    @staticmethod
    def _speech_script(body):
        return (
            "Add-Type -AssemblyName System.Speech; "
            "$s = New-Object System.Speech.Synthesis.SpeechSynthesizer; "
            "$voice = $env:APOLLO_TTS_VOICE; "
            "$gender = $env:APOLLO_TTS_GENDER; "
            "$accent = $env:APOLLO_TTS_ACCENT; "
            "if ($voice) { "
            "  $names = @($s.GetInstalledVoices() | ForEach-Object { $_.VoiceInfo.Name }); "
            "  if ($names -notcontains $voice) { throw ('Voice not installed: ' + $voice) }; "
            "  $s.SelectVoice($voice); "
            "} elseif ($accent) { "
            "  $accentVoices = @($s.GetInstalledVoices() | Where-Object { "
            "    $_.Enabled -and $_.VoiceInfo.Culture.Name -eq $accent "
            "  }); "
            "  $match = $null; "
            "  if ($gender -and $gender -ne 'any') { "
            "    $match = $accentVoices | Where-Object { "
            "      $_.VoiceInfo.Gender.ToString().ToLower() -eq $gender "
            "    } | Select-Object -First 1; "
            "  }; "
            "  if ($null -eq $match) { $match = $accentVoices | Select-Object -First 1 }; "
            "  if ($null -ne $match) { "
            "    $s.SelectVoice($match.VoiceInfo.Name); "
            "  } elseif ($gender -and $gender -ne 'any') { "
            "    $fallback = $s.GetInstalledVoices() | Where-Object { "
            "      $_.Enabled -and $_.VoiceInfo.Gender.ToString().ToLower() -eq $gender "
            "    } | Select-Object -First 1; "
            "    if ($null -ne $fallback) { $s.SelectVoice($fallback.VoiceInfo.Name) }; "
            "  }; "
            "} elseif ($gender -and $gender -ne 'any') { "
            "  $match = $s.GetInstalledVoices() | Where-Object { "
            "    $_.Enabled -and $_.VoiceInfo.Gender.ToString().ToLower() -eq $gender "
            "  } | Select-Object -First 1; "
            "  if ($null -ne $match) { $s.SelectVoice($match.VoiceInfo.Name) }; "
            "} "
            "$selectedCulture = $s.Voice.Culture.Name; "
            "$escaped = [System.Security.SecurityElement]::Escape($env:APOLLO_TTS_TEXT); "
            "$escaped = $escaped.Replace('[[APOLLO_LONG_BREAK]]', \"<break time='520ms'/>\"); "
            "$escaped = $escaped.Replace('[[APOLLO_BREAK]]', \"<break time='230ms'/>\"); "
            "$pitch = [int]$env:APOLLO_TTS_PITCH; "
            "$rate = [int]$env:APOLLO_TTS_RATE_PERCENT; "
            "$volume = [int]$env:APOLLO_TTS_VOLUME; "
            "$pitchText = if ($pitch -ge 0) { '+' + $pitch + 'st' } else { $pitch + 'st' }; "
            "$rateText = if ($rate -ge 0) { '+' + $rate + '%' } else { $rate + '%' }; "
            "$ssml = \"<speak version='1.0' xmlns='http://www.w3.org/2001/10/synthesis' "
            "xml:lang='$selectedCulture'><prosody pitch='$pitchText' rate='$rateText' "
            "volume='$volume'>$escaped</prosody></speak>\"; "
            + body
            + " $s.Dispose();"
        )

    def _speech_env(self, arguments, text):
        profile = self._merged_profile(arguments)
        rendered = self._speech_friendly_text(text, profile)
        if profile.get("delivery") == "expressive" and profile.get("emotion") == "neutral":
            profile["emotion"] = self._detect_emotion(rendered)
        resolved = self._resolved_modulation(profile)
        return resolved, {
            "APOLLO_TTS_TEXT": rendered,
            "APOLLO_TTS_VOICE": resolved["voice"],
            "APOLLO_TTS_GENDER": resolved["gender"],
            "APOLLO_TTS_ACCENT": resolved["accent"],
            "APOLLO_TTS_PITCH": str(resolved["resolved_pitch_semitones"]),
            "APOLLO_TTS_RATE_PERCENT": str(resolved["resolved_rate_percent"]),
            "APOLLO_TTS_VOLUME": str(resolved["resolved_volume"]),
        }

    def _stop_process(self):
        with self._lock:
            proc = self._speech_process
            self._speech_process = None
        if proc is None:
            return False
        try:
            if proc.poll() is None:
                proc.terminate()
                try:
                    proc.wait(timeout=1.0)
                except Exception:
                    proc.kill()
            return True
        except Exception:
            return False

    def _voice_metadata(self):
        script = (
            "Add-Type -AssemblyName System.Speech; "
            "$s = New-Object System.Speech.Synthesis.SpeechSynthesizer; "
            "$items = @($s.GetInstalledVoices() | Where-Object { $_.Enabled } | "
            "ForEach-Object { [pscustomobject]@{ "
            "name=$_.VoiceInfo.Name; "
            "gender=$_.VoiceInfo.Gender.ToString(); "
            "age=$_.VoiceInfo.Age.ToString(); "
            "culture=$_.VoiceInfo.Culture.Name; "
            "description=$_.VoiceInfo.Description "
            "} }); "
            "$items | ConvertTo-Json -Compress; "
            "$s.Dispose();"
        )
        output = self._run_powershell(script, timeout=30)
        if not output:
            return []
        data = json.loads(output)
        if isinstance(data, dict):
            data = [data]
        return [
            {
                "name": str(item.get("name", "") or ""),
                "gender": str(item.get("gender", "") or ""),
                "age": str(item.get("age", "") or ""),
                "culture": str(item.get("culture", "") or ""),
                "description": str(item.get("description", "") or ""),
            }
            for item in data
            if isinstance(item, dict)
        ]

    def self_test(self):
        names = [tool.get("name") for tool in self.tools()]
        assert names == [
            "speak_text",
            "stop_speaking",
            "save_wav",
            "list_voices",
            "list_voice_profiles",
            "get_voice_profile",
            "set_voice_profile",
            "reset_voice_profile",
            "preview_voice",
            "record_dictation",
            "voice_dataset_stats",
            "list_voice_dataset",
            "set_voice_sample_quality",
            "delete_voice_sample",
            "listen_once",
            "list_recognizers",
        ]

        assert self._bounded_int(99, -10, 10, 0) == 10
        assert self._bounded_int(-99, -10, 10, 0) == -10

        profile = self._normalise_profile(
            {
                "gender": "FEMALE",
                "accent": "British",
                "emotion": "excited",
                "depth": 50,
                "pitch": 3,
                "rate": 2,
                "volume": 90,
            }
        )
        assert profile["gender"] == "female"
        assert profile["accent"] == "en-GB"
        assert profile["emotion"] == "excited"
        assert self._clean_accent("American") == "en-US"
        assert self._clean_accent("en-au") == "en-AU"
        assert self._normalise_profile({})["delivery"] == "natural"
        assert self._normalise_profile({"delivery": "EXPRESSIVE"})["delivery"] == "expressive"
        assert profile["depth"] == 50

        resolved = self._resolved_modulation(profile)
        assert -12 <= resolved["resolved_pitch_semitones"] <= 12
        assert -50 <= resolved["resolved_rate_percent"] <= 80
        assert 0 <= resolved["resolved_volume"] <= 100

        deep = self._resolved_modulation(
            self._normalise_profile({"depth": 100})
        )
        light = self._resolved_modulation(
            self._normalise_profile({"depth": -100})
        )
        assert deep["resolved_pitch_semitones"] < light["resolved_pitch_semitones"]

        assert self.output_dir.name == "audio"
        assert self.profile_path.name == "speech_voice_profile.json"

        return (
            "Speech I/O Voice Studio profile, accent, emotion, gender, depth, "
            "pitch, rate, volume, storage and tool-contract checks passed."
        )

    def _voice_imprint_active(self):
        path = self.storage_dir / "media" / "voice_imprint" / "active_profile.json"
        try:
            stamp = path.stat().st_mtime_ns
        except Exception:
            self._imprint_active_cache = (0, False)
            return False
        cached_stamp, cached_value = self._imprint_active_cache
        if stamp == cached_stamp:
            return bool(cached_value)
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            value = bool(data.get("enabled") and data.get("profile_id"))
        except Exception:
            value = False
        self._imprint_active_cache = (stamp, value)
        return value

    def _voice_imprint_call(self, action, arguments):
        if not self._voice_imprint_active():
            return None
        if self.runtime is None or getattr(self.runtime, "_manager", None) is None:
            return None
        record = self.runtime._manager.get_module("voice_imprint_trainer")
        if not record or not record.get("enabled") or record.get("instance") is None:
            return None
        return self.runtime._manager.execute(
            "voice_imprint_trainer",
            action,
            dict(arguments or {}),
        )

    def _queue_voice_imprint(self, text):
        """Run voice on a daemon worker; keep only the newest queued request.

        Every request has an ID and a visible terminal state. A cancelled or
        superseded worker cannot mark the newer job as complete.
        """
        job = {"text": str(text or ""), "id": uuid.uuid4().hex}
        with self._imprint_worker_lock:
            self._imprint_generation += 1
            job["generation"] = self._imprint_generation
            self._imprint_pending = job
            worker = self._imprint_worker_thread
            queued = worker is not None and worker.is_alive()
            self._imprint_status = {
                "state": "queued" if queued else "starting",
                "job_id": job["id"], "updated_at": time.time(),
            }
            if queued:
                return {"started": True, "queued": True, "generating": True,
                        "job_id": job["id"], "characters": len(job["text"])}

            def loop():
                try:
                    while True:
                        with self._imprint_worker_lock:
                            current = self._imprint_pending
                            self._imprint_pending = None
                            if current is None:
                                break
                            if current["generation"] == self._imprint_generation:
                                self._imprint_status = {
                                    "state": "generating", "job_id": current["id"],
                                    "updated_at": time.time(),
                                }
                        try:
                            self._voice_imprint_call("speak", {"text": current["text"]})
                        except Exception as exc:
                            error = f"{type(exc).__name__}: {exc}"
                            with self._imprint_worker_lock:
                                self._imprint_last_error = error
                                if current["generation"] == self._imprint_generation:
                                    self._imprint_status = {
                                        "state": "failed", "job_id": current["id"],
                                        "updated_at": time.time(), "error": error,
                                    }
                        else:
                            with self._imprint_worker_lock:
                                if current["generation"] == self._imprint_generation:
                                    self._imprint_last_error = ""
                                    self._imprint_status = {
                                        "state": "completed", "job_id": current["id"],
                                        "updated_at": time.time(),
                                    }
                finally:
                    with self._imprint_worker_lock:
                        self._imprint_worker_thread = None

            worker = threading.Thread(
                target=loop, name="ApolloVoiceImprintTTS", daemon=True
            )
            self._imprint_worker_thread = worker
            worker.start()
        return {"started": True, "queued": False, "generating": True,
                "job_id": job["id"], "characters": len(job["text"])}

    def _speech_status(self):
        with self._imprint_worker_lock:
            snapshot = dict(self._imprint_status)
            worker = self._imprint_worker_thread
            snapshot["worker_alive"] = bool(worker and worker.is_alive())
            snapshot["pending"] = bool(self._imprint_pending)
            snapshot["last_error"] = self._imprint_last_error
        return snapshot

    def run(self, action, arguments):
        arguments = arguments or {}

        if action == "list_voice_profiles":
            voices = self._voice_metadata()
            return {
                "voices": voices,
                "engine": "Windows System.Speech",
                "offline": True,
            }

        if action == "list_voices":
            voices = self._voice_metadata()
            return {
                "voices": [item["name"] for item in voices],
                "engine": "Windows System.Speech",
                "offline": True,
            }

        if action == "get_voice_profile":
            return {
                "profile": dict(self.profile),
                "resolved": self._resolved_modulation(self.profile),
                "emotion_presets": {
                    key: value["label"]
                    for key, value in EMOTION_PRESETS.items()
                },
                "engine": "Windows System.Speech",
            }

        if action == "set_voice_profile":
            profile = self._save_profile(
                self._merged_profile(arguments)
            )
            return {
                "saved": True,
                "profile": profile,
                "resolved": self._resolved_modulation(profile),
                "file": str(self.profile_path),
            }

        if action == "reset_voice_profile":
            profile = self._save_profile(
                dict(DEFAULT_PROFILE)
            )
            return {
                "saved": True,
                "profile": profile,
                "resolved": self._resolved_modulation(profile),
            }

        if action == "list_recognizers":
            script = (
                "Add-Type -AssemblyName System.Speech; "
                "[System.Speech.Recognition.SpeechRecognitionEngine]::InstalledRecognizers() "
                "| ForEach-Object { $_.Culture.Name + ' | ' + $_.Description }"
            )
            output = self._run_powershell(script, timeout=30)
            recognizers = []
            for line in output.splitlines():
                line = line.strip()
                if not line:
                    continue
                if " | " in line:
                    culture, description = line.split(" | ", 1)
                else:
                    culture, description = line, line
                recognizers.append(
                    {
                        "culture": culture,
                        "description": description,
                    }
                )
            return {
                "recognizers": recognizers,
                "engine": "Windows System.Speech.Recognition",
                "offline": True,
            }

        if action == "speech_status":
            return self._speech_status()

        if action == "stop_speaking":
            with self._imprint_worker_lock:
                self._imprint_generation += 1
                self._imprint_pending = None
                self._imprint_status = {
                    "state": "cancelled", "job_id": self._imprint_status.get("job_id"),
                    "updated_at": time.time(),
                }
            imprint_stopped = False
            try:
                result = self._voice_imprint_call("stop_speaking", {})
                imprint_stopped = bool(result and result.get("stopped"))
            except Exception:
                imprint_stopped = False
            return {
                "stopped": bool(self._stop_process() or imprint_stopped)
            }

        if action in {"speak_text", "preview_voice"}:
            text = self._text(arguments)
            if action == "speak_text" and arguments.get("use_voice_imprint", True):
                try:
                    imprint = self._queue_voice_imprint(text) if self._voice_imprint_active() else None
                    if imprint and imprint.get("started"):
                        return {
                            **imprint,
                            "engine": "Apollo Voice Imprint / local neural TTS",
                            "voice_imprint": True,
                            "offline": True,
                        }
                except Exception as exc:
                    imprint_error = f"{type(exc).__name__}: {exc}"
                else:
                    imprint_error = ""
            else:
                imprint_error = ""

            resolved, env = self._speech_env(arguments, text)
            script = self._speech_script(
                "$s.SpeakSsml($ssml);"
            )
            self._stop_process()
            proc = self._start_powershell(script, env)
            with self._lock:
                self._speech_process = proc
            result = {
                "started": True,
                "pid": proc.pid,
                "characters": len(text),
                "profile": resolved,
                "engine": "Windows System.Speech + SSML",
                "offline": True,
                "voice_imprint": False,
            }
            if imprint_error:
                result["voice_imprint_fallback_reason"] = imprint_error
            return result

        if action == "save_wav":
            text = self._text(arguments)
            if arguments.get("use_voice_imprint", True):
                try:
                    imprint_args = {"text": text}
                    if arguments.get("filename"):
                        imprint_args["filename"] = arguments.get("filename")
                    imprint = self._voice_imprint_call("synthesize", imprint_args)
                    if imprint and imprint.get("saved"):
                        return {
                            **imprint,
                            "engine": "Apollo Voice Imprint / local neural TTS",
                            "voice_imprint": True,
                            "offline": True,
                        }
                except Exception:
                    pass
            filename = str(
                arguments.get("filename", "apollo_speech.wav")
                or "apollo_speech.wav"
            ).strip()

            if not filename.lower().endswith(".wav"):
                filename += ".wav"

            if (
                not _SAFE_FILENAME.match(filename)
                or "/" in filename
                or "\\" in filename
                or filename in {".", ".."}
            ):
                raise ValueError(
                    "Use a simple WAV filename without folders."
                )

            self.output_dir.mkdir(
                parents=True,
                exist_ok=True,
            )
            target = (
                self.output_dir
                / filename
            ).resolve()

            if self.output_dir not in target.parents:
                raise PermissionError(
                    "Output path escaped Apollo's TTS audio folder."
                )

            resolved, env = self._speech_env(
                arguments,
                text,
            )
            env["APOLLO_TTS_OUTPUT"] = str(
                target
            )
            script = self._speech_script(
                "$s.SetOutputToWaveFile($env:APOLLO_TTS_OUTPUT); "
                "$s.SpeakSsml($ssml); "
                "$s.SetOutputToDefaultAudioDevice();"
            )
            self._run_powershell(
                script,
                env,
                timeout=180,
            )
            return {
                "saved": True,
                "file": str(target),
                "characters": len(text),
                "profile": resolved,
                "engine": "Windows System.Speech + SSML",
                "offline": True,
            }

        if action == "voice_dataset_stats":
            records = self._dataset_records()
            return {
                "samples": len(records),
                "approved": sum(1 for r in records if r.get("approved_for_training")),
                "good": sum(1 for r in records if r.get("quality") == "good"),
                "seconds": round(sum(float(r.get("duration", 0) or 0) for r in records), 2),
                "folder": str(self.voice_dataset_dir),
            }

        if action == "list_voice_dataset":
            limit = self._bounded_int(arguments.get("limit", 100), 1, 1000, 100)
            records = self._dataset_records()
            return {"samples": records[-limit:], "total": len(records), "folder": str(self.voice_dataset_dir)}

        if action == "set_voice_sample_quality":
            sample_id = str(arguments.get("id", "") or "").strip()
            if not sample_id:
                raise ValueError("id is required.")
            quality = str(arguments.get("quality", "unrated") or "unrated").lower()
            if quality not in {"good", "bad", "unrated"}:
                quality = "unrated"
            approved = bool(arguments.get("approved_for_training", quality == "good"))
            with self._lock:
                records = self._dataset_records()
                found = False
                for record in records:
                    if str(record.get("id")) == sample_id:
                        record["quality"] = quality
                        record["approved_for_training"] = approved
                        found = True
                        break
                if not found:
                    raise KeyError(sample_id)
                self._write_dataset_records(records)
            return {"updated": True, "id": sample_id, "quality": quality, "approved_for_training": approved}

        if action == "delete_voice_sample":
            sample_id = str(arguments.get("id", "") or "").strip()
            if not sample_id:
                raise ValueError("id is required.")
            with self._lock:
                records = self._dataset_records()
                kept, removed = [], None
                for record in records:
                    if str(record.get("id")) == sample_id and removed is None:
                        removed = record
                    else:
                        kept.append(record)
                if removed is None:
                    raise KeyError(sample_id)
                audio = (self.voice_dataset_dir / str(removed.get("audio", ""))).resolve()
                if self.voice_dataset_dir in audio.parents and audio.is_file():
                    audio.unlink()
                self._write_dataset_records(kept)
            return {"deleted": True, "id": sample_id}

        if action == "record_dictation":
            self._require_windows()
            timeout_seconds = self._bounded_int(arguments.get("timeout_seconds", 12), 3, 30, 12)
            culture = str(arguments.get("culture", "") or "").strip()
            sample_id = time.strftime("%Y%m%d_%H%M%S") + "_" + uuid.uuid4().hex[:8]
            temp_dir = (self.storage_dir / "cache" / "dictation_temp").resolve()
            temp_dir.mkdir(parents=True, exist_ok=True)
            temp_wav = temp_dir / f"{sample_id}.wav"
            duration = self._record_microphone(temp_wav, timeout_seconds)
            transcript = self._recognize_wave_file(temp_wav, timeout_seconds, culture)

            saved = False
            final_file = temp_wav
            if self.profile.get("save_dictation", True) and transcript:
                self.voice_recordings_dir.mkdir(parents=True, exist_ok=True)
                final_file = self.voice_recordings_dir / f"{sample_id}.wav"
                temp_wav.replace(final_file)
                record = {
                    "id": sample_id,
                    "audio": f"recordings/{final_file.name}",
                    "transcript": transcript,
                    "duration": round(duration, 3),
                    "sample_rate": 16000,
                    "channels": 1,
                    "quality": "unrated",
                    "approved_for_training": False,
                    "source": "dictation",
                    "created_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
                }
                self._append_dataset_record(record)
                saved = True
            else:
                try:
                    temp_wav.unlink(missing_ok=True)
                except Exception:
                    pass

            return {
                "text": transcript,
                "heard": bool(transcript),
                "audio_saved": saved,
                "audio_file": str(final_file) if saved else None,
                "duration": round(duration, 3),
                "dataset_folder": str(self.voice_dataset_dir),
                "engine": "sounddevice capture + Windows System.Speech recognition",
                "offline": True,
            }

        if action == "listen_once":
            self._require_windows()

            timeout_seconds = self._bounded_int(
                arguments.get(
                    "timeout_seconds",
                    12,
                ),
                3,
                30,
                12,
            )
            culture = str(
                arguments.get(
                    "culture",
                    "",
                )
                or ""
            ).strip()

            env = {
                "APOLLO_STT_TIMEOUT": str(
                    timeout_seconds
                ),
                "APOLLO_STT_CULTURE": culture,
            }

            script = (
                "Add-Type -AssemblyName System.Speech; "
                "$infos = @([System.Speech.Recognition.SpeechRecognitionEngine]::InstalledRecognizers()); "
                "if ($infos.Count -eq 0) { throw 'No Windows speech recognizer is installed.' }; "
                "$wanted = $env:APOLLO_STT_CULTURE; "
                "$info = $null; "
                "if ($wanted) { "
                "  $info = $infos | Where-Object { $_.Culture.Name -eq $wanted } | Select-Object -First 1 "
                "}; "
                "if ($null -eq $info) { "
                "  $ui = [System.Globalization.CultureInfo]::CurrentUICulture.Name; "
                "  $info = $infos | Where-Object { $_.Culture.Name -eq $ui } | Select-Object -First 1 "
                "}; "
                "if ($null -eq $info) { $info = $infos | Select-Object -First 1 }; "
                "$r = New-Object System.Speech.Recognition.SpeechRecognitionEngine($info); "
                "$g = New-Object System.Speech.Recognition.DictationGrammar; "
                "$r.LoadGrammar($g); "
                "$r.SetInputToDefaultAudioDevice(); "
                "$seconds = [int]$env:APOLLO_STT_TIMEOUT; "
                "$result = $r.Recognize([TimeSpan]::FromSeconds($seconds)); "
                "if ($null -ne $result) { Write-Output $result.Text }; "
                "$r.Dispose();"
            )

            output = self._run_powershell(
                script,
                env,
                timeout=timeout_seconds + 20,
            )
            transcript = output.strip()

            return {
                "text": transcript,
                "heard": bool(transcript),
                "timeout_seconds": timeout_seconds,
                "engine": "Windows System.Speech.Recognition",
                "offline": True,
            }

        raise KeyError(action)

    def build_ui(self, parent=None, ui_context=None):
        from PySide6.QtCore import Qt, QObject, Signal
        from PySide6.QtWidgets import (
            QWidget,
            QVBoxLayout,
            QHBoxLayout,
            QLabel,
            QComboBox,
            QSlider,
            QPushButton,
            QLineEdit,
            QFrame,
            QCheckBox,
        )

        page = QWidget(parent)
        root = QVBoxLayout(page)
        root.setSpacing(12)

        title = QLabel("Voice Control & Selection")
        title.setStyleSheet(
            "font-size:24px;font-weight:800;color:#e7fffb;"
        )
        root.addWidget(title)

        subtitle = QLabel(
            "Choose and shape Apollo's Windows fallback voice. When a Voice Imprint is active, "
            "the neural voice takes priority; use the Voice Imprint tab to select and tune it."
        )
        subtitle.setWordWrap(True)
        subtitle.setStyleSheet("color:#8fcfc3;")
        root.addWidget(subtitle)

        note = QLabel(
            "Accent uses the culture of an installed Windows voice. Only accents "
            "available on this PC can be used. Choosing an accent can switch the exact "
            "voice back to Automatic so Windows selects a matching culture. Emotion is "
            "prosody modulation, not full neural acting."
        )
        note.setWordWrap(True)
        note.setStyleSheet(
            "color:#6fa99f;background:#071917;border:1px solid #124b45;"
            "border-radius:10px;padding:10px;"
        )
        root.addWidget(note)

        card = QFrame()
        card.setObjectName("card")
        card.setStyleSheet(
            "QFrame#card{background:#061312;border:1px solid #12574f;"
            "border-radius:14px;padding:8px;}"
        )
        form = QVBoxLayout(card)

        def add_combo(label_text, combo):
            row = QHBoxLayout()
            label = QLabel(label_text)
            label.setMinimumWidth(120)
            label.setStyleSheet("color:#cceee8;font-weight:600;")
            row.addWidget(label)
            row.addWidget(combo, 1)
            form.addLayout(row)

        def add_slider(label_text, low, high):
            row = QHBoxLayout()
            label = QLabel(label_text)
            label.setMinimumWidth(120)
            label.setStyleSheet("color:#cceee8;font-weight:600;")
            slider = QSlider(Qt.Horizontal)
            slider.setRange(low, high)
            value = QLabel("0")
            value.setMinimumWidth(48)
            value.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
            value.setStyleSheet("color:#73e9d3;font-weight:700;")
            slider.valueChanged.connect(
                lambda number, target=value: target.setText(str(number))
            )
            row.addWidget(label)
            row.addWidget(slider, 1)
            row.addWidget(value)
            form.addLayout(row)
            return slider, value

        voice_combo = QComboBox()
        voice_combo.addItem(
            "Automatic / Windows default",
            "",
        )
        add_combo("Installed voice", voice_combo)

        gender_combo = QComboBox()
        gender_combo.addItem("Any", "any")
        gender_combo.addItem("Male", "male")
        gender_combo.addItem("Female", "female")
        add_combo("Gender", gender_combo)

        accent_combo = QComboBox()
        accent_combo.addItem(
            "Automatic / voice default",
            "",
        )
        add_combo("Accent", accent_combo)

        emotion_combo = QComboBox()
        for key, data in EMOTION_PRESETS.items():
            emotion_combo.addItem(
                data["label"],
                key,
            )
        add_combo("Emotion", emotion_combo)

        delivery_combo = QComboBox()
        delivery_combo.addItem("Precise — read text closely", "precise")
        delivery_combo.addItem("Natural — conversational cleanup + pauses", "natural")
        delivery_combo.addItem("Expressive — natural + automatic emotion cues", "expressive")
        add_combo("Delivery", delivery_combo)

        save_dictation_check = QCheckBox("Save Dictate microphone audio + transcript for future TinyVoice training")
        save_dictation_check.setChecked(bool(self.profile.get("save_dictation", True)))
        save_dictation_check.setStyleSheet("color:#9fd9cf;")
        form.addWidget(save_dictation_check)

        skip_code_check = QCheckBox("Skip code blocks/URLs when Apollo speaks")
        skip_code_check.setChecked(bool(self.profile.get("skip_code", True)))
        skip_code_check.setStyleSheet("color:#9fd9cf;")
        form.addWidget(skip_code_check)

        depth_slider, depth_value = add_slider(
            "Depth",
            -100,
            100,
        )
        pitch_slider, pitch_value = add_slider(
            "Pitch (semitones)",
            -12,
            12,
        )
        rate_slider, rate_value = add_slider(
            "Speed",
            -10,
            10,
        )
        volume_slider, volume_value = add_slider(
            "Volume",
            0,
            100,
        )

        root.addWidget(card)

        resolved_label = QLabel()
        resolved_label.setStyleSheet(
            "color:#72d9c8;font-family:Consolas;"
        )
        resolved_label.setWordWrap(True)
        root.addWidget(resolved_label)

        preview_row = QHBoxLayout()
        preview_text = QLineEdit()
        preview_text.setPlaceholderText(
            "Preview phrase..."
        )
        preview_text.setText(
            "Hello. I'm Apollo. This is my current voice profile."
        )
        preview_button = QPushButton("▶ Preview")
        stop_button = QPushButton("■ Stop")
        preview_row.addWidget(
            preview_text,
            1,
        )
        preview_row.addWidget(
            preview_button
        )
        preview_row.addWidget(
            stop_button
        )
        root.addLayout(preview_row)

        button_row = QHBoxLayout()
        save_button = QPushButton(
            "Save as Apollo Voice"
        )
        reset_button = QPushButton(
            "Reset Neutral"
        )
        refresh_button = QPushButton(
            "Refresh Voices"
        )
        button_row.addWidget(save_button)
        button_row.addWidget(reset_button)
        button_row.addWidget(refresh_button)
        button_row.addStretch(1)
        root.addLayout(button_row)

        status = QLabel(
            "Voice Studio ready."
        )
        status.setStyleSheet(
            "color:#8ebbb4;"
        )
        root.addWidget(status)
        root.addStretch(1)

        def controls_profile():
            return self._normalise_profile(
                {
                    "voice": (
                        voice_combo.currentData()
                        or ""
                    ),
                    "gender": (
                        gender_combo.currentData()
                        or "any"
                    ),
                    "accent": (
                        accent_combo.currentData()
                        or ""
                    ),
                    "emotion": (
                        emotion_combo.currentData()
                        or "neutral"
                    ),
                    "delivery": (
                        delivery_combo.currentData()
                        or "natural"
                    ),
                    "save_dictation": save_dictation_check.isChecked(),
                    "skip_code": skip_code_check.isChecked(),
                    "depth": depth_slider.value(),
                    "pitch": pitch_slider.value(),
                    "rate": rate_slider.value(),
                    "volume": volume_slider.value(),
                }
            )

        def refresh_resolved():
            resolved = self._resolved_modulation(
                controls_profile()
            )
            resolved_label.setText(
                "Resolved output: "
                f"{resolved['resolved_pitch_semitones']:+d} st pitch  •  "
                f"{resolved['resolved_rate_percent']:+d}% rate  •  "
                f"{resolved['resolved_volume']}% volume  •  "
                f"{resolved['emotion_label']}  •  "
                f"accent {resolved['accent'] or 'voice default'}"
            )

        def set_combo_by_data(combo, wanted):
            for index in range(
                combo.count()
            ):
                if (
                    combo.itemData(index)
                    == wanted
                ):
                    combo.setCurrentIndex(
                        index
                    )
                    return

        def load_profile(profile):
            profile = self._normalise_profile(
                profile
            )

            wanted_voice = profile[
                "voice"
            ]
            found = False
            for index in range(
                voice_combo.count()
            ):
                if (
                    voice_combo.itemData(index)
                    == wanted_voice
                ):
                    voice_combo.setCurrentIndex(
                        index
                    )
                    found = True
                    break

            if (
                wanted_voice
                and not found
            ):
                voice_combo.addItem(
                    wanted_voice,
                    wanted_voice,
                )
                voice_combo.setCurrentIndex(
                    voice_combo.count() - 1
                )

            set_combo_by_data(
                gender_combo,
                profile["gender"],
            )

            wanted_accent = profile["accent"]
            accent_found = False
            for index in range(
                accent_combo.count()
            ):
                if (
                    accent_combo.itemData(index)
                    == wanted_accent
                ):
                    accent_combo.setCurrentIndex(
                        index
                    )
                    accent_found = True
                    break

            if (
                wanted_accent
                and not accent_found
            ):
                accent_combo.addItem(
                    ACCENT_LABELS.get(
                        wanted_accent,
                        wanted_accent,
                    ),
                    wanted_accent,
                )
                accent_combo.setCurrentIndex(
                    accent_combo.count() - 1
                )

            set_combo_by_data(
                emotion_combo,
                profile["emotion"],
            )
            set_combo_by_data(
                delivery_combo,
                profile.get("delivery", "natural"),
            )
            save_dictation_check.setChecked(bool(profile.get("save_dictation", True)))
            skip_code_check.setChecked(bool(profile.get("skip_code", True)))
            depth_slider.setValue(
                profile["depth"]
            )
            pitch_slider.setValue(
                profile["pitch"]
            )
            rate_slider.setValue(
                profile["rate"]
            )
            volume_slider.setValue(
                profile["volume"]
            )
            refresh_resolved()

        def refresh_voices():
            selected_voice = (
                voice_combo.currentData()
                or ""
            )
            selected_accent = (
                accent_combo.currentData()
                or ""
            )

            voice_combo.blockSignals(
                True
            )
            accent_combo.blockSignals(
                True
            )

            voice_combo.clear()
            accent_combo.clear()

            voice_combo.addItem(
                "Automatic / match accent",
                "",
            )
            accent_combo.addItem(
                "Automatic / voice default",
                "",
            )

            self._voice_culture_map = {}

            try:
                result = self.run(
                    "list_voice_profiles",
                    {},
                )
                voices = result.get(
                    "voices",
                    [],
                )

                cultures = {}

                for item in voices:
                    name = item.get(
                        "name",
                        "",
                    )
                    culture = item.get(
                        "culture",
                        "",
                    )

                    if not name:
                        continue

                    self._voice_culture_map[
                        name
                    ] = culture

                    detail = (
                        f"{name} — "
                        f"{item.get('gender', '?')} / "
                        f"{culture or '?'}"
                    )
                    voice_combo.addItem(
                        detail,
                        name,
                    )

                    if culture:
                        cultures[
                            culture
                        ] = (
                            ACCENT_LABELS.get(
                                culture,
                                culture,
                            )
                        )

                for culture in sorted(
                    cultures,
                    key=lambda item: (
                        cultures[item].lower(),
                        item.lower(),
                    ),
                ):
                    accent_combo.addItem(
                        cultures[culture],
                        culture,
                    )

                status.setText(
                    f"Found {len(voices)} installed Windows voice(s) "
                    f"across {len(cultures)} accent/culture option(s)."
                )

            except Exception as exc:
                status.setText(
                    "Could not list Windows voices: "
                    + str(exc)[:180]
                )

            voice_combo.blockSignals(
                False
            )
            accent_combo.blockSignals(
                False
            )

            for index in range(
                voice_combo.count()
            ):
                if (
                    voice_combo.itemData(index)
                    == selected_voice
                ):
                    voice_combo.setCurrentIndex(
                        index
                    )
                    break

            for index in range(
                accent_combo.count()
            ):
                if (
                    accent_combo.itemData(index)
                    == selected_accent
                ):
                    accent_combo.setCurrentIndex(
                        index
                    )
                    break

        def voice_changed():
            voice_name = (
                voice_combo.currentData()
                or ""
            )

            if voice_name:
                culture = getattr(
                    self,
                    "_voice_culture_map",
                    {},
                ).get(
                    voice_name,
                    "",
                )

                if culture:
                    accent_combo.blockSignals(
                        True
                    )
                    for index in range(
                        accent_combo.count()
                    ):
                        if (
                            accent_combo.itemData(index)
                            == culture
                        ):
                            accent_combo.setCurrentIndex(
                                index
                            )
                            break
                    accent_combo.blockSignals(
                        False
                    )

            refresh_resolved()

        def accent_changed():
            wanted = (
                accent_combo.currentData()
                or ""
            )
            voice_name = (
                voice_combo.currentData()
                or ""
            )

            if wanted and voice_name:
                current_culture = getattr(
                    self,
                    "_voice_culture_map",
                    {},
                ).get(
                    voice_name,
                    "",
                )

                if (
                    current_culture
                    and current_culture
                    != wanted
                ):
                    voice_combo.blockSignals(
                        True
                    )
                    voice_combo.setCurrentIndex(
                        0
                    )
                    voice_combo.blockSignals(
                        False
                    )
                    status.setText(
                        "Exact voice switched to Automatic so Apollo can use "
                        f"the {ACCENT_LABELS.get(wanted, wanted)} accent."
                    )

            refresh_resolved()

        def save_profile():
            result = self.run(
                "set_voice_profile",
                controls_profile(),
            )
            status.setText(
                "Saved. Apollo's next spoken reply will use this profile."
            )
            refresh_resolved()
            return result

        def preview():
            text = preview_text.text().strip()
            if not text:
                status.setText(
                    "Enter a preview phrase first."
                )
                return

            try:
                args = controls_profile()
                args["text"] = text
                self.run(
                    "preview_voice",
                    args,
                )
                status.setText(
                    "Preview playing..."
                )
            except Exception as exc:
                status.setText(
                    "Preview failed: "
                    + str(exc)[:180]
                )

        def stop():
            self.run(
                "stop_speaking",
                {},
            )
            status.setText(
                "Speech stopped."
            )

        def reset():
            self.run(
                "reset_voice_profile",
                {},
            )
            load_profile(
                dict(DEFAULT_PROFILE)
            )
            status.setText(
                "Voice profile reset to neutral."
            )

        voice_combo.currentIndexChanged.connect(
            voice_changed
        )
        accent_combo.currentIndexChanged.connect(
            accent_changed
        )

        for widget in (
            gender_combo,
            emotion_combo,
            delivery_combo,
        ):
            widget.currentIndexChanged.connect(
                refresh_resolved
            )

        for slider in (
            depth_slider,
            pitch_slider,
            rate_slider,
            volume_slider,
        ):
            slider.valueChanged.connect(
                refresh_resolved
            )

        class VoiceListSignals(QObject):
            finished = Signal(object, str)

        voice_list_signals = VoiceListSignals(page)

        def apply_voice_list_result(result, error):
            selected_voice = voice_combo.currentData() or ""
            selected_accent = accent_combo.currentData() or ""
            voice_combo.blockSignals(True)
            accent_combo.blockSignals(True)
            voice_combo.clear()
            accent_combo.clear()
            voice_combo.addItem("Automatic / match accent", "")
            accent_combo.addItem("Automatic / voice default", "")
            self._voice_culture_map = {}
            voices = result.get("voices", []) if isinstance(result, dict) else []
            cultures = {}
            for item in voices:
                name = item.get("name", "")
                culture = item.get("culture", "")
                if not name:
                    continue
                self._voice_culture_map[name] = culture
                voice_combo.addItem(f"{name} — {item.get('gender', '?')} / {culture or '?'}", name)
                if culture:
                    cultures[culture] = ACCENT_LABELS.get(culture, culture)
            for culture in sorted(cultures, key=lambda item: (cultures[item].lower(), item.lower())):
                accent_combo.addItem(cultures[culture], culture)
            voice_combo.blockSignals(False)
            accent_combo.blockSignals(False)
            set_combo_by_data(voice_combo, selected_voice)
            set_combo_by_data(accent_combo, selected_accent)
            status.setText(
                ("Could not list Windows voices: " + str(error)[:180]) if error else
                f"Found {len(voices)} installed Windows voice(s) across {len(cultures)} accent/culture option(s)."
            )
            load_profile(self.profile)

        voice_list_signals.finished.connect(apply_voice_list_result)

        def refresh_voices_async():
            status.setText("Scanning installed Windows voices in background...")

            def worker():
                try:
                    result = self.run("list_voice_profiles", {})
                    error = ""
                except Exception as exc:
                    result = {"voices": []}
                    error = f"{type(exc).__name__}: {exc}"
                voice_list_signals.finished.emit(result, error)

            threading.Thread(target=worker, name="ApolloVoiceList", daemon=True).start()

        preview_button.clicked.connect(
            preview
        )
        stop_button.clicked.connect(
            stop
        )
        save_button.clicked.connect(
            save_profile
        )
        reset_button.clicked.connect(
            reset
        )
        refresh_button.clicked.connect(
            refresh_voices_async
        )

        # Load saved controls immediately; enumerate Windows voices without
        # blocking the Qt event loop.
        load_profile(self.profile)
        refresh_voices_async()

        return page

    def close(self):
        self._stop_process()
