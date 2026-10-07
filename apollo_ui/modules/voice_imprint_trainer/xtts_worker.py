from __future__ import annotations

import importlib
import importlib.metadata
import json
import os
import sys
import tempfile
import traceback
import wave
from pathlib import Path
from typing import Any, Dict, Optional, Tuple


SAMPLE_RATE = 24000


def _version(name: str) -> Optional[str]:
    try:
        return importlib.metadata.version(name)
    except importlib.metadata.PackageNotFoundError:
        return None


def _path(value: Any) -> Optional[str]:
    if value is None:
        return None
    value = str(value).strip().strip('"')
    return str(Path(value).expanduser()) if value else None


def _first(request: Dict[str, Any], *keys: str) -> Any:
    for key in keys:
        value = request.get(key)
        if value not in (None, "", []):
            return value
    return None


class XTTSEngine:
    """
    Isolated Apollo XTTS engine.

    Heavy imports happen inside this worker rather than Apollo's UI process.
    This prevents a broken TTS/PyTorch install from taking down the whole UI.
    """

    def __init__(self) -> None:
        self.model = None
        self.config = None
        self.torch = None
        self.np = None
        self.device = "cpu"
        self.model_dir: Optional[str] = None
        self._dll_handles = []
        self._voice_cache: Dict[str, Tuple[Any, Any]] = {}

    def _prepare_runtime(self, ffmpeg_shared_bin: str, cpu_threads: int) -> None:
        ffmpeg_shared_bin = _path(ffmpeg_shared_bin) or ""

        if ffmpeg_shared_bin and Path(ffmpeg_shared_bin).exists():
            current = os.environ.get("PATH", "")
            if ffmpeg_shared_bin.lower() not in current.lower():
                os.environ["PATH"] = ffmpeg_shared_bin + os.pathsep + current

            if os.name == "nt" and hasattr(os, "add_dll_directory"):
                try:
                    self._dll_handles.append(os.add_dll_directory(ffmpeg_shared_bin))
                except OSError:
                    pass

        threads = max(1, int(cpu_threads or 4))
        os.environ.setdefault("OMP_NUM_THREADS", str(threads))
        os.environ.setdefault("MKL_NUM_THREADS", str(threads))

    def _import_xtts(self):
        coqui = _version("coqui-tts")
        legacy = _version("TTS")

        # `TTS` (legacy) and `coqui-tts` expose the same top-level TTS namespace.
        # Coexistence can create mixed imports and misleading circular-import errors.
        if legacy is not None:
            state = (
                f"Conflicting legacy TTS package detected ({legacy}) alongside coqui-tts {coqui}."
                if coqui is not None
                else f"Old TTS package detected ({legacy})."
            )
            raise RuntimeError(
                state + " Apollo Voice requires a clean maintained coqui-tts install. "
                "Run: python -m pip uninstall -y TTS coqui-tts && "
                "python -m pip install --no-cache-dir \"coqui-tts>=0.27.5\""
            )

        if coqui is None:
            raise RuntimeError(
                "coqui-tts is not installed in Apollo's XTTS environment. "
                "Run: python -m pip install --no-cache-dir \"coqui-tts>=0.27.5\""
            )

        try:
            # Lazy, ordered imports. Do not import XTTS at Apollo UI startup.
            config_mod = importlib.import_module("TTS.tts.configs.xtts_config")
            model_mod = importlib.import_module("TTS.tts.models.xtts")
            return config_mod.XttsConfig, model_mod.Xtts
        except Exception as exc:
            raise RuntimeError(
                f"XTTS import failed with coqui-tts {coqui}: {exc}. "
                "The XTTS environment probably contains conflicting TTS, "
                "transformers or torch packages."
            ) from exc

    def _choose_device(self, requested: str) -> str:
        requested = (requested or "auto").lower()

        if requested in ("auto", "default"):
            return "cuda" if self.torch.cuda.is_available() else "cpu"

        if requested.startswith("cuda"):
            if not self.torch.cuda.is_available():
                raise RuntimeError("CUDA requested, but PyTorch cannot see CUDA.")
            return requested

        if requested == "cpu":
            return "cpu"

        raise ValueError(f"Unsupported XTTS device: {requested}")

    def load(
        self,
        model_dir: str,
        device: str = "auto",
        ffmpeg_shared_bin: str = "",
        cpu_threads: int = 4,
    ) -> Dict[str, Any]:
        model_dir = _path(model_dir)
        if not model_dir:
            raise ValueError("model_dir is required.")

        root = Path(model_dir)
        if not root.is_dir():
            raise FileNotFoundError(f"XTTS model directory not found: {root}")

        config_file = root / "config.json"
        if not config_file.is_file():
            raise FileNotFoundError(f"Missing XTTS config.json: {config_file}")

        self._prepare_runtime(ffmpeg_shared_bin, cpu_threads)

        self.torch = importlib.import_module("torch")
        self.np = importlib.import_module("numpy")

        try:
            self.torch.set_num_threads(max(1, int(cpu_threads or 4)))
        except Exception:
            pass

        chosen = self._choose_device(device)
        resolved_root = str(root.resolve())

        if (
            self.model is not None
            and self.model_dir == resolved_root
            and self.device == chosen
        ):
            return {
                "ok": True,
                "loaded": True,
                "cached": True,
                "device": self.device,
                "model_dir": self.model_dir,
            }

        XttsConfig, Xtts = self._import_xtts()

        config = XttsConfig()
        config.load_json(str(config_file))

        # Old and new maintained Coqui versions differ here.
        if hasattr(Xtts, "init_from_config"):
            model = Xtts.init_from_config(config)
        else:
            model = Xtts(config)

        model.load_checkpoint(
            config,
            checkpoint_dir=str(root),
            eval=True,
        )

        model.to(chosen)
        try:
            model.eval()
        except Exception:
            pass

        self.model = model
        self.config = config
        self.device = chosen
        self.model_dir = resolved_root
        self._voice_cache.clear()

        return {
            "ok": True,
            "loaded": True,
            "cached": False,
            "device": chosen,
            "model_dir": resolved_root,
            "coqui_tts_version": _version("coqui-tts"),
            "torch_version": getattr(self.torch, "__version__", "unknown"),
        }

    def _validate_reference(self, reference: Any) -> Any:
        if isinstance(reference, (list, tuple)):
            refs = [_path(x) for x in reference]
            refs = [x for x in refs if x]
            if not refs:
                raise ValueError("No valid speaker reference audio supplied.")
            missing = [x for x in refs if not Path(x).is_file()]
            if missing:
                raise FileNotFoundError(
                    "Speaker reference audio not found: " + ", ".join(missing)
                )
            return refs

        ref = _path(reference)
        if not ref:
            raise ValueError("speaker_wav/reference_audio is required.")
        if not Path(ref).is_file():
            raise FileNotFoundError(f"Speaker reference audio not found: {ref}")
        return ref

    def _voice_key(self, reference: Any) -> str:
        refs = reference if isinstance(reference, list) else [reference]
        parts = []
        for item in refs:
            p = Path(item)
            stat = p.stat()
            parts.append(f"{p.resolve()}::{stat.st_size}::{stat.st_mtime_ns}")
        return "||".join(parts)

    def _conditioning(self, reference: Any):
        reference = self._validate_reference(reference)
        key = self._voice_key(reference)

        if key in self._voice_cache:
            return self._voice_cache[key]

        cond = self.model.get_conditioning_latents(audio_path=reference)

        # Keep only one current profile cached to control VRAM/RAM use.
        self._voice_cache.clear()
        self._voice_cache[key] = cond
        return cond

    def _save_wav(self, data: Any, output: Path) -> float:
        arr = self.np.asarray(data, dtype=self.np.float32).reshape(-1)
        if arr.size == 0:
            raise RuntimeError("XTTS returned an empty waveform.")

        arr = self.np.nan_to_num(arr, nan=0.0, posinf=1.0, neginf=-1.0)
        arr = self.np.clip(arr, -1.0, 1.0)
        pcm = (arr * 32767.0).astype(self.np.int16)

        output.parent.mkdir(parents=True, exist_ok=True)

        with wave.open(str(output), "wb") as wav:
            wav.setnchannels(1)
            wav.setsampwidth(2)
            wav.setframerate(SAMPLE_RATE)
            wav.writeframes(pcm.tobytes())

        return float(arr.size) / SAMPLE_RATE

    def synthesize(self, request: Dict[str, Any]) -> Dict[str, Any]:
        text = str(request.get("text", "")).strip()
        if not text:
            raise ValueError("No text supplied to XTTS.")

        model_dir = _first(request, "model_dir", "xtts_model_dir")
        if not model_dir and not self.model_dir:
            raise ValueError("No XTTS model_dir supplied.")

        load_info = self.load(
            str(model_dir or self.model_dir),
            request.get("device", "auto"),
            request.get("ffmpeg_shared_bin", ""),
            request.get("cpu_threads", 4),
        )

        reference = _first(
            request,
            "speaker_wav",
            "reference_audio",
            "reference_wav",
            "voice_reference",
            "reference",
        )
        if reference is None:
            raise ValueError("No speaker reference audio supplied.")

        gpt_cond_latent, speaker_embedding = self._conditioning(reference)

        result = self.model.inference(
            text=text,
            language=str(request.get("language", "en") or "en"),
            gpt_cond_latent=gpt_cond_latent,
            speaker_embedding=speaker_embedding,
            temperature=float(request.get("temperature", 0.75) or 0.75),
            length_penalty=float(request.get("length_penalty", 1.0) or 1.0),
            repetition_penalty=float(
                request.get("repetition_penalty", 2.0) or 2.0
            ),
            top_k=int(request.get("top_k", 50) or 50),
            top_p=float(request.get("top_p", 0.85) or 0.85),
            speed=float(request.get("speed", 1.0) or 1.0),
            enable_text_splitting=True,
        )

        if not isinstance(result, dict) or result.get("wav") is None:
            raise RuntimeError("XTTS returned no wav data.")

        output_name = _first(request, "output_path", "out_path", "wav_path")

        if output_name:
            output = Path(str(output_name)).expanduser()
        else:
            fd, temp_name = tempfile.mkstemp(
                prefix="apollo_xtts_", suffix=".wav"
            )
            os.close(fd)
            output = Path(temp_name)

        duration = self._save_wav(result["wav"], output)

        return {
            "ok": True,
            "output_path": str(output.resolve()),
            "sample_rate": SAMPLE_RATE,
            "duration_seconds": round(duration, 3),
            "device": self.device,
            "model_cached": bool(load_info.get("cached")),
        }


def _send(payload: Dict[str, Any]) -> None:
    print(json.dumps(payload, ensure_ascii=False), flush=True)


def main() -> int:
    engine = XTTSEngine()

    for raw in sys.stdin:
        raw = raw.strip()
        if not raw:
            continue

        try:
            request = json.loads(raw)
            if not isinstance(request, dict):
                raise TypeError("XTTS worker input must be a JSON object.")

            command = str(
                request.get("op", request.get("command", request.get("cmd", "")))
            ).lower().strip()

            # Compatibility with the previous Apollo worker.
            if not command and "text" in request:
                command = "synthesize"

            if command in ("ping", "health", "status"):
                result = {
                    "ok": True,
                    "status": "ready",
                    "model_loaded": engine.model is not None,
                    "device": engine.device,
                    "coqui_tts_version": _version("coqui-tts"),
                    "legacy_tts_version": _version("TTS"),
                }

            elif command == "load":
                result = engine.load(
                    request["model_dir"],
                    request.get("device", "auto"),
                    request.get("ffmpeg_shared_bin", ""),
                    request.get("cpu_threads", 4),
                )

            elif command in ("synthesize", "tts", "speak"):
                result = engine.synthesize(request)

            elif command in ("stop", "shutdown", "quit"):
                _send({
                    "id": request.get("id"),
                    "ok": True,
                    "result": {"shutdown": True},
                })
                break

            else:
                raise ValueError(f"Unknown XTTS worker command: {command!r}")

            _send({
                "id": request.get("id"),
                "ok": True,
                "result": result,
            })

        except Exception as exc:
            trace = traceback.format_exc()
            print(trace, file=sys.stderr, flush=True)
            _send({
                "id": request.get("id") if isinstance(request, dict) else None,
                "ok": False,
                "error": str(exc),
                "error_type": type(exc).__name__,
                "traceback": trace,
            })

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
