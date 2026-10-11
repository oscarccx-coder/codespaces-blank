"""Finish XTTS v2 setup without embedding multiline Python in a Windows .bat.

Only configures Apollo's existing voice settings. No model downloads, package
installation, user voice deletion, or global Python changes occur here.
"""
import argparse
import json
import os
from pathlib import Path
import shutil


REQUIRED_MODEL_FILES = ("config.json", "model.pth", "vocab.json")


def configure(settings_file, model_dir, ffmpeg_bin, pins):
    settings_file = Path(settings_file)
    model_dir = Path(model_dir)
    ffmpeg_bin = Path(ffmpeg_bin)
    missing = [name for name in REQUIRED_MODEL_FILES if not (model_dir / name).is_file()]
    if missing:
        raise ValueError("XTTS model incomplete: missing " + ", ".join(missing))
    if not ffmpeg_bin.is_dir():
        raise ValueError("Shared FFmpeg directory not found: " + str(ffmpeg_bin))

    if settings_file.exists():
        try:
            data = json.loads(settings_file.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            raise ValueError(
                "Existing XTTS settings are unreadable. Preserving the original: "
                + str(settings_file)
            ) from exc
        if not isinstance(data, dict):
            raise ValueError("Existing XTTS settings are not a JSON object; original preserved.")
    else:
        data = {}

    data.update({
        "backend": "xtts_local",
        "model_dir": str(model_dir),
        "device": "auto",
        "ffmpeg_shared_bin": str(ffmpeg_bin),
        "runtime_pins": dict(pins),
    })
    data.setdefault("language", "en")
    settings_file.parent.mkdir(parents=True, exist_ok=True)
    # Keep a recoverable copy of existing user preferences before replacing.
    if settings_file.exists():
        shutil.copy2(settings_file, settings_file.with_name(settings_file.name + ".bak"))
    temp = settings_file.with_name(settings_file.name + ".tmp")
    try:
        with temp.open("w", encoding="utf-8", newline="\n") as handle:
            json.dump(data, handle, indent=2)
            handle.write("\n")
        os.replace(temp, settings_file)
    finally:
        if temp.exists():
            temp.unlink()
    print("Apollo XTTS settings updated:", settings_file)
    return data


def main(argv=None):
    parser = argparse.ArgumentParser(description="Configure installed XTTS voice settings")
    parser.add_argument("--settings", required=True)
    parser.add_argument("--model-dir", required=True)
    parser.add_argument("--ffmpeg-bin", required=True)
    for name in ("torch", "torchvision", "torchaudio", "torchcodec", "coqui_tts", "transformers"):
        parser.add_argument("--" + name.replace("_", "-"), required=True)
    args = parser.parse_args(argv)
    pins = {name: getattr(args, name) for name in
            ("torch", "torchvision", "torchaudio", "torchcodec", "coqui_tts", "transformers")}
    configure(args.settings, args.model_dir, args.ffmpeg_bin, pins)


if __name__ == "__main__":
    main()
