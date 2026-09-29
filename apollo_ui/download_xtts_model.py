from __future__ import annotations

import inspect
import os
import sys
from pathlib import Path

MODEL_NAME = "tts_models/multilingual/multi-dataset/xtts_v2"


def main() -> int:
    if len(sys.argv) != 2:
        print("Usage: download_xtts_model.py <download_home>")
        return 2

    download_home = Path(sys.argv[1]).expanduser().resolve()
    download_home.mkdir(parents=True, exist_ok=True)

    os.environ["TTS_HOME"] = str(download_home)
    os.environ["COQUI_TOS_AGREED"] = "1"

    from TTS.utils.manage import ModelManager

    signature = inspect.signature(ModelManager)
    kwargs = {}

    # Different Coqui releases/forks expose slightly different constructor args.
    # Pass only what THIS installed ModelManager actually supports.
    if "progress_bar" in signature.parameters:
        kwargs["progress_bar"] = True
    if "verbose" in signature.parameters:
        kwargs["verbose"] = True

    print("ModelManager signature:", signature)
    print("Using arguments:", kwargs)
    print("TTS_HOME:", download_home)
    print("Downloading:", MODEL_NAME)

    manager = ModelManager(**kwargs)
    result = manager.download_model(MODEL_NAME)
    print("Download result:", result)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
