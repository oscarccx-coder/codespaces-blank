import inspect
import json
import math
import os
import queue
import re
import shutil
import subprocess
import sys
import threading
import uuid
import wave
from datetime import datetime
from pathlib import Path
from apollo_xtts_paths import chosen_xtts_folder, save_xtts_folder
from apollo_voice_profiles import VoiceProfileLibrary

import numpy as np


PROFILE_ID_RE = re.compile(r"[^a-zA-Z0-9_-]+")
SUPPORTED_SOURCE_EXTENSIONS = {
    ".wav", ".mp3", ".m4a", ".m4b", ".aac", ".flac", ".ogg", ".opus", ".wma"
}
SAMPLE_RATE = 24000

VOICE_TUNING_DEFAULTS = {
    "speed": 1.00,
    "pitch_semitones": 0.0,
    "temperature": 0.65,
    "length_penalty": 1.0,
    "repetition_penalty": 2.0,
    "top_k": 50,
    "top_p": 0.85,
    "gpt_cond_len": 6,
    "enable_text_splitting": False,
    "bass_db": 0.0,
    "treble_db": 0.0,
    "volume_db": 0.0,
}

VOICE_TUNING_PRESETS = {
    "Natural": dict(VOICE_TUNING_DEFAULTS),
    "Apollo": {
        **VOICE_TUNING_DEFAULTS,
        "speed": 1.04,
        "pitch_semitones": -1.25,
        "temperature": 0.72,
        "bass_db": 1.5,
        "treble_db": 0.5,
    },
    "Deep": {
        **VOICE_TUNING_DEFAULTS,
        "speed": 0.94,
        "pitch_semitones": -2.75,
        "temperature": 0.62,
        "bass_db": 3.0,
        "treble_db": -1.0,
    },
    "Cinematic": {
        **VOICE_TUNING_DEFAULTS,
        "speed": 0.90,
        "pitch_semitones": -1.5,
        "temperature": 0.78,
        "top_p": 0.90,
        "bass_db": 2.0,
        "treble_db": 0.5,
    },
    "Fast": {
        **VOICE_TUNING_DEFAULTS,
        "speed": 1.16,
        "temperature": 0.58,
    },
    "Stable": {
        **VOICE_TUNING_DEFAULTS,
        "temperature": 0.45,
        "repetition_penalty": 2.5,
        "top_k": 35,
        "top_p": 0.72,
    },
    "Bright": {
        **VOICE_TUNING_DEFAULTS,
        "speed": 1.03,
        "pitch_semitones": 1.0,
        "treble_db": 3.0,
    },
}


class Module:
    """
    Apollo Voice Imprint Lab.

    Architecture:
      1. Import a local single-speaker source recording for personal use.
      2. Convert it locally to 24 kHz mono PCM WAV with ffmpeg.
      3. Detect speech/silence and create quality-scored training/reference clips.
      4. Train a small NumPy autoencoder over acoustic feature vectors.  This is
         Apollo's local voice-signature network: it learns a compact speaker/style
         embedding and consistency statistics.
      5. For high-quality text-to-speech, use an OPTIONAL local pretrained neural
         TTS backend (XTTS).  Apollo supplies the learned profile's best reference
         clip; no network/download is performed automatically.

    The custom autoencoder is deliberately not presented as a full TTS model.
    Training a usable text-to-waveform synthesizer from one audiobook from scratch
    would be poor engineering.  The voice signature learns the source speaker;
    a pretrained local TTS model performs speech generation.
    """

    def __init__(self, context=None):
        context = context or {}
        self.base = Path(context.get("base_dir", ".")).resolve()
        self.runtime = context.get("runtime")
        self.validation = bool(context.get("validation", False))
        self.storage = self.base / "storage" / "media" / "voice_imprint"
        self.profiles = self.storage / "profiles"
        self.output = self.storage / "output"
        self.settings_path = self.storage / "settings.json"
        self.active_path = self.storage / "active_profile.json"
        self.library = VoiceProfileLibrary(self.storage)
        self.profiles.mkdir(parents=True, exist_ok=True)
        self.output.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._speech_process = None
        # Legacy in-process XTTS fields are kept only for explicit fallback/testing.
        # Normal Apollo speech uses an isolated worker process so torch/XTTS cannot
        # stall the Qt UI event loop or retain CUDA state inside the GUI process.
        self._xtts_model = None
        self._xtts_model_key = None
        self._xtts_inference_lock = threading.Lock()
        self._conditioning_cache = {}
        self._xtts_worker_process = None
        self._xtts_worker_reader = None
        self._xtts_worker_responses = queue.Queue()
        self._xtts_worker_request_lock = threading.Lock()
        self._xtts_worker_cancelled = threading.Event()
        self._xtts_worker_log_handle = None
        self._xtts_worker_last_error = ""
        self._dll_directory_handles = []
        self._training_state = {
            "running": False,
            "profile_id": "",
            "phase": "idle",
            "progress": 0,
            "epoch": 0,
            "epochs": 0,
            "loss": None,
            "message": "Idle",
            "started_at": "",
            "finished_at": "",
            "error": "",
        }

    # --------------------------- contracts ---------------------------
    def tools(self):
        return [
            {
                "name": "backend_status",
                "description": "Check ffmpeg, optional transcription and local neural TTS backend readiness.",
                "parameters": {"type": "object", "properties": {}},
            },
            {
                "name": "xtts_worker_status",
                "description": "Return isolated XTTS worker process status without importing the model in Apollo's GUI process.",
                "parameters": {"type": "object", "properties": {}},
            },
            {
                "name": "unload_xtts_worker",
                "description": "Stop the isolated XTTS worker and free its CPU/GPU memory. It will restart on the next neural speech request.",
                "parameters": {"type": "object", "properties": {}},
            },
            {
                "name": "import_audio",
                "description": (
                    "Import and analyse a local single-speaker voice source for Apollo's personal-use Voice Imprint workflow."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "source_path": {"type": "string"},
                        "profile_name": {"type": "string"},
                    },
                    "required": ["source_path", "profile_name"],
                },
            },
            {
                "name": "build_voice_from_audio",
                "description": (
                    "One-click personal-use workflow: import a local audio file, analyse/split it, "
                    "train Apollo's acoustic voice signature, create an XTTS-ready reference pack, "
                    "and optionally activate the finished profile."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "source_path": {"type": "string"},
                        "profile_name": {"type": "string"},
                        "epochs": {"type": "integer", "minimum": 20, "maximum": 1000},
                        "activate": {"type": "boolean"},
                    },
                    "required": ["source_path", "profile_name"],
                },
            },
            {
                "name": "voice_readiness",
                "description": (
                    "Report separately whether the selected voice profile is ready and whether "
                    "the shared XTTS base speech engine is ready."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {"profile_id": {"type": "string"}},
                },
            },
            {
                "name": "launch_xtts_installer",
                "description": (
                    "Launch Apollo's local XTTS v2 installer/repair utility in a separate console. "
                    "The user must explicitly accept the XTTS model terms in that installer."
                ),
                "parameters": {"type": "object", "properties": {}},
            },
            {
                "name": "find_xtts_model",
                "description": (
                    "Search Apollo and common local Coqui TTS cache folders for an already-installed "
                    "XTTS model containing config.json and model.pth."
                ),
                "parameters": {"type": "object", "properties": {}},
            },
            {
                "name": "play_reference",
                "description": "Play the extracted reference WAV for a prepared Voice Imprint profile.",
                "parameters": {
                    "type": "object",
                    "properties": {"profile_id": {"type": "string"}},
                    "required": ["profile_id"],
                },
            },
            {
                "name": "list_profiles",
                "description": "List imported voice profiles and training status.",
                "parameters": {"type": "object", "properties": {}},
            },
            {
                "name": "profile_status",
                "description": "Return one profile's dataset, quality, signature and backend status.",
                "parameters": {
                    "type": "object",
                    "properties": {"profile_id": {"type": "string"}},
                    "required": ["profile_id"],
                },
            },
            {
                "name": "train_voice_signature",
                "description": (
                    "Train Apollo's small local acoustic autoencoder on the imported clips and save a compact voice/style embedding."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "profile_id": {"type": "string"},
                        "epochs": {"type": "integer", "minimum": 20, "maximum": 1000},
                    },
                    "required": ["profile_id"],
                },
            },
            {
                "name": "training_status",
                "description": "Return live Voice Imprint training state, progress, current epoch and loss.",
                "parameters": {"type": "object", "properties": {}},
            },
            {
                "name": "transcribe_profile",
                "description": (
                    "Optionally transcribe prepared clips with faster-whisper if it is already installed/local. "
                    "Useful for future fine-tuning datasets; not required for reference-conditioned XTTS synthesis."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "profile_id": {"type": "string"},
                        "model": {"type": "string"},
                        "language": {"type": "string"},
                    },
                    "required": ["profile_id"],
                },
            },
            {
                "name": "configure_backend",
                "description": (
                    "Configure a local XTTS model directory and language. Apollo never downloads a voice model automatically."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "backend": {"type": "string", "enum": ["xtts_local", "disabled"]},
                        "model_dir": {"type": "string"},
                        "language": {"type": "string"},
                        "device": {"type": "string", "enum": ["auto", "cpu", "cuda"]},
                    },
                    "required": ["backend"],
                },
            },
            {
                "name": "get_voice_tuning",
                "description": "Get the selected/active Voice Imprint profile's saved XTTS and audio tuning controls.",
                "parameters": {
                    "type": "object",
                    "properties": {"profile_id": {"type": "string"}},
                },
            },
            {
                "name": "set_voice_tuning",
                "description": "Save speed, depth/pitch, expressiveness, sampling and EQ controls for a Voice Imprint profile.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "profile_id": {"type": "string"},
                        "tuning": {"type": "object"},
                    },
                    "required": ["profile_id", "tuning"],
                },
            },
            {
                "name": "reset_voice_tuning",
                "description": "Reset one Voice Imprint profile to natural tuning defaults.",
                "parameters": {
                    "type": "object",
                    "properties": {"profile_id": {"type": "string"}},
                    "required": ["profile_id"],
                },
            },
            {
                "name": "activate_profile",
                "description": "Activate a trained/imported profile as Apollo's preferred neural voice.",
                "parameters": {
                    "type": "object",
                    "properties": {"profile_id": {"type": "string"}},
                    "required": ["profile_id"],
                },
            },
            {
                "name": "deactivate_profile",
                "description": "Disable Voice Imprint routing and return Apollo to the normal Voice Studio engine.",
                "parameters": {"type": "object", "properties": {}},
            },
            {
                "name": "synthesize",
                "description": "Render text to WAV with the active/profile voice using the configured local neural backend.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "text": {"type": "string"},
                        "profile_id": {"type": "string"},
                        "filename": {"type": "string"},
                        "language": {"type": "string"},
                        "tuning": {"type": "object"},
                    },
                    "required": ["text"],
                },
            },
            {
                "name": "speak",
                "description": "Synthesize then play text using the active Voice Imprint profile.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "text": {"type": "string"},
                        "profile_id": {"type": "string"},
                        "language": {"type": "string"},
                        "tuning": {"type": "object"},
                    },
                    "required": ["text"],
                },
            },
            {
                "name": "stop_speaking",
                "description": "Stop Voice Imprint playback.",
                "parameters": {"type": "object", "properties": {}},
            },
            {
                "name": "export_training_dataset",
                "description": "Export the prepared clips/transcripts manifest path for future TinyVoice/fine-tuning work.",
                "parameters": {
                    "type": "object",
                    "properties": {"profile_id": {"type": "string"}},
                    "required": ["profile_id"],
                },
            },
        ]

    # ----------------------------- paths -----------------------------
    @staticmethod
    def _slug(value):
        value = PROFILE_ID_RE.sub("_", str(value or "").strip()).strip("_")
        if not value:
            value = "voice"
        return value[:64].lower()

    def _profile_dir(self, profile_id):
        profile_id = self._slug(profile_id)
        path = (self.profiles / profile_id).resolve()
        if self.profiles.resolve() not in path.parents:
            raise PermissionError("Profile path escaped voice storage")
        return path

    def _profile_json(self, profile_id):
        return self._profile_dir(profile_id) / "profile.json"

    def _load_json(self, path, default=None):
        try:
            value = json.loads(Path(path).read_text(encoding="utf-8"))
            return value
        except Exception:
            return {} if default is None else default

    def _save_json(self, path, value):
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        temp = path.with_suffix(path.suffix + ".tmp")
        temp.write_text(json.dumps(value, indent=2, ensure_ascii=False), encoding="utf-8")
        temp.replace(path)

    def _load_profile(self, profile_id):
        path = self._profile_json(profile_id)
        if not path.exists():
            raise KeyError(f"Voice profile '{profile_id}' does not exist")
        return self._load_json(path)

    def _save_profile(self, profile):
        profile["updated_at"] = datetime.now().isoformat(timespec="seconds")
        self._save_json(self._profile_json(profile["id"]), profile)
        return profile

    def _active(self):
        data = self._load_json(self.active_path, {})
        if not isinstance(data, dict):
            return {}
        return data

    def _settings(self):
        # 7.5.12.7's standalone C-drive helper accidentally wrote
        # backend_settings.json while Voice Imprint actually uses settings.json.
        # Merge that legacy file once so the user's successful path is not lost.
        legacy_backend = self.storage / "backend_settings.json"
        if legacy_backend.is_file():
            legacy = self._load_json(legacy_backend, {})
            current = self._load_json(self.settings_path, {})
            if not isinstance(current, dict):
                current = {}
            if isinstance(legacy, dict):
                for key in ("backend", "model_dir", "device", "language", "ffmpeg_shared_bin"):
                    if legacy.get(key) and not current.get(key):
                        current[key] = legacy[key]
                self._save_json(self.settings_path, current)
            try:
                legacy_backend.rename(self.storage / "backend_settings.migrated.json")
            except Exception:
                pass

        data = self._load_json(self.settings_path, {})
        if not isinstance(data, dict):
            data = {}
        data.setdefault("backend", "disabled")
        # A complete drop-in model or a saved user preference wins; legacy
        # settings are honoured if they still point to an installed model.
        data["model_dir"] = str(chosen_xtts_folder(self.base, data.get("model_dir")))
        data.setdefault("language", "en")
        data.setdefault("device", "auto")
        data.setdefault("process_isolation", True)
        data.setdefault("worker_cpu_threads", 4)
        data.setdefault("worker_timeout_seconds", 900)
        return data

    @staticmethod
    def _clamp(value, low, high):
        return max(low, min(high, value))

    def _normalise_voice_tuning(self, values=None):
        values = values or {}
        base = dict(VOICE_TUNING_DEFAULTS)
        if isinstance(values, dict):
            base.update(values)

        def f(name, low, high):
            try:
                value = float(base.get(name, VOICE_TUNING_DEFAULTS[name]))
            except Exception:
                value = float(VOICE_TUNING_DEFAULTS[name])
            return round(self._clamp(value, low, high), 4)

        def i(name, low, high):
            try:
                value = int(base.get(name, VOICE_TUNING_DEFAULTS[name]))
            except Exception:
                value = int(VOICE_TUNING_DEFAULTS[name])
            return int(self._clamp(value, low, high))

        return {
            "speed": f("speed", 0.65, 1.40),
            "pitch_semitones": f("pitch_semitones", -6.0, 6.0),
            "temperature": f("temperature", 0.10, 1.00),
            "length_penalty": f("length_penalty", -2.0, 3.0),
            "repetition_penalty": f("repetition_penalty", 1.0, 10.0),
            "top_k": i("top_k", 1, 100),
            "top_p": f("top_p", 0.10, 1.00),
            "gpt_cond_len": i("gpt_cond_len", 3, 12),
            "enable_text_splitting": bool(base.get("enable_text_splitting", True)),
            "bass_db": f("bass_db", -12.0, 12.0),
            "treble_db": f("treble_db", -12.0, 12.0),
            "volume_db": f("volume_db", -12.0, 6.0),
        }

    def _profile_tuning(self, profile_id):
        profile = self._load_profile(profile_id)
        return self._normalise_voice_tuning(profile.get("voice_tuning", {}))

    def _save_profile_tuning(self, profile_id, tuning):
        profile = self._load_profile(profile_id)
        clean = self._normalise_voice_tuning(tuning)
        profile["voice_tuning"] = clean
        profile["voice_tuning_updated_at"] = datetime.now().isoformat(timespec="seconds")
        self._save_json(self._profile_json(profile_id), profile)
        return clean

    def _resolve_tuning(self, profile_id, override=None):
        tuning = self._profile_tuning(profile_id)
        if isinstance(override, dict) and override:
            tuning.update(override)
            tuning = self._normalise_voice_tuning(tuning)
        return tuning

    # ------------------------- dependency state ----------------------
    @staticmethod
    def _ffmpeg():
        return shutil.which("ffmpeg")

    @staticmethod
    def _ffprobe():
        return shutil.which("ffprobe")

    @staticmethod
    def _module_available(name):
        # Readiness checks must never import torch/TTS into Apollo's GUI process.
        try:
            import importlib.util
            return importlib.util.find_spec(name) is not None
        except Exception:
            return False

    @staticmethod
    def _package_version(name):
        try:
            import importlib.metadata as metadata
            return str(metadata.version(name))
        except Exception:
            return ""

    @staticmethod
    def _import_status(name):
        # Historical name retained for compatibility; this is now a non-importing
        # spec check so opening Voice Center cannot freeze while importing PyTorch.
        try:
            import importlib.util
            found = importlib.util.find_spec(name) is not None
            return found, "" if found else f"{name} is not installed"
        except Exception as exc:
            return False, f"{type(exc).__name__}: {exc}"

    def _discover_ffmpeg_shared_bin(self):
        if sys.platform != "win32":
            return ""
        helper = self.base / "find_ffmpeg_shared.ps1"
        if not helper.is_file():
            return ""
        try:
            proc = subprocess.run(
                [
                    "powershell.exe",
                    "-NoProfile",
                    "-ExecutionPolicy",
                    "Bypass",
                    "-File",
                    str(helper),
                ],
                capture_output=True,
                text=True,
                timeout=25,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
            if proc.returncode == 0:
                lines = [line.strip() for line in (proc.stdout or "").splitlines() if line.strip()]
                if lines:
                    path = Path(lines[0])
                    if path.is_dir():
                        return str(path)
        except Exception:
            pass
        return ""

    def _prepare_xtts_runtime(self, settings=None):
        """Prepare Windows DLL search state for TorchCodec/XTTS.

        Apollo records the FFmpeg Shared bin path after installation, and can
        rediscover it from WinGet/package roots if Windows moves the portable
        package or PATH is incomplete.
        """
        settings = settings or self._settings()
        ffmpeg_shared = str(settings.get("ffmpeg_shared_bin", "") or "").strip()

        if not ffmpeg_shared or not Path(ffmpeg_shared).expanduser().is_dir():
            discovered = self._discover_ffmpeg_shared_bin()
            if discovered:
                ffmpeg_shared = discovered
                settings["ffmpeg_shared_bin"] = discovered
                try:
                    self._save_json(self.settings_path, settings)
                except Exception:
                    pass

        if not ffmpeg_shared:
            return {"configured": False, "path": "", "exists": False}

        path = Path(ffmpeg_shared).expanduser()
        exists = path.is_dir()
        if exists and sys.platform == "win32":
            text = str(path.resolve())
            current = os.environ.get("PATH", "")
            if text.lower() not in current.lower():
                os.environ["PATH"] = text + os.pathsep + current
            os.environ["TORCHCODEC_FFMPEG_DIR"] = text
            if hasattr(os, "add_dll_directory"):
                try:
                    handle = os.add_dll_directory(text)
                    self._dll_directory_handles.append(handle)
                except Exception:
                    pass
        return {"configured": bool(ffmpeg_shared), "path": str(path), "exists": exists}

    def _backend_status(self):
        settings = self._settings()
        runtime_path = self._prepare_xtts_runtime(settings)
        model_dir = Path(settings.get("model_dir", "")).expanduser()
        xtts_files = {
            "config": model_dir / "config.json",
            "checkpoint": model_dir / "model.pth",
            "vocab": model_dir / "vocab.json",
        }

        transformers_version = self._package_version("transformers")
        transformers_compatible = None
        if transformers_version:
            try:
                transformers_compatible = int(transformers_version.split(".", 1)[0]) < 5
            except Exception:
                pass

        torch_version = self._package_version("torch")
        torchvision_version = self._package_version("torchvision")
        torchaudio_version = self._package_version("torchaudio")
        torchcodec_version = self._package_version("torchcodec")
        coqui_version = self._package_version("coqui-tts")
        expected_runtime = {
            "torch": "2.11.0",
            "torchvision": "0.26.0",
            "torchaudio": "2.11.0",
            "torchcodec": "0.16.0",
            "coqui-tts": "0.27.5",
            "transformers": "4.57.6",
        }
        installed_runtime = {
            "torch": torch_version.split("+", 1)[0] if torch_version else "",
            "torchvision": torchvision_version.split("+", 1)[0] if torchvision_version else "",
            "torchaudio": torchaudio_version.split("+", 1)[0] if torchaudio_version else "",
            "torchcodec": torchcodec_version,
            "coqui-tts": coqui_version,
            "transformers": transformers_version,
        }
        runtime_mismatches = {
            name: {"installed": installed_runtime.get(name, ""), "expected": expected}
            for name, expected in expected_runtime.items()
            if installed_runtime.get(name, "") != expected
        }
        torch_ok, torch_error = self._import_status("torch")
        torchcodec_required = False
        if torch_version:
            try:
                parts = torch_version.split("+", 1)[0].split(".")
                torchcodec_required = (int(parts[0]), int(parts[1])) >= (2, 9)
            except Exception:
                pass

        if torchcodec_required:
            torchcodec_ok, torchcodec_error = self._import_status("torchcodec")
        else:
            torchcodec_ok, torchcodec_error = True, ""

        tts_ok, tts_error = self._import_status("TTS")

        return {
            "ffmpeg": self._ffmpeg() or "",
            "ffprobe": self._ffprobe() or "",
            "ffmpeg_shared_runtime": runtime_path,
            "numpy": True,
            "faster_whisper": self._module_available("faster_whisper"),
            "torch": torch_ok,
            "torch_version": torch_version,
            "torchvision_version": torchvision_version,
            "torchaudio_version": torchaudio_version,
            "torch_import_error": torch_error,
            "expected_xtts_runtime": expected_runtime,
            "installed_xtts_runtime": installed_runtime,
            "xtts_runtime_mismatches": runtime_mismatches,
            "xtts_runtime_pins_ok": not runtime_mismatches,
            "torchcodec_required": torchcodec_required,
            "torchcodec_version": torchcodec_version,
            "torchcodec_ready": torchcodec_ok,
            "torchcodec_import_error": torchcodec_error,
            "coqui_tts": tts_ok,
            "coqui_tts_import_error": tts_error,
            "transformers_version": transformers_version,
            "transformers_xtts_compatible": transformers_compatible,
            "recommended_transformers": "4.57.6",
            "backend": settings,
            "xtts_model_dir_exists": model_dir.is_dir(),
            "xtts_config_exists": xtts_files["config"].is_file(),
            "xtts_checkpoint_exists": xtts_files["checkpoint"].is_file(),
            "xtts_vocab_exists": xtts_files["vocab"].is_file(),
            "ready_for_import": bool(self._ffmpeg()),
            "ready_for_xtts": (
                torch_ok
                and torchcodec_ok
                and tts_ok
                and not runtime_mismatches
                and transformers_compatible is not False
                and xtts_files["config"].is_file()
                and xtts_files["checkpoint"].is_file()
                and xtts_files["vocab"].is_file()
            ),
            "engine_files_are_pretrained": True,
            "engine_explanation": (
                "config.json/model.pth/vocab.json are the shared pretrained XTTS engine. "
                "Your selected audio creates the speaker/reference pack used by that engine."
            ),
            "offline_policy": (
                "Apollo does not silently download the XTTS engine. Use Install / Repair XTTS Engine "
                "to perform the explicit dependency/model installation."
            ),
            "worker": self._xtts_worker_status(),
            "performance_policy": (
                "Heavy torch/XTTS imports, model loading, tokenization and neural inference run in a separate "
                "below-normal-priority process. Apollo's GUI process stays free of the XTTS model."
            ),
        }

    # --------------------------- audio IO ----------------------------
    def _convert_to_wav(self, source, target):
        ffmpeg = self._ffmpeg()
        if not ffmpeg:
            raise RuntimeError(
                "ffmpeg is required to import audiobook/audio tracks. Install ffmpeg and make sure ffmpeg.exe is on PATH."
            )
        target.parent.mkdir(parents=True, exist_ok=True)
        command = [
            ffmpeg, "-y", "-hide_banner", "-loglevel", "error",
            "-i", str(source),
            "-vn", "-ac", "1", "-ar", str(SAMPLE_RATE),
            "-c:a", "pcm_s16le", str(target),
        ]
        result = subprocess.run(command, capture_output=True, text=True, timeout=7200)
        if result.returncode != 0 or not target.exists():
            raise RuntimeError("ffmpeg conversion failed: " + (result.stderr or result.stdout)[-4000:])
        return target

    @staticmethod
    def _read_wav(path):
        with wave.open(str(path), "rb") as wav:
            channels = wav.getnchannels()
            width = wav.getsampwidth()
            rate = wav.getframerate()
            frames = wav.readframes(wav.getnframes())
        if width != 2:
            raise ValueError("Expected 16-bit PCM WAV")
        audio = np.frombuffer(frames, dtype="<i2").astype(np.float32)
        if channels > 1:
            audio = audio.reshape(-1, channels).mean(axis=1)
        audio /= 32768.0
        return rate, audio

    @staticmethod
    def _write_wav(path, rate, audio):
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        pcm = np.clip(np.asarray(audio, dtype=np.float32), -1.0, 1.0)
        pcm = (pcm * 32767.0).astype("<i2")
        with wave.open(str(path), "wb") as wav:
            wav.setnchannels(1)
            wav.setsampwidth(2)
            wav.setframerate(int(rate))
            wav.writeframes(pcm.tobytes())

    @staticmethod
    def _frame_rms(audio, frame_samples):
        if len(audio) < frame_samples:
            return np.array([float(np.sqrt(np.mean(audio * audio) + 1e-12))], dtype=np.float32)
        n = len(audio) // frame_samples
        trimmed = audio[: n * frame_samples].reshape(n, frame_samples)
        return np.sqrt(np.mean(trimmed * trimmed, axis=1) + 1e-12)

    def _segment_audio(self, wav_path, clips_dir):
        rate, audio = self._read_wav(wav_path)
        clips_dir.mkdir(parents=True, exist_ok=True)
        for old in clips_dir.glob("clip_*.wav"):
            old.unlink()

        frame_sec = 0.05
        frame = max(1, int(rate * frame_sec))
        rms = self._frame_rms(audio, frame)
        if rms.size == 0:
            raise ValueError("No audio found")

        floor = float(np.percentile(rms, 20))
        active = float(np.percentile(rms, 75))
        threshold = max(0.006, floor * 2.2, active * 0.12)
        voiced = rms > threshold

        # Fill brief gaps under ~350 ms so words are not chopped apart.
        gap_frames = max(1, int(0.35 / frame_sec))
        i = 0
        while i < len(voiced):
            if voiced[i]:
                i += 1
                continue
            j = i
            while j < len(voiced) and not voiced[j]:
                j += 1
            if i > 0 and j < len(voiced) and (j - i) <= gap_frames:
                voiced[i:j] = True
            i = j

        regions = []
        i = 0
        while i < len(voiced):
            if not voiced[i]:
                i += 1
                continue
            j = i
            while j < len(voiced) and voiced[j]:
                j += 1
            start = max(0.0, i * frame_sec - 0.15)
            end = min(len(audio) / rate, j * frame_sec + 0.15)
            if end - start >= 0.8:
                regions.append([start, end])
            i = j

        # Combine short speech regions into useful 5-14 sec references, splitting
        # long narration safely. This is intentionally conservative for audiobook data.
        chunks = []
        current = None
        for start, end in regions:
            if current is None:
                current = [start, end]
                continue
            proposed = end - current[0]
            gap = start - current[1]
            if proposed <= 14.0 and gap <= 0.9:
                current[1] = end
            else:
                chunks.append(current)
                current = [start, end]
        if current:
            chunks.append(current)

        final = []
        for start, end in chunks:
            duration = end - start
            if duration < 3.0:
                continue
            if duration <= 15.0:
                final.append((start, end))
                continue
            cursor = start
            while cursor < end:
                stop = min(cursor + 12.0, end)
                if stop - cursor >= 3.0:
                    final.append((cursor, stop))
                cursor = stop

        records = []
        for index, (start, end) in enumerate(final[:5000], 1):
            a = int(start * rate)
            b = int(end * rate)
            clip = audio[a:b]
            if clip.size == 0:
                continue
            peak = float(np.max(np.abs(clip)))
            rms_value = float(np.sqrt(np.mean(clip * clip) + 1e-12))
            clipping = float(np.mean(np.abs(clip) >= 0.995))
            silence_ratio = float(np.mean(np.abs(clip) < 0.006))
            dbfs = float(20.0 * np.log10(max(rms_value, 1e-8)))
            duration = float(len(clip) / rate)

            score = 100.0
            score -= min(40.0, clipping * 4000.0)
            score -= max(0.0, (silence_ratio - 0.28) * 65.0)
            if dbfs < -38:
                score -= min(30.0, (-38 - dbfs) * 2.0)
            if peak < 0.03:
                score -= 25.0
            if duration < 5.0:
                score -= (5.0 - duration) * 4.0
            score = max(0.0, min(100.0, score))
            quality = "good" if score >= 68.0 else "review" if score >= 45.0 else "bad"

            filename = f"clip_{index:05d}.wav"
            target = clips_dir / filename
            self._write_wav(target, rate, clip)
            records.append({
                "id": f"clip_{index:05d}",
                "audio": f"clips/{filename}",
                "duration": round(duration, 3),
                "rms_dbfs": round(dbfs, 2),
                "peak": round(peak, 5),
                "clipping_ratio": round(clipping, 6),
                "silence_ratio": round(silence_ratio, 4),
                "score": round(score, 2),
                "quality": quality,
                "transcript": "",
                "approved_for_training": quality == "good",
            })

        if not records:
            raise RuntimeError("No usable speech clips were detected in the imported audio")
        return records, {
            "threshold_rms": threshold,
            "source_seconds": round(len(audio) / rate, 2),
            "clip_count": len(records),
            "good_clips": sum(1 for r in records if r["quality"] == "good"),
            "usable_seconds": round(sum(r["duration"] for r in records if r["quality"] == "good"), 2),
        }

    # ---------------------- acoustic feature net --------------------
    @staticmethod
    def _clip_features(path, feature_bins=48):
        rate, audio = Module._read_wav(path)
        if len(audio) < int(rate * 0.5):
            raise ValueError("clip too short")

        frame = 1024
        hop = 512
        window = np.hanning(frame).astype(np.float32)
        spectra = []
        rms_values = []
        zcr_values = []
        centroids = []
        rolloffs = []
        freqs = np.fft.rfftfreq(frame, d=1.0 / rate)
        valid = (freqs >= 70.0) & (freqs <= min(11000.0, rate / 2.0))
        valid_freqs = freqs[valid]
        edges = np.geomspace(70.0, max(80.0, min(11000.0, rate / 2.0)), feature_bins + 1)

        for start in range(0, max(1, len(audio) - frame), hop):
            chunk = audio[start:start + frame]
            if len(chunk) < frame:
                chunk = np.pad(chunk, (0, frame - len(chunk)))
            rms = float(np.sqrt(np.mean(chunk * chunk) + 1e-12))
            if rms < 0.003:
                continue
            weighted = chunk * window
            power = np.abs(np.fft.rfft(weighted)) ** 2
            p = power[valid]
            if p.size == 0 or float(p.sum()) <= 0:
                continue
            bands = []
            for i in range(feature_bins):
                mask = (valid_freqs >= edges[i]) & (valid_freqs < edges[i + 1])
                bands.append(float(np.log1p(p[mask].mean() if np.any(mask) else 0.0)))
            spectra.append(bands)
            rms_values.append(rms)
            zcr_values.append(float(np.mean(np.signbit(chunk[:-1]) != np.signbit(chunk[1:]))))
            centroid = float((valid_freqs * p).sum() / max(p.sum(), 1e-12))
            centroids.append(centroid / max(rate / 2.0, 1.0))
            cumsum = np.cumsum(p)
            cutoff = cumsum[-1] * 0.85
            idx = int(np.searchsorted(cumsum, cutoff))
            rolloffs.append(float(valid_freqs[min(idx, len(valid_freqs) - 1)] / max(rate / 2.0, 1.0)))

        if not spectra:
            raise ValueError("no voiced frames")
        spectral = np.asarray(spectra, dtype=np.float32)
        mean_spec = spectral.mean(axis=0)

        def stats(values):
            arr = np.asarray(values, dtype=np.float32)
            return [
                float(arr.mean()), float(arr.std()),
                float(np.percentile(arr, 10)), float(np.percentile(arr, 90)),
            ]

        extra = []
        extra.extend(stats(rms_values))
        extra.extend(stats(zcr_values))
        extra.extend(stats(centroids))
        extra.extend(stats(rolloffs))
        vector = np.concatenate([mean_spec, np.asarray(extra, dtype=np.float32)])
        # 48 spectral + 16 prosody = 64 dimensions.
        assert vector.shape[0] == 64
        return vector.astype(np.float32)

    @staticmethod
    def _train_autoencoder(matrix, epochs=240, seed=73, progress_callback=None):
        x = np.asarray(matrix, dtype=np.float32)
        if x.ndim != 2 or x.shape[0] < 3:
            raise ValueError("At least three good clips are required to train the voice signature")
        mean = x.mean(axis=0)
        std = x.std(axis=0)
        std[std < 1e-5] = 1.0
        z = (x - mean) / std

        rng = np.random.default_rng(seed)
        dims = [z.shape[1], 48, 16, 48, z.shape[1]]
        weights = [rng.normal(0, 0.08, (dims[i], dims[i + 1])).astype(np.float32) for i in range(4)]
        biases = [np.zeros((1, dims[i + 1]), dtype=np.float32) for i in range(4)]
        lr = 0.006
        losses = []

        for epoch in range(int(epochs)):
            h1_pre = z @ weights[0] + biases[0]
            h1 = np.maximum(h1_pre, 0)
            code_pre = h1 @ weights[1] + biases[1]
            code = np.tanh(code_pre)
            h3_pre = code @ weights[2] + biases[2]
            h3 = np.maximum(h3_pre, 0)
            out = h3 @ weights[3] + biases[3]
            diff = out - z
            loss = float(np.mean(diff * diff))
            if epoch % 10 == 0 or epoch == epochs - 1:
                losses.append(loss)
            if progress_callback is not None:
                # Do not flood the UI/event loop: report roughly 100 steps max,
                # plus the first and final epoch.
                report_every = max(1, int(epochs) // 100)
                if epoch == 0 or epoch == epochs - 1 or (epoch + 1) % report_every == 0:
                    progress_callback(epoch + 1, int(epochs), loss)

            n = float(z.shape[0] * z.shape[1])
            d_out = 2.0 * diff / n
            d_w4 = h3.T @ d_out
            d_b4 = d_out.sum(axis=0, keepdims=True)
            d_h3 = d_out @ weights[3].T
            d_h3[h3_pre <= 0] = 0
            d_w3 = code.T @ d_h3
            d_b3 = d_h3.sum(axis=0, keepdims=True)
            d_code = d_h3 @ weights[2].T
            d_code_pre = d_code * (1.0 - code * code)
            d_w2 = h1.T @ d_code_pre
            d_b2 = d_code_pre.sum(axis=0, keepdims=True)
            d_h1 = d_code_pre @ weights[1].T
            d_h1[h1_pre <= 0] = 0
            d_w1 = z.T @ d_h1
            d_b1 = d_h1.sum(axis=0, keepdims=True)

            grads = [d_w1, d_w2, d_w3, d_w4]
            grad_bs = [d_b1, d_b2, d_b3, d_b4]
            # gradient clipping keeps tiny datasets stable
            for i in range(4):
                grads[i] = np.clip(grads[i], -2.0, 2.0)
                grad_bs[i] = np.clip(grad_bs[i], -2.0, 2.0)
                weights[i] -= lr * grads[i]
                biases[i] -= lr * grad_bs[i]
            lr = max(0.0015, lr * 0.998)

        h1 = np.maximum(z @ weights[0] + biases[0], 0)
        codes = np.tanh(h1 @ weights[1] + biases[1])
        embedding = codes.mean(axis=0)
        spread = codes.std(axis=0)
        consistency = float(max(0.0, min(1.0, 1.0 - float(np.mean(spread)) / 0.8)))
        return {
            "mean": mean, "std": std,
            "weights": weights, "biases": biases,
            "embedding": embedding,
            "spread": spread,
            "consistency": consistency,
            "losses": losses,
        }

    # ------------------------ profile actions ------------------------
    def _import_audio(self, source_path, profile_name, rights_confirmed=None):
        # Personal-use mode: no rights/permission checkbox gates local voice import.
        source = Path(str(source_path)).expanduser().resolve()
        if not source.is_file():
            raise FileNotFoundError(str(source))
        if source.suffix.lower() not in SUPPORTED_SOURCE_EXTENSIONS:
            raise ValueError("Unsupported audio type: " + source.suffix)

        base_id = self._slug(profile_name)
        profile_id = base_id
        counter = 2
        while self._profile_dir(profile_id).exists():
            profile_id = f"{base_id}_{counter}"
            counter += 1

        folder = self._profile_dir(profile_id)
        source_dir = folder / "source"
        clips_dir = folder / "clips"
        source_dir.mkdir(parents=True, exist_ok=True)
        clips_dir.mkdir(parents=True, exist_ok=True)
        original_copy = source_dir / ("original" + source.suffix.lower())
        shutil.copy2(source, original_copy)
        normalized = source_dir / "normalized_24k_mono.wav"
        self._convert_to_wav(original_copy, normalized)
        records, analysis = self._segment_audio(normalized, clips_dir)

        manifest_path = folder / "manifest.jsonl"
        manifest_path.write_text(
            "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in records),
            encoding="utf-8",
        )
        good = [row for row in records if row["quality"] == "good"]
        ranked = sorted(good or records, key=lambda row: (-float(row["score"]), abs(float(row["duration"]) - 9.0)))
        reference = ranked[0]["audio"] if ranked else ""
        profile = {
            "id": profile_id,
            "name": str(profile_name).strip() or profile_id,
            "created_at": datetime.now().isoformat(timespec="seconds"),
            "updated_at": datetime.now().isoformat(timespec="seconds"),
            "rights_confirmed": None,
            "personal_use_mode": True,
            "source_filename": source.name,
            "source_copy": str(original_copy.relative_to(folder)).replace("\\", "/"),
            "normalized_wav": str(normalized.relative_to(folder)).replace("\\", "/"),
            "manifest": "manifest.jsonl",
            "reference_clip": reference,
            "analysis": analysis,
            "signature_trained": False,
            "signature": {},
            "transcription": {"status": "not_run"},
        }
        self._save_profile(profile)
        return self._profile_status(profile_id)

    def _records(self, profile_id):
        folder = self._profile_dir(profile_id)
        manifest = folder / "manifest.jsonl"
        rows = []
        if manifest.exists():
            for line in manifest.read_text(encoding="utf-8", errors="replace").splitlines():
                try:
                    row = json.loads(line)
                    if isinstance(row, dict):
                        rows.append(row)
                except Exception:
                    pass
        return rows

    def _save_records(self, profile_id, rows):
        manifest = self._profile_dir(profile_id) / "manifest.jsonl"
        manifest.write_text(
            "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows),
            encoding="utf-8",
        )

    def _profile_status(self, profile_id):
        profile = self._load_profile(profile_id)
        rows = self._records(profile_id)
        active = self._active()
        return {
            "profile": profile,
            "clips": len(rows),
            "good_clips": sum(1 for row in rows if row.get("quality") == "good"),
            "approved_clips": sum(1 for row in rows if row.get("approved_for_training")),
            "seconds": round(sum(float(row.get("duration", 0) or 0) for row in rows), 2),
            "approved_seconds": round(sum(float(row.get("duration", 0) or 0) for row in rows if row.get("approved_for_training")), 2),
            "transcribed": sum(1 for row in rows if str(row.get("transcript", "")).strip()),
            "active": active.get("profile_id") == profile_id and bool(active.get("enabled")),
            "folder": str(self._profile_dir(profile_id)),
            "voice_tuning": self._profile_tuning(profile_id),
            "backend": self._backend_status(),
        }

    def _prepare_voice_pack(self, profile_id):
        """Create the speaker-specific files XTTS needs from imported audio.

        This is intentionally separate from the pretrained XTTS base engine.
        Source audio can produce speaker/reference files, but it cannot recreate
        XTTS's pretrained config.json/model.pth weights.
        """
        profile = self._load_profile(profile_id)
        rows = self._records(profile_id)
        folder = self._profile_dir(profile_id)
        pack_dir = folder / "voice_pack"
        pack_dir.mkdir(parents=True, exist_ok=True)

        candidates = [
            row for row in rows
            if row.get("approved_for_training") and (folder / str(row.get("audio", ""))).is_file()
        ]
        if not candidates:
            candidates = [
                row for row in rows
                if (folder / str(row.get("audio", ""))).is_file()
            ]
        if not candidates:
            raise RuntimeError("No usable reference clips were produced from this audio.")

        candidates = sorted(
            candidates,
            key=lambda row: (
                -float(row.get("score", 0.0) or 0.0),
                abs(float(row.get("duration", 0.0) or 0.0) - 9.0),
            ),
        )

        # Prefer the reference selected by signature training if it exists.
        preferred = str(profile.get("reference_clip", "")).strip()
        selected = None
        if preferred:
            for row in candidates:
                if str(row.get("audio", "")) == preferred:
                    selected = row
                    break
        if selected is None:
            selected = candidates[0]

        selected_path = (folder / selected["audio"]).resolve()
        reference_path = pack_dir / "reference.wav"
        shutil.copy2(selected_path, reference_path)

        top = []
        for index, row in enumerate(candidates[:5], start=1):
            source = (folder / row["audio"]).resolve()
            target = pack_dir / f"reference_{index:02d}.wav"
            shutil.copy2(source, target)
            top.append({
                "file": target.name,
                "source_clip": str(row.get("audio", "")),
                "duration": float(row.get("duration", 0.0) or 0.0),
                "score": float(row.get("score", 0.0) or 0.0),
                "quality": str(row.get("quality", "")),
            })

        pack = {
            "schema_version": 1,
            "profile_id": profile_id,
            "profile_name": profile.get("name", profile_id),
            "created_at": datetime.now().isoformat(timespec="seconds"),
            "reference_wav": "voice_pack/reference.wav",
            "reference_candidates": top,
            "normalized_source": profile.get("normalized_wav", ""),
            "signature_file": "voice_signature.json" if (folder / "voice_signature.json").is_file() else "",
            "signature_model": "voice_signature_net.npz" if (folder / "voice_signature_net.npz").is_file() else "",
            "speaker_files_ready": True,
            "requires_shared_engine": {
                "backend": "XTTS v2",
                "files": ["config.json", "model.pth"],
                "note": (
                    "These are pretrained XTTS engine files shared by every voice profile. "
                    "They cannot be generated from the speaker recording."
                ),
            },
        }
        self._save_json(pack_dir / "voice_pack.json", pack)

        profile["reference_clip"] = str(selected.get("audio", ""))
        profile["voice_pack"] = {
            "ready": True,
            "manifest": "voice_pack/voice_pack.json",
            "reference_wav": "voice_pack/reference.wav",
            "prepared_at": pack["created_at"],
        }
        self._save_profile(profile)
        return {
            "ready": True,
            "profile_id": profile_id,
            "folder": str(pack_dir),
            "reference_wav": str(reference_path),
            "manifest": str(pack_dir / "voice_pack.json"),
            "reference_candidates": len(top),
        }

    def _voice_readiness(self, profile_id=None):
        if not profile_id:
            active = self._active()
            profile_id = str(active.get("profile_id", "")).strip()
        profile_ready = False
        pack_ready = False
        signature_ready = False
        reference = ""
        profile_name = ""
        if profile_id:
            try:
                profile = self._load_profile(profile_id)
                profile_name = str(profile.get("name", profile_id))
                folder = self._profile_dir(profile_id)
                reference_path = folder / "voice_pack" / "reference.wav"
                pack_ready = reference_path.is_file() and (folder / "voice_pack" / "voice_pack.json").is_file()
                signature_ready = bool(profile.get("signature_trained")) and (folder / "voice_signature.json").is_file()
                profile_ready = pack_ready
                reference = str(reference_path) if reference_path.is_file() else ""
            except Exception:
                pass

        backend = self._backend_status()
        return {
            "profile_id": profile_id or "",
            "profile_name": profile_name,
            "speaker_voice_ready": profile_ready,
            "signature_ready": signature_ready,
            "reference_pack_ready": pack_ready,
            "reference_wav": reference,
            "xtts_engine_ready": bool(backend.get("ready_for_xtts")),
            "ready_to_generate_new_speech": bool(profile_ready and backend.get("ready_for_xtts")),
            "backend": backend,
            "next_step": (
                "Ready to generate new speech."
                if profile_ready and backend.get("ready_for_xtts")
                else (
                    "Voice pack is ready. Locate/install the shared XTTS base engine (config.json + model.pth)."
                    if profile_ready
                    else "Import/build a voice from audio first."
                )
            ),
        }

    def _find_xtts_models(self):
        settings = self._settings()
        roots = []

        def add_root(value):
            if not value:
                return
            try:
                path = Path(str(value)).expanduser().resolve()
            except Exception:
                return
            if path not in roots:
                roots.append(path)

        add_root(settings.get("model_dir"))
        if os.environ.get("LOCALAPPDATA"):
            add_root(Path(os.environ["LOCALAPPDATA"]) / "Apollo" / "models" / "voice")
        add_root(self.base / "storage" / "models" / "voice")
        add_root(os.environ.get("TTS_HOME"))
        add_root(os.environ.get("LOCALAPPDATA") and Path(os.environ["LOCALAPPDATA"]) / "tts")
        add_root(os.environ.get("APPDATA") and Path(os.environ["APPDATA"]) / "tts")
        add_root(Path.home() / ".local" / "share" / "tts")
        add_root(Path.home() / ".cache" / "tts")
        add_root(Path.home() / "AppData" / "Local" / "tts")

        found = []
        seen = set()
        inspected = 0
        max_inspected = 4000

        for root in roots:
            if not root.exists():
                continue

            candidates = [root]
            try:
                candidates.extend(path for path in root.rglob("*") if path.is_dir())
            except Exception:
                pass

            for folder in candidates:
                inspected += 1
                if inspected > max_inspected:
                    break
                try:
                    config = folder / "config.json"
                    checkpoint = folder / "model.pth"
                    if config.is_file() and checkpoint.is_file():
                        resolved = str(folder.resolve())
                        if resolved not in seen:
                            seen.add(resolved)
                            found.append({
                                "path": resolved,
                                "config": str(config),
                                "checkpoint": str(checkpoint),
                                "checkpoint_mb": round(checkpoint.stat().st_size / (1024 * 1024), 1),
                            })
                except Exception:
                    continue
            if inspected > max_inspected:
                break

        found.sort(
            key=lambda row: (
                0 if "xtts" in row["path"].lower() else 1,
                row["path"].lower(),
            )
        )
        return {
            "found": found,
            "count": len(found),
            "inspected_directories": inspected,
            "searched_roots": [str(path) for path in roots],
        }

    def _build_voice_from_audio(
        self,
        source_path,
        profile_name,
        epochs=240,
        activate=True,
        progress_callback=None,
    ):
        def emit(phase, progress, message, **extra):
            if progress_callback is not None:
                state = {
                    "phase": phase,
                    "progress": int(progress),
                    "message": message,
                    **extra,
                }
                progress_callback(state)

        emit("importing", 2, "Copying and normalising source audio...")
        imported = self._import_audio(source_path, profile_name)
        profile_id = imported["profile"]["id"]

        emit(
            "analysing",
            18,
            f"Audio analysed: {imported.get('clips', 0)} clips, "
            f"{imported.get('approved_clips', 0)} approved.",
        )

        def training_update(state):
            mapped = dict(state)
            # Allocate 20..90% to acoustic training.
            mapped["progress"] = 20 + int(float(state.get("progress", 0) or 0) * 0.70)
            emit(
                mapped.get("phase", "training"),
                mapped["progress"],
                mapped.get("message", "Training voice signature..."),
                epoch=mapped.get("epoch", 0),
                epochs=mapped.get("epochs", epochs),
                loss=mapped.get("loss"),
            )

        trained = self._train_signature(
            profile_id,
            epochs=epochs,
            progress_callback=training_update,
        )

        emit("packing", 93, "Building XTTS-ready speaker reference pack...")
        pack = self._prepare_voice_pack(profile_id)

        activation = None
        if activate:
            activation = self.run("activate_profile", {"profile_id": profile_id})

        readiness = self._voice_readiness(profile_id)
        emit(
            "complete",
            100,
            (
                "Voice files are ready. XTTS engine is ready too."
                if readiness.get("xtts_engine_ready")
                else "Voice files are ready. XTTS base engine still needs to be located/installed."
            ),
        )
        return {
            "built": True,
            "profile_id": profile_id,
            "profile": self._load_profile(profile_id),
            "import": imported,
            "training": trained,
            "voice_pack": pack,
            "activation": activation,
            "readiness": readiness,
        }

    def _train_signature(self, profile_id, epochs=240, progress_callback=None):
        requested_epochs = max(20, min(int(epochs), 1000))
        started_at = datetime.now().isoformat(timespec="seconds")

        with self._lock:
            if self._training_state.get("running"):
                raise RuntimeError(
                    "Voice Imprint training is already running for profile "
                    + str(self._training_state.get("profile_id") or "unknown")
                )
            self._training_state = {
                "running": True,
                "profile_id": profile_id,
                "phase": "preparing",
                "progress": 0,
                "epoch": 0,
                "epochs": requested_epochs,
                "loss": None,
                "message": "Preparing approved clips...",
                "started_at": started_at,
                "finished_at": "",
                "error": "",
            }

        def report(phase, progress, message, epoch=0, loss=None):
            state = {
                "running": True,
                "profile_id": profile_id,
                "phase": str(phase),
                "progress": max(0, min(100, int(progress))),
                "epoch": int(epoch or 0),
                "epochs": requested_epochs,
                "loss": None if loss is None else float(loss),
                "message": str(message),
                "started_at": started_at,
                "finished_at": "",
                "error": "",
            }
            with self._lock:
                self._training_state = state
            if progress_callback is not None:
                progress_callback(dict(state))

        try:
            profile = self._load_profile(profile_id)
            rows = [row for row in self._records(profile_id) if row.get("approved_for_training")]
            if len(rows) < 3:
                raise RuntimeError("At least three approved/good clips are required")

            folder = self._profile_dir(profile_id)
            features = []
            used = []
            limited_rows = rows[:800]
            total_clips = max(1, len(limited_rows))

            for index, row in enumerate(limited_rows, start=1):
                path = folder / row["audio"]
                try:
                    features.append(self._clip_features(path))
                    used.append(row)
                except Exception:
                    pass

                # Feature extraction gets the first 20% of the progress bar.
                prep_progress = int((index / total_clips) * 20)
                report(
                    "preparing",
                    prep_progress,
                    f"Preparing acoustic features {index}/{total_clips}",
                )

            if len(features) < 3:
                raise RuntimeError("Not enough clips produced usable acoustic features")

            matrix = np.stack(features, axis=0)

            def training_progress(epoch, total, loss):
                # Neural epochs occupy 20..95%; saving/finalising uses 95..100.
                fraction = float(epoch) / max(float(total), 1.0)
                overall = 20 + int(fraction * 75)
                report(
                    "training",
                    overall,
                    f"Training epoch {epoch}/{total}",
                    epoch=epoch,
                    loss=loss,
                )

            result = self._train_autoencoder(
                matrix,
                epochs=requested_epochs,
                progress_callback=training_progress,
            )

            report(
                "saving",
                96,
                "Saving trained voice signature...",
                epoch=requested_epochs,
                loss=float(result["losses"][-1]),
            )
            model_path = folder / "voice_signature_net.npz"
            np.savez_compressed(
            model_path,
            mean=result["mean"], std=result["std"],
            w1=result["weights"][0], w2=result["weights"][1],
            w3=result["weights"][2], w4=result["weights"][3],
            b1=result["biases"][0], b2=result["biases"][1],
            b3=result["biases"][2], b4=result["biases"][3],
            embedding=result["embedding"], spread=result["spread"],
            )
            # Pick the clip whose feature is closest to the mean source feature; this
            # tends to be a stable neutral reference instead of an extreme performance.
            normalized = (matrix - result["mean"]) / result["std"]
            centroid = normalized.mean(axis=0)
            distances = np.sqrt(np.sum((normalized - centroid) ** 2, axis=1))
            reference_row = used[int(np.argmin(distances))]
            signature = {
            "network": "numpy-acoustic-autoencoder-v1",
            "input_dimensions": 64,
            "embedding_dimensions": 16,
            "training_clips": len(features),
            "epochs": max(20, min(int(epochs), 1000)),
            "final_loss": round(float(result["losses"][-1]), 6),
            "consistency": round(float(result["consistency"]), 4),
            "embedding": [round(float(v), 6) for v in result["embedding"].tolist()],
            "reference_clip": reference_row["audio"],
            "model_file": model_path.name,
            "trained_at": datetime.now().isoformat(timespec="seconds"),
            }
            profile["signature_trained"] = True
            profile["signature"] = signature
            profile["reference_clip"] = reference_row["audio"]
            self._save_profile(profile)
            self._save_json(folder / "voice_signature.json", signature)

            finished_at = datetime.now().isoformat(timespec="seconds")
            complete = {
                "running": False,
                "profile_id": profile_id,
                "phase": "complete",
                "progress": 100,
                "epoch": requested_epochs,
                "epochs": requested_epochs,
                "loss": float(signature["final_loss"]),
                "message": "Voice signature training complete.",
                "started_at": started_at,
                "finished_at": finished_at,
                "error": "",
            }
            with self._lock:
                self._training_state = complete
            if progress_callback is not None:
                progress_callback(dict(complete))

            pack = self._prepare_voice_pack(profile_id)
            return {
                "trained": True,
                "profile_id": profile_id,
                "signature": signature,
                "voice_pack": pack,
                "training_status": complete,
            }

        except Exception as exc:
            failed = {
                "running": False,
                "profile_id": profile_id,
                "phase": "error",
                "progress": int(self._training_state.get("progress", 0) or 0),
                "epoch": int(self._training_state.get("epoch", 0) or 0),
                "epochs": requested_epochs,
                "loss": self._training_state.get("loss"),
                "message": "Training failed.",
                "started_at": started_at,
                "finished_at": datetime.now().isoformat(timespec="seconds"),
                "error": f"{type(exc).__name__}: {exc}",
            }
            with self._lock:
                self._training_state = failed
            if progress_callback is not None:
                progress_callback(dict(failed))
            raise

    def _transcribe(self, profile_id, model_name="base", language="en"):
        try:
            from faster_whisper import WhisperModel
        except Exception as exc:
            raise RuntimeError(
                "faster-whisper is not installed in Apollo's Python environment. This step is optional."
            ) from exc
        model_name = str(model_name or "base").strip()
        # faster-whisper may download named models. To preserve Apollo's offline-first
        # rule, named model IDs are only accepted if the path already exists; otherwise
        # the user must deliberately provide/install a model outside this action.
        model_path = Path(model_name).expanduser()
        if not model_path.exists():
            raise RuntimeError(
                "For offline transcription, provide a local faster-whisper model folder path. Apollo will not download it automatically."
            )
        model = WhisperModel(str(model_path), device="cpu", compute_type="int8")
        rows = self._records(profile_id)
        folder = self._profile_dir(profile_id)
        count = 0
        for row in rows:
            if not row.get("approved_for_training"):
                continue
            path = folder / row["audio"]
            segments, _info = model.transcribe(str(path), language=language or None, vad_filter=True)
            text = " ".join(segment.text.strip() for segment in segments if segment.text.strip()).strip()
            row["transcript"] = text
            if text:
                count += 1
        self._save_records(profile_id, rows)
        profile = self._load_profile(profile_id)
        profile["transcription"] = {
            "status": "complete",
            "clips": count,
            "model": str(model_path),
            "language": language,
            "completed_at": datetime.now().isoformat(timespec="seconds"),
        }
        self._save_profile(profile)
        return {"transcribed": count, "profile_id": profile_id}

    # -------------------- isolated XTTS worker ----------------------
    def _xtts_worker_status(self):
        proc = self._xtts_worker_process
        running = bool(proc is not None and proc.poll() is None)
        return {
            "process_isolation": bool(self._settings().get("process_isolation", True)),
            "running": running,
            "pid": proc.pid if running else None,
            "generating": self._xtts_worker_request_lock.locked(),
            "cancel_requested": self._xtts_worker_cancelled.is_set(),
            "last_error": self._xtts_worker_last_error,
            "log": str((self.base / "storage" / "logs" / "xtts_worker.log").resolve()),
        }

    def _xtts_worker_reader_loop(self, proc, response_queue):
        try:
            for line in iter(proc.stdout.readline, ""):
                line = line.strip()
                if not line.startswith("APOLLO_XTTS_JSON "):
                    continue
                try:
                    payload = json.loads(line[len("APOLLO_XTTS_JSON "):])
                except Exception:
                    continue
                response_queue.put(payload)
        finally:
            response_queue.put({
                "_worker_exit": True,
                "returncode": proc.poll(),
            })

    def _start_xtts_worker(self):
        proc = self._xtts_worker_process
        if proc is not None and proc.poll() is None:
            return proc

        worker = (self.base / "modules" / "voice_imprint_trainer" / "xtts_worker.py").resolve()
        if not worker.is_file():
            raise FileNotFoundError(str(worker))

        logs = (self.base / "storage" / "logs").resolve()
        logs.mkdir(parents=True, exist_ok=True)
        log_path = logs / "xtts_worker.log"
        try:
            if self._xtts_worker_log_handle:
                self._xtts_worker_log_handle.close()
        except Exception:
            pass
        self._xtts_worker_log_handle = open(log_path, "a", encoding="utf-8", buffering=1)

        env = os.environ.copy()
        env["PYTHONUNBUFFERED"] = "1"
        env["TOKENIZERS_PARALLELISM"] = "false"
        settings = self._settings()
        threads = max(1, min(int(settings.get("worker_cpu_threads", 4) or 4), 6))
        env["OMP_NUM_THREADS"] = str(threads)
        env["MKL_NUM_THREADS"] = str(threads)
        env["NUMEXPR_NUM_THREADS"] = str(threads)

        creationflags = 0
        if sys.platform == "win32":
            creationflags |= getattr(subprocess, "CREATE_NO_WINDOW", 0)
            creationflags |= getattr(subprocess, "BELOW_NORMAL_PRIORITY_CLASS", 0)

        proc = subprocess.Popen(
            [sys.executable, "-u", str(worker)],
            cwd=str(self.base),
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=self._xtts_worker_log_handle,
            text=True,
            bufsize=1,
            env=env,
            creationflags=creationflags,
        )
        self._xtts_worker_process = proc
        self._xtts_worker_last_error = ""
        response_queue = queue.Queue()
        self._xtts_worker_responses = response_queue
        reader = threading.Thread(
            target=self._xtts_worker_reader_loop,
            args=(proc, response_queue),
            name="ApolloXTTSWorkerReader",
            daemon=True,
        )
        self._xtts_worker_reader = reader
        reader.start()
        return proc

    def _stop_xtts_worker(self, graceful=False):
        # Wake any waiter immediately, even when a model is still importing or
        # CUDA has stopped responding. Never wait for its 900s synth timeout.
        self._xtts_worker_cancelled.set()
        response_queue = self._xtts_worker_responses
        response_queue.put({"_cancelled": True})
        proc = self._xtts_worker_process
        self._xtts_worker_process = None
        if proc is None:
            return False
        if proc.poll() is None:
            if graceful:
                try:
                    request = {"id": uuid.uuid4().hex, "op": "shutdown"}
                    proc.stdin.write(json.dumps(request) + "\n")
                    proc.stdin.flush()
                    proc.wait(timeout=4)
                except Exception:
                    pass
            if proc.poll() is None:
                try:
                    proc.terminate()
                    proc.wait(timeout=4)
                except Exception:
                    try:
                        proc.kill()
                    except Exception:
                        pass
        try:
            if proc.stdin:
                proc.stdin.close()
        except Exception:
            pass
        try:
            if proc.stdout:
                proc.stdout.close()
        except Exception:
            pass
        try:
            if self._xtts_worker_log_handle:
                self._xtts_worker_log_handle.close()
        except Exception:
            pass
        self._xtts_worker_log_handle = None
        self._xtts_worker_reader = None
        self._xtts_worker_responses = queue.Queue()
        return True

    def _xtts_worker_request(self, payload, timeout=None):
        settings = self._settings()
        timeout = int(timeout or settings.get("worker_timeout_seconds", 900) or 900)
        timeout = max(30, min(timeout, 3600))
        request_id = uuid.uuid4().hex
        message = {"id": request_id, **dict(payload or {})}

        with self._xtts_worker_request_lock:
            self._xtts_worker_cancelled.clear()
            proc = self._start_xtts_worker()
            response_queue = self._xtts_worker_responses
            try:
                proc.stdin.write(json.dumps(message, ensure_ascii=False) + "\n")
                proc.stdin.flush()
            except Exception as exc:
                self._xtts_worker_last_error = f"{type(exc).__name__}: {exc}"
                self._stop_xtts_worker(False)
                raise RuntimeError("XTTS worker could not accept a request: " + self._xtts_worker_last_error) from exc

            deadline = __import__("time").monotonic() + timeout
            while True:
                remaining = deadline - __import__("time").monotonic()
                if remaining <= 0:
                    self._xtts_worker_last_error = f"XTTS worker timed out after {timeout}s"
                    self._stop_xtts_worker(False)
                    raise TimeoutError(self._xtts_worker_last_error)
                if self._xtts_worker_cancelled.is_set():
                    raise RuntimeError("XTTS generation cancelled")
                try:
                    response = response_queue.get(timeout=min(0.25, remaining))
                except queue.Empty:
                    if proc.poll() is not None:
                        self._xtts_worker_last_error = f"XTTS worker exited with code {proc.returncode}"
                        self._stop_xtts_worker(False)
                        raise RuntimeError(self._xtts_worker_last_error)
                    continue
                if response.get("_cancelled"):
                    raise RuntimeError("XTTS generation cancelled")
                if response.get("_worker_exit"):
                    self._xtts_worker_last_error = f"XTTS worker exited with code {response.get('returncode')}"
                    self._stop_xtts_worker(False)
                    raise RuntimeError(self._xtts_worker_last_error)
                if str(response.get("id", "")) != request_id:
                    continue
                if not response.get("ok"):
                    error = str(response.get("error") or "XTTS worker failed")
                    detail = str(response.get("traceback") or "")
                    self._xtts_worker_last_error = error
                    raise RuntimeError(error + (("\n" + detail[-2500:]) if detail else ""))
                self._xtts_worker_last_error = ""
                return response

    def _synthesize_isolated(self, text, profile_id, target, language, tuning, settings, reference):
        runtime = self._prepare_xtts_runtime(settings)
        response = self._xtts_worker_request({
            "op": "synthesize",
            "text": text,
            "model_dir": str(Path(settings.get("model_dir", "")).expanduser().resolve()),
            "device": str(settings.get("device", "auto")),
            "ffmpeg_shared_bin": str(runtime.get("path") or settings.get("ffmpeg_shared_bin", "")),
            "cpu_threads": int(settings.get("worker_cpu_threads", 4) or 4),
            "reference": str(reference),
            "language": str(language),
            "tuning": dict(tuning),
            "output_path": str(target),
        })
        return dict(response.get("result") or {})

    # ---------------------- XTTS local synthesis ---------------------
    def _reference_wav(self, profile_id):
        profile = self._load_profile(profile_id)
        folder = self._profile_dir(profile_id)

        packed = (folder / "voice_pack" / "reference.wav").resolve()
        if packed.is_file():
            return packed

        rel = str(profile.get("reference_clip", "")).strip()
        if not rel:
            raise RuntimeError("Profile has no reference clip")
        path = (folder / rel).resolve()
        if not path.is_file():
            raise FileNotFoundError(str(path))
        return path

    def _load_xtts(self):
        settings = self._settings()
        if settings.get("backend") != "xtts_local":
            raise RuntimeError("Neural voice backend is disabled. Configure xtts_local first.")
        model_dir = Path(settings.get("model_dir", "")).expanduser().resolve()
        config_path = model_dir / "config.json"
        checkpoint = model_dir / "model.pth"
        if not config_path.is_file() or not checkpoint.is_file():
            raise RuntimeError(
                "Your speaker audio cannot create XTTS's pretrained model.pth/config.json. "
                "Apollo can build the complete speaker voice/reference pack from your audio, but "
                "new-text speech still needs the shared XTTS v2 base engine. "
                "Use 'Find Installed XTTS' or browse to a folder containing config.json and model.pth. "
                "Current folder: " + str(model_dir)
            )
        self._prepare_xtts_runtime(settings)
        try:
            import torch
            from TTS.tts.configs.xtts_config import XttsConfig
            from TTS.tts.models.xtts import Xtts
        except Exception as exc:
            raise RuntimeError(
                "XTTS runtime could not load. Use 'Install / Repair XTTS Engine' in Voice Imprint Lab, "
                "then restart Apollo. Runtime error: " + f"{type(exc).__name__}: {exc}"
            ) from exc

        device = str(settings.get("device", "auto")).lower()
        use_cuda = device == "cuda" or (device == "auto" and torch.cuda.is_available())
        key = (str(model_dir), use_cuda)
        if self._xtts_model is not None and self._xtts_model_key == key:
            return self._xtts_model, settings, use_cuda

        config = XttsConfig()
        config.load_json(str(config_path))
        model = Xtts.init_from_config(config)
        model.load_checkpoint(config, checkpoint_dir=str(model_dir), eval=True)
        if use_cuda:
            model.cuda()
        else:
            model.cpu()
        self._xtts_model = (model, config)
        self._xtts_model_key = key
        self._conditioning_cache.clear()
        return self._xtts_model, settings, use_cuda

    def _xtts_token_count(self, model, text, language):
        try:
            return len(model.tokenizer.encode(str(text), lang=str(language).split("-")[0]))
        except Exception:
            # Conservative fallback if a fork changes tokenizer API.
            return max(1, len(str(text)) // 2)

    def _split_xtts_text(self, model, text, language):
        """Split text below XTTS' hard autoregressive token limit without spaCy."""
        text = " ".join(str(text or "").split()).strip()
        if not text:
            return []

        hard_limit = int(getattr(getattr(model, "args", None), "gpt_max_text_tokens", 402) or 402)
        # XTTS asserts token_count < hard_limit. Leave generous headroom because
        # tokenization differs by language/punctuation and forks vary slightly.
        target = max(120, min(350, hard_limit - 32))
        if self._xtts_token_count(model, text, language) <= target:
            return [text]

        sentences = re.split(r"(?<=[.!?])\\s+|(?<=[。！？])", text)
        sentences = [part.strip() for part in sentences if part and part.strip()]
        chunks = []
        current = ""

        def push_piece(piece):
            nonlocal current
            piece = piece.strip()
            if not piece:
                return
            candidate = (current + " " + piece).strip() if current else piece
            if current and self._xtts_token_count(model, candidate, language) > target:
                chunks.append(current)
                current = piece
            else:
                current = candidate

        for sentence in sentences or [text]:
            if self._xtts_token_count(model, sentence, language) <= target:
                push_piece(sentence)
                continue

            words = sentence.split()
            if len(words) > 1:
                piece = ""
                for word in words:
                    candidate = (piece + " " + word).strip() if piece else word
                    if piece and self._xtts_token_count(model, candidate, language) > target:
                        push_piece(piece)
                        piece = word
                    else:
                        piece = candidate
                if piece:
                    push_piece(piece)
            else:
                # Languages without spaces / pathological long strings: binary-ish
                # character growth until the tokenizer approaches the safe target.
                start = 0
                while start < len(sentence):
                    lo, hi = 1, len(sentence) - start
                    best = 1
                    while lo <= hi:
                        mid = (lo + hi) // 2
                        candidate = sentence[start:start + mid]
                        if self._xtts_token_count(model, candidate, language) <= target:
                            best = mid
                            lo = mid + 1
                        else:
                            hi = mid - 1
                    push_piece(sentence[start:start + best])
                    start += best

        if current:
            chunks.append(current)

        # Final guard: never send a chunk at/over the model's true hard limit.
        for chunk in chunks:
            count = self._xtts_token_count(model, chunk, language)
            if count >= hard_limit:
                raise RuntimeError(
                    f"Apollo could not safely split XTTS text below its {hard_limit - 2} token limit "
                    f"(chunk token count: {count})."
                )
        return chunks

    def _conditioning_latents(self, model, config, profile_id, reference, tuning):
        """Cache speaker conditioning so repeated speech skips reference analysis."""
        if not hasattr(model, "get_conditioning_latents") or not hasattr(model, "inference"):
            return None
        reference = Path(reference).resolve()
        try:
            stamp = reference.stat().st_mtime_ns
        except Exception:
            stamp = 0
        key = (self._xtts_model_key, str(profile_id), str(reference), stamp, int(tuning["gpt_cond_len"]))
        if key in self._conditioning_cache:
            return self._conditioning_cache[key]
        try:
            method = model.get_conditioning_latents
            params = inspect.signature(method).parameters
            kwargs = {"audio_path": str(reference)}
            cond_len = int(tuning["gpt_cond_len"])
            if "gpt_cond_len" in params:
                kwargs["gpt_cond_len"] = cond_len
            if "gpt_cond_chunk_len" in params:
                kwargs["gpt_cond_chunk_len"] = min(4, cond_len)
            if "max_ref_length" in params:
                kwargs["max_ref_length"] = max(10, cond_len)
            if "sound_norm_refs" in params:
                kwargs["sound_norm_refs"] = False
            latents = method(**kwargs)
        except Exception:
            return None
        self._conditioning_cache.clear()
        self._conditioning_cache[key] = latents
        return latents

    def _xtts_generate_chunk(self, model, config, profile_id, reference, language, text, tuning):
        latents = self._conditioning_latents(model, config, profile_id, reference, tuning)
        if latents is not None:
            try:
                gpt_cond_latent, speaker_embedding = latents
                return model.inference(
                    text=text,
                    language=language,
                    gpt_cond_latent=gpt_cond_latent,
                    speaker_embedding=speaker_embedding,
                    temperature=float(tuning["temperature"]),
                    length_penalty=float(tuning["length_penalty"]),
                    repetition_penalty=float(tuning["repetition_penalty"]),
                    top_k=int(tuning["top_k"]),
                    top_p=float(tuning["top_p"]),
                    speed=float(tuning["speed"]),
                    enable_text_splitting=False,
                )
            except Exception:
                pass
        return model.synthesize(
            text,
            config,
            speaker_wav=str(reference),
            language=language,
            gpt_cond_len=int(tuning["gpt_cond_len"]),
            speed=float(tuning["speed"]),
            temperature=float(tuning["temperature"]),
            length_penalty=float(tuning["length_penalty"]),
            repetition_penalty=float(tuning["repetition_penalty"]),
            top_k=int(tuning["top_k"]),
            top_p=float(tuning["top_p"]),
            enable_text_splitting=False,
        )

    def _postprocess_voice_wav(self, path, rate, tuning, settings=None):
        """Apply independent pitch/depth, EQ and gain using local FFmpeg."""
        tuning = self._normalise_voice_tuning(tuning)
        pitch = float(tuning["pitch_semitones"])
        bass = float(tuning["bass_db"])
        treble = float(tuning["treble_db"])
        volume = float(tuning["volume_db"])

        filters = []
        if abs(pitch) >= 0.01:
            factor = 2.0 ** (pitch / 12.0)
            shifted_rate = max(8000, int(round(float(rate) * factor)))
            tempo = 1.0 / factor
            filters.extend([
                f"asetrate={shifted_rate}",
                f"aresample={int(rate)}",
                f"atempo={tempo:.8f}",
            ])
        if abs(bass) >= 0.01:
            filters.append(f"bass=g={bass:.3f}:f=120")
        if abs(treble) >= 0.01:
            filters.append(f"treble=g={treble:.3f}:f=3500")
        if abs(volume) >= 0.01:
            filters.append(f"volume={volume:.3f}dB")

        if not filters:
            return {"applied": [], "warning": ""}

        settings = settings or self._settings()
        prepared = self._prepare_xtts_runtime(settings)
        ffmpeg = shutil.which("ffmpeg")
        if not ffmpeg and prepared.get("path"):
            candidate = Path(prepared["path"]) / ("ffmpeg.exe" if sys.platform == "win32" else "ffmpeg")
            if candidate.is_file():
                ffmpeg = str(candidate)

        if not ffmpeg:
            return {
                "applied": [],
                "warning": "FFmpeg was not available for depth/EQ processing; base XTTS audio was kept.",
            }

        target = Path(path)
        processed = target.with_name(target.stem + "_voicefx.wav")
        command = [
            ffmpeg, "-y", "-hide_banner", "-loglevel", "error",
            "-i", str(target),
            "-af", ",".join(filters),
            "-c:a", "pcm_s16le",
            str(processed),
        ]
        try:
            proc = subprocess.run(
                command,
                capture_output=True,
                text=True,
                timeout=180,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0) if sys.platform == "win32" else 0,
            )
            if proc.returncode != 0 or not processed.is_file():
                detail = (proc.stderr or proc.stdout or "unknown FFmpeg error").strip()
                return {
                    "applied": [],
                    "warning": "Voice FX could not be applied; base XTTS audio was kept. " + detail[-500:],
                }
            os.replace(processed, target)
            applied = []
            if abs(pitch) >= 0.01:
                applied.append(f"pitch {pitch:+.2f} st")
            if abs(bass) >= 0.01:
                applied.append(f"bass {bass:+.1f} dB")
            if abs(treble) >= 0.01:
                applied.append(f"treble {treble:+.1f} dB")
            if abs(volume) >= 0.01:
                applied.append(f"gain {volume:+.1f} dB")
            return {"applied": applied, "warning": ""}
        finally:
            try:
                if processed.exists():
                    processed.unlink()
            except Exception:
                pass

    def _synthesize(self, text, profile_id=None, filename=None, language=None, tuning_override=None):
        text = " ".join(str(text or "").split()).strip()
        if not text:
            raise ValueError("text is required")
        if len(text) > 12000:
            raise ValueError("Voice Imprint synthesis is limited to 12000 characters per call")
        if not profile_id:
            active = self._active()
            if not active.get("enabled") or not active.get("profile_id"):
                raise RuntimeError("No active Voice Imprint profile")
            profile_id = active["profile_id"]

        profile = self._load_profile(profile_id)
        tuning = self._resolve_tuning(profile_id, tuning_override)
        settings = self._settings()
        if settings.get("backend") != "xtts_local":
            raise RuntimeError("Neural voice backend is disabled. Configure xtts_local first.")
        model_dir = Path(settings.get("model_dir", "")).expanduser().resolve()
        for required in ("config.json", "model.pth", "vocab.json"):
            if not (model_dir / required).is_file():
                raise RuntimeError(f"XTTS model is missing {required} in {model_dir}")

        reference = self._reference_wav(profile_id)
        language = str(language or settings.get("language") or "en")
        if filename:
            safe = PROFILE_ID_RE.sub("_", Path(str(filename)).stem).strip("_") or "apollo_voice"
            target = self.output / (safe + ".wav")
        else:
            target = self.output / ("apollo_voice_" + datetime.now().strftime("%Y%m%d_%H%M%S_%f") + ".wav")

        if bool(settings.get("process_isolation", True)):
            result = self._synthesize_isolated(
                text, profile_id, target, language, tuning, settings, reference
            )
            return {
                "saved": True,
                "file": str(target),
                "profile_id": profile_id,
                "profile_name": profile.get("name", profile_id),
                "reference_clip": str(reference),
                "backend": "xtts_local_worker",
                "process_isolated": True,
                "device": result.get("device", "unknown"),
                "language": language,
                "characters": len(text),
                "chunks": int(result.get("chunks", 1) or 1),
                "xtts_max_tokens": int(result.get("xtts_max_tokens", 402) or 402),
                "conditioning_cache_hit": bool(result.get("conditioning_cache_hit")),
                "conditioning_cache_entries": int(result.get("conditioning_cache_entries", 0) or 0),
                "worker": self._xtts_worker_status(),
                "tuning": tuning,
                "voice_fx": result.get("voice_fx", {}),
            }

        # Explicit legacy mode only. Keeping it available makes recovery possible,
        # but Apollo defaults to process isolation because threads alone cannot protect
        # Qt from native PyTorch/CUDA work in the same process.
        (model, config), settings, use_cuda = self._load_xtts()
        chunks = self._split_xtts_text(model, text, language)
        generated = []
        with self._xtts_inference_lock:
            for index, chunk in enumerate(chunks):
                result = self._xtts_generate_chunk(
                    model, config, profile_id, reference, language, chunk, tuning
                )
                wav_part = np.asarray(result.get("wav"), dtype=np.float32).reshape(-1)
                if wav_part.size == 0:
                    raise RuntimeError("XTTS returned empty audio")
                generated.append(wav_part)
                if index < len(chunks) - 1:
                    generated.append(np.zeros(int(SAMPLE_RATE * 0.08), dtype=np.float32))
        wav = np.concatenate(generated) if len(generated) > 1 else generated[0]
        rate = int(getattr(config.audio, "sample_rate", 24000) or 24000)
        self._write_wav(target, rate, wav)
        voice_fx = self._postprocess_voice_wav(target, rate, tuning, settings)
        return {
            "saved": True,
            "file": str(target),
            "profile_id": profile_id,
            "profile_name": profile.get("name", profile_id),
            "reference_clip": str(reference),
            "backend": "xtts_local_legacy_inprocess",
            "process_isolated": False,
            "device": "cuda" if use_cuda else "cpu",
            "language": language,
            "characters": len(text),
            "chunks": len(chunks),
            "xtts_max_tokens": int(getattr(getattr(model, "args", None), "gpt_max_text_tokens", 402) or 402),
            "conditioning_cached": bool(self._conditioning_cache),
            "tuning": tuning,
            "voice_fx": voice_fx,
        }

    def _stop_playback(self):
        with self._lock:
            proc = self._speech_process
            self._speech_process = None
        if proc is not None and proc.poll() is None:
            try:
                proc.terminate()
                proc.wait(timeout=2)
            except Exception:
                try:
                    proc.kill()
                except Exception:
                    pass
            return True
        return False

    def _play_wav(self, path):
        self._stop_playback()
        path = Path(path).resolve()
        if sys.platform == "win32":
            command = [
                "powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command",
                "$p=$env:APOLLO_VOICE_WAV; $s=New-Object System.Media.SoundPlayer $p; $s.PlaySync();",
            ]
            env = os.environ.copy()
            env["APOLLO_VOICE_WAV"] = str(path)
            kwargs = {}
            creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
            if creationflags:
                kwargs["creationflags"] = creationflags
            proc = subprocess.Popen(command, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, **kwargs)
        else:
            player = shutil.which("ffplay")
            if not player:
                raise RuntimeError("Playback requires Windows SoundPlayer or ffplay")
            proc = subprocess.Popen([player, "-nodisp", "-autoexit", "-loglevel", "quiet", str(path)])
        with self._lock:
            self._speech_process = proc
        return proc

    # ---------------------- UI-only profile management ----------------------
    def rename_profile_from_ui(self, profile_id, display_name):
        """Rename friendly label, preserving profile ID, clips and voice tuning."""
        with self._lock:
            result = self.library.rename(profile_id, display_name)
            active = self._active()
            if active.get("enabled") and active.get("profile_id") == profile_id:
                active["profile_name"] = result["name"]
                self._save_json(self.active_path, active)
                if self.runtime:
                    try:
                        self.runtime.blackboard_set("voice.active_imprint", active, "voice_imprint_trainer")
                    except Exception:
                        pass
            return result

    def reorder_profiles_from_ui(self, ordered_ids):
        with self._lock:
            return {"order": self.library.reorder(ordered_ids)}

    def archive_profile_from_ui(self, profile_id):
        """Only user-confirmed UI calls this method, never the agent tool bus."""
        with self._lock:
            if self._training_state.get("running"):
                raise RuntimeError("Stop voice training before deleting a profile.")
            status = self._xtts_worker_status()
            if status.get("generating"):
                raise RuntimeError("Stop voice generation before deleting a profile.")
            active = self._active()
            was_active = bool(active.get("enabled") and active.get("profile_id") == profile_id)
            result = self.library.archive(profile_id)
            if was_active:
                try:
                    self._save_json(self.active_path, {"enabled": False, "profile_id": ""})
                except Exception:
                    # Don't leave Apollo's active voice pointing at missing files.
                    Path(result["archive"]).rename(self._profile_dir(profile_id))
                    raise
                self._stop_playback()
                self._stop_xtts_worker(False)
                if self.runtime:
                    try:
                        self.runtime.blackboard_set(
                            "voice.active_imprint", {"enabled": False, "profile_id": ""},
                            "voice_imprint_trainer"
                        )
                    except Exception:
                        pass
            self._conditioning_cache.clear()
            return {**result, "deactivated": was_active}

    # ----------------------------- run -------------------------------
    def run(self, action, arguments):
        x = arguments or {}

        if action == "backend_status":
            return self._backend_status()

        if action == "xtts_worker_status":
            return self._xtts_worker_status()

        if action == "unload_xtts_worker":
            stopped = self._stop_xtts_worker(False)
            self._xtts_model = None
            self._xtts_model_key = None
            self._conditioning_cache.clear()
            return {"unloaded": bool(stopped), "worker": self._xtts_worker_status()}

        if action == "import_audio":
            return self._import_audio(
                x.get("source_path", ""), x.get("profile_name", "")
            )

        if action == "training_status":
            with self._lock:
                return dict(self._training_state)

        if action == "build_voice_from_audio":
            return self._build_voice_from_audio(
                x["source_path"],
                x["profile_name"],
                x.get("epochs", 240),
                bool(x.get("activate", True)),
            )

        if action == "voice_readiness":
            return self._voice_readiness(x.get("profile_id"))

        if action == "launch_xtts_installer":
            installer = (self.base / "install_xtts_v2.bat").resolve()
            if not installer.is_file():
                raise FileNotFoundError(str(installer))
            if sys.platform != "win32":
                raise RuntimeError("Apollo's bundled XTTS installer currently targets Windows.")
            flags = getattr(subprocess, "CREATE_NEW_CONSOLE", 0)
            proc = subprocess.Popen(
                ["cmd.exe", "/c", "call", str(installer)],
                cwd=str(self.base),
                creationflags=flags,
            )
            return {
                "started": True,
                "pid": proc.pid,
                "installer": str(installer),
                "note": "Complete the XTTS installer window, then restart/check Voice Imprint readiness.",
            }

        if action == "find_xtts_model":
            result = self._find_xtts_models()
            if result["found"]:
                settings = self._settings()
                settings["backend"] = "xtts_local"
                settings["model_dir"] = result["found"][0]["path"]
                self._save_json(self.settings_path, settings)
                self._xtts_model = None
                self._xtts_model_key = None
                result["selected"] = result["found"][0]
                result["settings"] = settings
            return result

        if action == "play_reference":
            reference = self._reference_wav(x["profile_id"])
            proc = self._play_wav(reference)
            return {
                "started": True,
                "profile_id": x["profile_id"],
                "reference_wav": str(reference),
                "pid": proc.pid,
            }

        if action == "list_profiles":
            profiles = []
            active = self._active()
            for profile_id in self.library.ordered_ids():
                folder = self.library._folder(profile_id)
                profile = self._load_json(folder / "profile.json", {})
                rows = self._records(folder.name)
                profiles.append({
                    "id": folder.name,
                    "name": profile.get("name", folder.name),
                    "signature_trained": bool(profile.get("signature_trained")),
                    "clips": len(rows),
                    "approved_seconds": round(sum(float(r.get("duration", 0) or 0) for r in rows if r.get("approved_for_training")), 2),
                    "active": active.get("enabled") and active.get("profile_id") == folder.name,
                    "created_at": profile.get("created_at", ""),
                })
            return {"profiles": profiles, "active": active}

        if action == "profile_status":
            return self._profile_status(x["profile_id"])

        if action == "train_voice_signature":
            return self._train_signature(x["profile_id"], x.get("epochs", 240))

        if action == "transcribe_profile":
            return self._transcribe(x["profile_id"], x.get("model", "base"), x.get("language", "en"))

        if action == "configure_backend":
            backend = str(x.get("backend", "disabled")).lower()
            if backend not in {"xtts_local", "disabled"}:
                raise ValueError("backend must be xtts_local or disabled")
            settings = self._settings()
            settings["backend"] = backend
            if x.get("model_dir"):
                settings["model_dir"] = save_xtts_folder(self.base, x["model_dir"])
            if x.get("language"):
                settings["language"] = str(x["language"])
            if x.get("device"):
                settings["device"] = str(x["device"]).lower()
            self._save_json(self.settings_path, settings)
            self._xtts_model = None
            self._xtts_model_key = None
            self._conditioning_cache.clear()
            self._stop_xtts_worker(False)
            return {"saved": True, "settings": settings, "status": self._backend_status()}

        if action == "get_voice_tuning":
            profile_id = str(x.get("profile_id", "") or "").strip()
            if not profile_id:
                active = self._active()
                profile_id = str(active.get("profile_id", "") or "").strip()
            if not profile_id:
                return {
                    "profile_id": "",
                    "tuning": dict(VOICE_TUNING_DEFAULTS),
                    "presets": VOICE_TUNING_PRESETS,
                }
            profile = self._load_profile(profile_id)
            return {
                "profile_id": profile_id,
                "profile_name": profile.get("name", profile_id),
                "tuning": self._profile_tuning(profile_id),
                "presets": VOICE_TUNING_PRESETS,
            }

        if action == "set_voice_tuning":
            profile_id = str(x.get("profile_id", "") or "").strip()
            if not profile_id:
                raise ValueError("profile_id is required")
            tuning = self._save_profile_tuning(profile_id, x.get("tuning", {}))
            profile = self._load_profile(profile_id)
            return {
                "saved": True,
                "profile_id": profile_id,
                "profile_name": profile.get("name", profile_id),
                "tuning": tuning,
            }

        if action == "reset_voice_tuning":
            profile_id = str(x.get("profile_id", "") or "").strip()
            if not profile_id:
                raise ValueError("profile_id is required")
            tuning = self._save_profile_tuning(profile_id, dict(VOICE_TUNING_DEFAULTS))
            return {"reset": True, "profile_id": profile_id, "tuning": tuning}

        if action == "activate_profile":
            profile = self._load_profile(x["profile_id"])
            readiness = self._voice_readiness(profile["id"])
            if not readiness.get("speaker_voice_ready"):
                raise RuntimeError("This profile has no usable Voice Imprint reference pack yet.")
            payload = {
                "enabled": True,
                "profile_id": profile["id"],
                "profile_name": profile.get("name", profile["id"]),
                "voice_tuning": self._profile_tuning(profile["id"]),
                "activated_at": datetime.now().isoformat(timespec="seconds"),
            }
            self._save_json(self.active_path, payload)
            if self.runtime:
                try:
                    self.runtime.blackboard_set("voice.active_imprint", payload, "voice_imprint_trainer")
                except Exception:
                    pass
            return {"activated": True, **payload}

        if action == "deactivate_profile":
            self._save_json(self.active_path, {"enabled": False, "profile_id": ""})
            self._stop_playback()
            return {"deactivated": True}

        if action == "synthesize":
            return self._synthesize(
                x.get("text", ""),
                x.get("profile_id"),
                x.get("filename"),
                x.get("language"),
                x.get("tuning"),
            )

        if action == "speak":
            result = self._synthesize(
                x.get("text", ""),
                x.get("profile_id"),
                None,
                x.get("language"),
                x.get("tuning"),
            )
            proc = self._play_wav(result["file"])
            return {**result, "started": True, "pid": proc.pid}

        if action == "stop_speaking":
            playback = self._stop_playback()
            worker = self._stop_xtts_worker(False)
            return {"stopped": bool(playback or worker), "playback": playback, "generation_cancelled": worker}

        if action == "export_training_dataset":
            profile = self._load_profile(x["profile_id"])
            folder = self._profile_dir(profile["id"])
            return {
                "profile_id": profile["id"],
                "folder": str(folder),
                "manifest": str(folder / "manifest.jsonl"),
                "clips": str(folder / "clips"),
                "signature": str(folder / "voice_signature.json"),
                "note": "Personal-use Voice Imprint dataset exported for local Apollo training/fine-tuning workflows.",
            }

        raise KeyError(action)

    def self_test(self):
        names = {tool["name"] for tool in self.tools()}
        required = {
            "import_audio", "train_voice_signature", "activate_profile", "synthesize",
            "configure_backend", "backend_status", "export_training_dataset",
            "build_voice_from_audio", "voice_readiness", "find_xtts_model", "play_reference",
            "launch_xtts_installer", "get_voice_tuning", "set_voice_tuning",
            "reset_voice_tuning", "xtts_worker_status", "unload_xtts_worker",
        }
        assert required.issubset(names)
        assert self._slug("Apollo Voice!") == "apollo_voice"
        assert SAMPLE_RATE == 24000
        tuned = self._normalise_voice_tuning({
            "speed": 9,
            "pitch_semitones": -99,
            "top_p": 4,
            "top_k": 0,
        })
        assert tuned["speed"] == 1.4
        assert tuned["pitch_semitones"] == -6.0
        assert tuned["top_p"] == 1.0
        assert tuned["top_k"] == 1
        # Neural net shape regression on synthetic voice-like feature vectors.
        rng = np.random.default_rng(9)
        matrix = rng.normal(size=(8, 64)).astype(np.float32)
        trained = self._train_autoencoder(matrix, epochs=20)
        assert trained["embedding"].shape == (16,)
        assert 0.0 <= trained["consistency"] <= 1.0
        return "Voice Imprint import, dataset, neural signature and local-backend contracts passed."

    # ------------------------------- UI ------------------------------
    def build_ui(self, parent=None, ui_context=None):
        from PySide6.QtCore import Qt, QObject, Signal, QTimer
        from PySide6.QtWidgets import (
            QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QLineEdit,
            QTextEdit, QCheckBox, QFileDialog, QComboBox, QListWidget, QMessageBox,
            QSpinBox, QDoubleSpinBox, QGroupBox, QFormLayout, QSplitter, QScrollArea, QSizePolicy,
            QProgressBar, QInputDialog, QListWidgetItem,
        )

        page = QWidget(parent)
        page.setMinimumHeight(720)
        outer = QVBoxLayout(page)
        outer.setSpacing(12)
        title = QLabel("Voice Imprint Lab")
        title.setStyleSheet("font-size:24px;font-weight:800;")
        outer.addWidget(title)
        description = QLabel(
            "Import a clean single-speaker recording, build a speech dataset, train Apollo's acoustic voice-signature network, "
            "then use an optional LOCAL XTTS model to reinterpret Apollo's text in that voice. "
            "Personal-use mode is enabled: Apollo does not block local imports with a permission checkbox."
        )
        description.setWordWrap(True)
        outer.addWidget(description)

        splitter = QSplitter(Qt.Horizontal)
        outer.addWidget(splitter, 1)

        left = QWidget()
        left_layout = QVBoxLayout(left)
        profiles_list = QListWidget()
        left_layout.addWidget(QLabel("Voice Profiles"))
        left_layout.addWidget(profiles_list, 1)
        manager_actions = QHBoxLayout()
        rename_profile_button = QPushButton("Rename")
        archive_profile_button = QPushButton("Delete…")
        manager_actions.addWidget(rename_profile_button)
        manager_actions.addWidget(archive_profile_button)
        left_layout.addLayout(manager_actions)
        move_actions = QHBoxLayout()
        move_up_button = QPushButton("Move Up")
        move_down_button = QPushButton("Move Down")
        move_actions.addWidget(move_up_button)
        move_actions.addWidget(move_down_button)
        left_layout.addLayout(move_actions)
        refresh_profiles = QPushButton("Refresh Profiles")
        left_layout.addWidget(refresh_profiles)
        splitter.addWidget(left)

        right = QWidget()
        right.setMinimumWidth(620)
        right_layout = QVBoxLayout(right)
        right_layout.setSpacing(12)

        import_box = QGroupBox("1. Choose Audio + Build Voice")
        import_form = QFormLayout(import_box)
        profile_name = QLineEdit()
        profile_name.setMinimumHeight(38)
        profile_name.setPlaceholderText("Apollo narrator")
        source_path = QLineEdit()
        source_path.setMinimumHeight(38)
        browse = QPushButton("Browse Audio…")
        source_row = QHBoxLayout()
        source_row.addWidget(source_path, 1)
        source_row.addWidget(browse)
        source_host = QWidget()
        source_host.setLayout(source_row)
        personal_use = QLabel(
            "Personal-use mode. Choose the recording you want Apollo to learn from. "
            "Apollo will keep the source locally, normalise it, split/score the speech, "
            "learn the acoustic signature and build the speaker reference files."
        )
        personal_use.setWordWrap(True)
        build_button = QPushButton("Use This Audio → Build Voice")
        import_button = QPushButton("Import + Analyse Only")
        import_form.addRow("Profile name", profile_name)
        import_form.addRow("Audio track", source_host)
        import_form.addRow(personal_use)
        import_form.addRow(build_button)
        import_form.addRow(import_button)
        right_layout.addWidget(import_box)

        train_box = QGroupBox("2. Learn Voice Signature")
        train_form = QFormLayout(train_box)
        epochs = QSpinBox()
        epochs.setRange(20, 1000)
        epochs.setValue(240)
        train_button = QPushButton("Train Acoustic Neural Signature")
        activate_button = QPushButton("Set Selected as Apollo Default Voice")
        deactivate_button = QPushButton("Return to Normal Voice Studio")

        training_status_label = QLabel("Status: Idle")
        training_status_label.setWordWrap(True)
        training_progress = QProgressBar()
        training_progress.setRange(0, 100)
        training_progress.setValue(0)
        training_progress.setTextVisible(True)
        training_progress.setFormat("%p%")
        training_detail = QLabel("Epoch: —   Loss: —   Elapsed: 00:00")
        training_detail.setWordWrap(True)

        train_form.addRow("Training epochs", epochs)
        train_form.addRow(train_button)
        train_form.addRow(training_status_label)
        train_form.addRow(training_progress)
        train_form.addRow(training_detail)
        train_form.addRow(activate_button)
        train_form.addRow(deactivate_button)
        right_layout.addWidget(train_box)

        backend_box = QGroupBox("3. Local Neural Speech Backend")
        backend_form = QFormLayout(backend_box)
        model_dir = QLineEdit(str(self._settings().get("model_dir", "")))
        model_dir.setMinimumHeight(38)
        browse_model = QPushButton("Browse Model Folder…")
        model_row = QHBoxLayout()
        model_row.addWidget(model_dir, 1)
        model_row.addWidget(browse_model)
        model_host = QWidget()
        model_host.setLayout(model_row)
        device = QComboBox()
        device.setMinimumHeight(38)
        device.addItems(["auto", "cuda", "cpu"])
        device.setCurrentText(str(self._settings().get("device", "auto")))
        language = QLineEdit(str(self._settings().get("language", "en")))
        language.setMinimumHeight(38)
        engine_note = QLabel(
            "One-time speech engine: Apollo builds the speaker voice files from your audio. "
            "XTTS still needs its shared pretrained config.json + model.pth to turn new text into speech. "
            "Those two engine files are not trained from your recording."
        )
        engine_note.setWordWrap(True)
        install_backend = QPushButton("Install / Repair XTTS Engine")
        find_backend = QPushButton("Find Installed XTTS")
        save_backend = QPushButton("Use This XTTS Folder")
        backend_status = QPushButton("Check Voice + Engine Readiness")
        backend_form.addRow(engine_note)
        backend_form.addRow("XTTS model folder", model_host)
        backend_form.addRow("Device", device)
        backend_form.addRow("Language", language)
        backend_form.addRow(install_backend)
        backend_form.addRow(find_backend)
        backend_form.addRow(save_backend)
        backend_form.addRow(backend_status)
        worker_status_label = QLabel("XTTS worker: stopped")
        worker_status_label.setWordWrap(True)
        unload_worker_button = QPushButton("Unload XTTS / Free GPU Memory")
        performance_note = QLabel(
            "Performance mode: neural model loading and synthesis run in a separate below-normal-priority process. "
            "Apollo's main UI process stays responsive and does not hold the XTTS CUDA model."
        )
        performance_note.setWordWrap(True)
        backend_form.addRow(worker_status_label)
        backend_form.addRow(performance_note)
        backend_form.addRow(unload_worker_button)
        right_layout.addWidget(backend_box)

        tuning_box = QGroupBox("4. Shape + Save This Voice")
        tuning_form = QFormLayout(tuning_box)

        active_voice_label = QLabel("Apollo default voice: none")
        active_voice_label.setWordWrap(True)
        active_voice_label.setStyleSheet("font-weight:700;")

        preset = QComboBox()
        preset.addItems(list(VOICE_TUNING_PRESETS.keys()))
        preset.setCurrentText("Natural")

        speed = QDoubleSpinBox()
        speed.setRange(0.65, 1.40)
        speed.setSingleStep(0.05)
        speed.setDecimals(2)
        speed.setSuffix(" ×")

        depth = QDoubleSpinBox()
        depth.setRange(-6.0, 6.0)
        depth.setSingleStep(0.5)
        depth.setDecimals(2)
        depth.setSuffix(" st")
        depth.setToolTip("Negative values make the finished voice deeper; positive values make it lighter.")

        expression = QDoubleSpinBox()
        expression.setRange(0.10, 1.00)
        expression.setSingleStep(0.05)
        expression.setDecimals(2)
        expression.setToolTip("XTTS temperature. Higher values add variation; lower values are more restrained/stable.")

        repetition = QDoubleSpinBox()
        repetition.setRange(1.0, 10.0)
        repetition.setSingleStep(0.25)
        repetition.setDecimals(2)

        top_p = QDoubleSpinBox()
        top_p.setRange(0.10, 1.00)
        top_p.setSingleStep(0.05)
        top_p.setDecimals(2)

        top_k = QSpinBox()
        top_k.setRange(1, 100)

        conditioning = QSpinBox()
        conditioning.setRange(3, 12)
        conditioning.setSuffix(" sec")

        bass = QDoubleSpinBox()
        bass.setRange(-12.0, 12.0)
        bass.setSingleStep(0.5)
        bass.setDecimals(1)
        bass.setSuffix(" dB")

        treble = QDoubleSpinBox()
        treble.setRange(-12.0, 12.0)
        treble.setSingleStep(0.5)
        treble.setDecimals(1)
        treble.setSuffix(" dB")

        volume = QDoubleSpinBox()
        volume.setRange(-12.0, 6.0)
        volume.setSingleStep(0.5)
        volume.setDecimals(1)
        volume.setSuffix(" dB")

        split_text = QCheckBox("Apollo token-safe auto chunking (recommended)")
        split_text.setChecked(False)

        save_tuning_button = QPushButton("Save Tuning to Selected Voice")
        reset_tuning_button = QPushButton("Reset Selected Voice to Natural")
        default_voice_button = QPushButton("Set Selected as Apollo Default Voice")

        tuning_note = QLabel(
            "Speed and expressiveness are generated inside XTTS. Depth/pitch, bass, treble and final gain "
            "are applied locally with FFmpeg after synthesis. Saved tuning follows the profile everywhere "
            "Apollo uses the active Voice Imprint."
        )
        tuning_note.setWordWrap(True)

        tuning_form.addRow(active_voice_label)
        tuning_form.addRow("Preset", preset)
        tuning_form.addRow("Speed", speed)
        tuning_form.addRow("Depth / pitch", depth)
        tuning_form.addRow("Expressiveness", expression)
        tuning_form.addRow("Repetition control", repetition)
        tuning_form.addRow("Sampling top-p", top_p)
        tuning_form.addRow("Sampling top-k", top_k)
        tuning_form.addRow("Reference detail", conditioning)
        tuning_form.addRow("Bass / warmth", bass)
        tuning_form.addRow("Treble / brightness", treble)
        tuning_form.addRow("Output gain", volume)
        tuning_form.addRow(split_text)
        tuning_form.addRow(tuning_note)
        tuning_form.addRow(save_tuning_button)
        tuning_form.addRow(reset_tuning_button)
        tuning_form.addRow(default_voice_button)
        right_layout.addWidget(tuning_box)

        test_box = QGroupBox("5. Test Apollo Voice")
        test_layout = QVBoxLayout(test_box)
        test_voice_row = QHBoxLayout()
        test_voice_row.addWidget(QLabel("Voice to test"))
        test_voice_combo = QComboBox()
        test_voice_combo.setMinimumWidth(190)
        test_voice_row.addWidget(test_voice_combo, 1)
        choose_test_voice = QPushButton("Select Voice")
        test_voice_row.addWidget(choose_test_voice)
        test_layout.addLayout(test_voice_row)
        test_text = QTextEdit()
        test_text.setPlaceholderText("Alright and hello — Apollo voice test. Science is mostly finding new ways to annoy causality.")
        test_text.setMinimumHeight(96)
        test_text.setMaximumHeight(150)
        test_buttons = QHBoxLayout()
        reference_button = QPushButton("Play Extracted Reference")
        synth_button = QPushButton("Generate New Speech")
        speak_button = QPushButton("Speak New Text")
        stop_button = QPushButton("Stop")
        test_buttons.addWidget(reference_button)
        test_buttons.addWidget(synth_button)
        test_buttons.addWidget(speak_button)
        test_buttons.addWidget(stop_button)
        test_layout.addWidget(test_text)
        test_layout.addLayout(test_buttons)
        right_layout.addWidget(test_box)

        output = QTextEdit()
        output.setReadOnly(True)
        output.setMinimumHeight(170)
        right_layout.addWidget(output, 1)
        splitter.addWidget(right)
        splitter.setSizes([320, 900])

        def selected_id():
            item = profiles_list.currentItem()
            return item.data(Qt.UserRole) if item else None

        def show(value):
            output.setPlainText(json.dumps(value, indent=2, default=str))

        class TrainingSignals(QObject):
            progress = Signal(object)
            finished = Signal(object)
            failed = Signal(str)

        class SynthesisSignals(QObject):
            finished = Signal(object)
            failed = Signal(str)

        training_signals = TrainingSignals(page)
        synthesis_signals = SynthesisSignals(page)
        synthesis_running = {"value": False}
        training_started_monotonic = {"value": None}

        def elapsed_text():
            started = training_started_monotonic.get("value")
            if started is None:
                return "00:00"
            seconds = max(0, int(__import__("time").monotonic() - started))
            return f"{seconds // 60:02d}:{seconds % 60:02d}"

        def apply_training_state(state):
            state = state or {}
            phase = str(state.get("phase", "idle")).replace("_", " ").title()
            message = str(state.get("message", "")).strip()
            training_status_label.setText(
                f"Status: {phase}" + (f" — {message}" if message else "")
            )
            training_progress.setValue(int(state.get("progress", 0) or 0))
            epoch = int(state.get("epoch", 0) or 0)
            total = int(state.get("epochs", 0) or 0)
            loss = state.get("loss")
            loss_text = "—" if loss is None else f"{float(loss):.6f}"
            epoch_text = "—" if total <= 0 else f"{epoch}/{total}"
            training_detail.setText(
                f"Epoch: {epoch_text}   Loss: {loss_text}   Elapsed: {elapsed_text()}"
            )

        training_timer = QTimer(page)
        training_timer.setInterval(500)
        def poll_training_state():
            state = self.run("training_status", {})
            if state.get("running"):
                apply_training_state(state)
        training_timer.timeout.connect(poll_training_state)

        def tuning_from_controls():
            return self._normalise_voice_tuning({
                "speed": speed.value(),
                "pitch_semitones": depth.value(),
                "temperature": expression.value(),
                "repetition_penalty": repetition.value(),
                "top_p": top_p.value(),
                "top_k": top_k.value(),
                "gpt_cond_len": conditioning.value(),
                "enable_text_splitting": split_text.isChecked(),
                "bass_db": bass.value(),
                "treble_db": treble.value(),
                "volume_db": volume.value(),
            })

        def apply_tuning_controls(tuning):
            tuning = self._normalise_voice_tuning(tuning)
            speed.setValue(float(tuning["speed"]))
            depth.setValue(float(tuning["pitch_semitones"]))
            expression.setValue(float(tuning["temperature"]))
            repetition.setValue(float(tuning["repetition_penalty"]))
            top_p.setValue(float(tuning["top_p"]))
            top_k.setValue(int(tuning["top_k"]))
            conditioning.setValue(int(tuning["gpt_cond_len"]))
            split_text.setChecked(bool(tuning["enable_text_splitting"]))
            bass.setValue(float(tuning["bass_db"]))
            treble.setValue(float(tuning["treble_db"]))
            volume.setValue(float(tuning["volume_db"]))

        def update_worker_label():
            status_row = self._xtts_worker_status()
            if status_row.get("running"):
                worker_status_label.setText(f"XTTS worker: running in isolated process PID {status_row.get('pid')}")
            else:
                worker_status_label.setText("XTTS worker: stopped — starts automatically when Apollo speaks")

        def update_active_voice_label():
            active = self._active()
            if active.get("enabled") and active.get("profile_id"):
                active_voice_label.setText(
                    "Apollo default voice: "
                    + str(active.get("profile_name") or active.get("profile_id"))
                    + "  •  Voice Imprint routing ON"
                )
            else:
                active_voice_label.setText(
                    "Apollo default voice: normal Voice Studio  •  Voice Imprint routing OFF"
                )

        def load_selected_tuning(show_status=True):
            pid = selected_id()
            if not pid:
                apply_tuning_controls(VOICE_TUNING_DEFAULTS)
                update_active_voice_label()
                return
            try:
                result = self.run("get_voice_tuning", {"profile_id": pid})
                apply_tuning_controls(result.get("tuning", {}))
                update_active_voice_label()
                if show_status:
                    show(self.run("profile_status", {"profile_id": pid}))
            except Exception as exc:
                QMessageBox.warning(page, "Voice Imprint", str(exc))

        def apply_preset(name):
            apply_tuning_controls(
                VOICE_TUNING_PRESETS.get(str(name), VOICE_TUNING_DEFAULTS)
            )

        def save_selected_tuning():
            pid = selected_id()
            if not pid:
                QMessageBox.information(page, "Voice Imprint", "Select a voice profile first.")
                return
            try:
                result = self.run("set_voice_tuning", {
                    "profile_id": pid,
                    "tuning": tuning_from_controls(),
                })
                show(result)
                update_active_voice_label()
            except Exception as exc:
                QMessageBox.warning(page, "Voice Imprint", str(exc))

        def reset_selected_tuning():
            pid = selected_id()
            if not pid:
                QMessageBox.information(page, "Voice Imprint", "Select a voice profile first.")
                return
            try:
                result = self.run("reset_voice_tuning", {"profile_id": pid})
                apply_tuning_controls(result.get("tuning", {}))
                preset.setCurrentText("Natural")
                show(result)
            except Exception as exc:
                QMessageBox.warning(page, "Voice Imprint", str(exc))

        def refresh(select_id=None):
            # Keep selection and the nearby Test Voice dropdown synchronized.
            selected = select_id or selected_id() or test_voice_combo.currentData()
            result = self.run("list_profiles", {})
            profiles_list.blockSignals(True)
            test_voice_combo.blockSignals(True)
            try:
                profiles_list.clear()
                test_voice_combo.clear()
                test_voice_combo.addItem("Choose a voice profile…", None)
                for row in result["profiles"]:
                    name = str(row["name"])
                    label = ("● " if row.get("active") else "") + f"{name}  |  {row['approved_seconds']:.1f}s  |  signature={'yes' if row['signature_trained'] else 'no'}"
                    item = QListWidgetItem(label)
                    item.setData(Qt.UserRole, row["id"])
                    profiles_list.addItem(item)
                    test_voice_combo.addItem(("● " if row.get("active") else "") + name, row["id"])
                    if row["id"] == selected:
                        profiles_list.setCurrentItem(item)
                ix = test_voice_combo.findData(selected)
                test_voice_combo.setCurrentIndex(ix if ix >= 0 else 0)
            finally:
                profiles_list.blockSignals(False)
                test_voice_combo.blockSignals(False)
            load_selected_tuning(False)
            update_active_voice_label()
            update_worker_label()
            show({"profiles": result, "backend": self.run("backend_status", {})})

        def select_test_voice(index):
            pid = test_voice_combo.itemData(index)
            for row in range(profiles_list.count()):
                item = profiles_list.item(row)
                if item.data(Qt.UserRole) == pid:
                    profiles_list.setCurrentItem(item)
                    return
            profiles_list.clearSelection()

        def selected_voice_changed():
            pid = selected_id()
            test_voice_combo.blockSignals(True)
            try:
                index = test_voice_combo.findData(pid)
                test_voice_combo.setCurrentIndex(index if index >= 0 else 0)
            finally:
                test_voice_combo.blockSignals(False)
            load_selected_tuning(True)

        def rename_selected_profile():
            pid = selected_id()
            if not pid:
                QMessageBox.information(page, "Voice Profiles", "Select a voice to rename.")
                return
            try:
                name = self._load_profile(pid).get("name", pid)
                value, confirmed = QInputDialog.getText(page, "Rename voice", "Voice name:", text=str(name))
                if confirmed:
                    show(self.rename_profile_from_ui(pid, value))
                    refresh(pid)
            except Exception as exc:
                QMessageBox.warning(page, "Rename voice", str(exc))

        def archive_selected_profile():
            pid = selected_id()
            if not pid:
                QMessageBox.information(page, "Voice Profiles", "Select a voice to delete.")
                return
            name = str(self._load_profile(pid).get("name", pid))
            confirm = QMessageBox.question(
                page, "Delete Voice Profile",
                f"Remove '{name}' from Apollo's voice list?\n\n"
                "The voice folder will be moved to a private local Deleted Profiles archive, "
                "so recordings can be recovered. This does not delete the shared XTTS model.",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if confirm != QMessageBox.StandardButton.Yes:
                return
            try:
                show(self.archive_profile_from_ui(pid))
                refresh()
            except Exception as exc:
                QMessageBox.warning(page, "Delete voice", str(exc))

        def move_selected_profile(delta):
            pid = selected_id()
            if not pid:
                return
            ids = self.library.ordered_ids()
            if pid not in ids:
                return
            index = ids.index(pid)
            destination = index + delta
            if destination < 0 or destination >= len(ids):
                return
            ids[index], ids[destination] = ids[destination], ids[index]
            try:
                self.reorder_profiles_from_ui(ids)
                refresh(pid)
            except Exception as exc:
                QMessageBox.warning(page, "Move voice", str(exc))

        def do_browse():
            path, _ = QFileDialog.getOpenFileName(
                page, "Choose voice source", "", "Audio (*.wav *.mp3 *.m4a *.m4b *.aac *.flac *.ogg *.opus *.wma);;All Files (*)"
            )
            if path:
                source_path.setText(path)
                if not profile_name.text().strip():
                    profile_name.setText(Path(path).stem[:50])

        def do_import():
            try:
                result = self.run("import_audio", {
                    "source_path": source_path.text().strip(),
                    "profile_name": profile_name.text().strip(),
                })
                show(result)
                refresh()
            except Exception as exc:
                QMessageBox.warning(page, "Voice Imprint", str(exc))

        def do_build_voice():
            source = source_path.text().strip()
            name = profile_name.text().strip()
            if not source:
                QMessageBox.information(page, "Voice Imprint", "Choose an audio file first.")
                return
            if not name:
                name = Path(source).stem[:50] or "Apollo Voice"
                profile_name.setText(name)

            if self.run("training_status", {}).get("running"):
                QMessageBox.information(page, "Voice Imprint", "Voice training is already running.")
                return

            build_button.setEnabled(False)
            import_button.setEnabled(False)
            train_button.setEnabled(False)
            activate_button.setEnabled(False)
            epochs.setEnabled(False)
            training_started_monotonic["value"] = __import__("time").monotonic()
            training_progress.setValue(1)
            training_status_label.setText("Status: Importing — preparing source audio...")
            output.setPlainText(
                "Apollo is building the voice from your selected audio.\n"
                "This creates the speaker/reference files locally, then trains the acoustic signature."
            )
            training_timer.start()
            requested_epochs = int(epochs.value())

            def worker():
                try:
                    result = self._build_voice_from_audio(
                        source,
                        name,
                        epochs=requested_epochs,
                        activate=True,
                        progress_callback=lambda state: training_signals.progress.emit(state),
                    )
                    training_signals.finished.emit(result)
                except Exception as exc:
                    training_signals.failed.emit(f"{type(exc).__name__}: {exc}")

            threading.Thread(
                target=worker,
                name="ApolloVoiceOneClickBuild",
                daemon=True,
            ).start()

        def do_train():
            pid = selected_id()
            if not pid:
                QMessageBox.information(page, "Voice Imprint", "Select a voice profile first.")
                return

            if self.run("training_status", {}).get("running"):
                QMessageBox.information(page, "Voice Imprint", "Voice training is already running.")
                return

            train_button.setEnabled(False)
            activate_button.setEnabled(False)
            epochs.setEnabled(False)
            training_started_monotonic["value"] = __import__("time").monotonic()
            training_progress.setValue(0)
            training_status_label.setText("Status: Starting training...")
            training_detail.setText(f"Epoch: 0/{epochs.value()}   Loss: —   Elapsed: 00:00")
            training_timer.start()
            output.setPlainText(
                "Voice Imprint training started.\n"
                "The UI will remain responsive while Apollo prepares clips and trains the acoustic network."
            )

            requested_epochs = int(epochs.value())

            def worker():
                try:
                    result = self._train_signature(
                        pid,
                        requested_epochs,
                        progress_callback=lambda state: training_signals.progress.emit(state),
                    )
                    training_signals.finished.emit(result)
                except Exception as exc:
                    training_signals.failed.emit(f"{type(exc).__name__}: {exc}")

            threading.Thread(
                target=worker,
                name=f"ApolloVoiceTrain-{pid}",
                daemon=True,
            ).start()

        def do_activate():
            pid = test_voice_combo.currentData() or selected_id()
            if not pid:
                QMessageBox.information(page, "Voice Imprint", "Select a voice profile first.")
                return
            try:
                self.run("set_voice_tuning", {
                    "profile_id": pid,
                    "tuning": tuning_from_controls(),
                })
                result = self.run("activate_profile", {"profile_id": pid})
                show(result)
                refresh()
                load_selected_tuning(False)
            except Exception as exc:
                QMessageBox.warning(page, "Voice Imprint", str(exc))

        def do_deactivate():
            show(self.run("deactivate_profile", {}))
            refresh()

        def do_model_browse():
            path = QFileDialog.getExistingDirectory(page, "Choose local XTTS model folder", model_dir.text())
            if path:
                model_dir.setText(path)

        def do_install_backend():
            try:
                result = self.run("launch_xtts_installer", {})
                show(result)
                QMessageBox.information(
                    page,
                    "XTTS Installer",
                    "Apollo opened the XTTS installer in a separate console. "
                    "Finish that window, then restart Apollo and check Voice + Engine Readiness.",
                )
            except Exception as exc:
                QMessageBox.warning(page, "XTTS Installer", str(exc))

        def do_find_backend():
            try:
                result = self.run("find_xtts_model", {})
                show(result)
                selected = result.get("selected") if isinstance(result, dict) else None
                if selected:
                    model_dir.setText(str(selected.get("path", "")))
                elif not result.get("found"):
                    QMessageBox.information(
                        page,
                        "XTTS Search",
                        "No local XTTS model containing config.json + model.pth was found. "
                        "Your speaker voice pack can still be built and tested with Play Extracted Reference.",
                    )
            except Exception as exc:
                QMessageBox.warning(page, "XTTS Search", str(exc))

        def do_backend_save():
            try:
                show(self.run("configure_backend", {
                    "backend": "xtts_local",
                    "model_dir": model_dir.text().strip(),
                    "language": language.text().strip() or "en",
                    "device": device.currentText(),
                }))
            except Exception as exc:
                QMessageBox.warning(page, "Voice Imprint", str(exc))

        def do_backend_status():
            show(self.run("voice_readiness", {"profile_id": selected_id()}))

        def do_play_reference():
            pid = selected_id()
            if not pid:
                QMessageBox.information(page, "Voice Imprint", "Select a voice profile first.")
                return
            try:
                show(self.run("play_reference", {"profile_id": pid}))
            except Exception as exc:
                QMessageBox.warning(page, "Voice Imprint", str(exc))

        def set_synthesis_busy(busy):
            synthesis_running["value"] = bool(busy)
            synth_button.setEnabled(not busy)
            speak_button.setEnabled(not busy)
            if busy:
                output.setPlainText(
                    "Generating neural speech in the background...\n"
                    "Apollo should remain responsive while XTTS uses the GPU."
                )

        def synthesis_finished(result):
            set_synthesis_busy(False)
            update_worker_label()
            show(result)

        def synthesis_failed(message):
            set_synthesis_busy(False)
            update_worker_label()
            if "cancelled" in str(message).lower():
                output.setPlainText("Voice generation cancelled.")
                return
            output.setPlainText("Voice synthesis failed:\n" + str(message))
            QMessageBox.warning(page, "Voice Imprint", str(message))

        def do_synth(speak=False):
            if synthesis_running["value"]:
                return
            pid = test_voice_combo.currentData() or selected_id()
            text = test_text.toPlainText().strip()
            action = "speak" if speak else "synthesize"
            args = {
                "text": text,
                "language": language.text().strip() or "en",
                "tuning": tuning_from_controls(),
            }
            if pid:
                args["profile_id"] = pid
            set_synthesis_busy(True)

            def worker():
                try:
                    synthesis_signals.finished.emit(self.run(action, args))
                except Exception as exc:
                    synthesis_signals.failed.emit(f"{type(exc).__name__}: {exc}")

            threading.Thread(target=worker, name="ApolloVoiceSynthesis", daemon=True).start()

        synthesis_signals.finished.connect(synthesis_finished)
        synthesis_signals.failed.connect(synthesis_failed)

        def training_finished(result):
            training_timer.stop()
            state = result.get("training_status")
            if state is None and isinstance(result.get("training"), dict):
                state = result["training"].get("training_status")
            if state is None:
                state = {
                    "phase": "complete",
                    "progress": 100,
                    "message": "Voice build complete.",
                    "epoch": epochs.value(),
                    "epochs": epochs.value(),
                    "loss": None,
                }
            apply_training_state(state)
            show(result)
            build_button.setEnabled(True)
            import_button.setEnabled(True)
            train_button.setEnabled(True)
            activate_button.setEnabled(True)
            epochs.setEnabled(True)
            refresh()

        def training_failed(message):
            training_timer.stop()
            apply_training_state(self.run("training_status", {}))
            build_button.setEnabled(True)
            import_button.setEnabled(True)
            train_button.setEnabled(True)
            activate_button.setEnabled(True)
            epochs.setEnabled(True)
            output.setPlainText("Voice Imprint build/training failed:\n" + str(message))
            QMessageBox.warning(page, "Voice Imprint", str(message))

        training_signals.progress.connect(apply_training_state)
        training_signals.finished.connect(training_finished)
        training_signals.failed.connect(training_failed)

        # Restore visible state if this UI is opened while a training run is active.
        existing_training = self.run("training_status", {})
        if existing_training.get("running"):
            training_started_monotonic["value"] = __import__("time").monotonic()
            train_button.setEnabled(False)
            activate_button.setEnabled(False)
            epochs.setEnabled(False)
            apply_training_state(existing_training)
            training_timer.start()

        browse.clicked.connect(do_browse)
        build_button.clicked.connect(do_build_voice)
        import_button.clicked.connect(do_import)
        refresh_profiles.clicked.connect(lambda: refresh())
        rename_profile_button.clicked.connect(rename_selected_profile)
        archive_profile_button.clicked.connect(archive_selected_profile)
        move_up_button.clicked.connect(lambda: move_selected_profile(-1))
        move_down_button.clicked.connect(lambda: move_selected_profile(1))
        test_voice_combo.currentIndexChanged.connect(select_test_voice)
        choose_test_voice.clicked.connect(do_activate)
        train_button.clicked.connect(do_train)
        activate_button.clicked.connect(do_activate)
        default_voice_button.clicked.connect(do_activate)
        deactivate_button.clicked.connect(do_deactivate)
        preset.currentTextChanged.connect(apply_preset)
        save_tuning_button.clicked.connect(save_selected_tuning)
        reset_tuning_button.clicked.connect(reset_selected_tuning)
        browse_model.clicked.connect(do_model_browse)
        install_backend.clicked.connect(do_install_backend)
        find_backend.clicked.connect(do_find_backend)
        save_backend.clicked.connect(do_backend_save)
        backend_status.clicked.connect(do_backend_status)
        unload_worker_button.clicked.connect(lambda: (show(self.run("unload_xtts_worker", {})), update_worker_label()))
        reference_button.clicked.connect(do_play_reference)
        synth_button.clicked.connect(lambda: do_synth(False))
        speak_button.clicked.connect(lambda: do_synth(True))
        def stop_voice():
            result = self.run("stop_speaking", {})
            output.setPlainText("Stopping voice generation..." if synthesis_running["value"] else "Playback stopped.")
            update_worker_label()
            return result
        stop_button.clicked.connect(stop_voice)
        profiles_list.itemSelectionChanged.connect(selected_voice_changed)
        apply_tuning_controls(VOICE_TUNING_DEFAULTS)
        refresh()
        return page

    def close(self):
        self._stop_playback()
        self._stop_xtts_worker(True)
        self._xtts_model = None
