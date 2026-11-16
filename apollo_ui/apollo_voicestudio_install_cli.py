"""Command-line front door for the owner-approved VoiceStudio installer.

Double-click the BAT to inspect/downloaded checkout. Installation is not
started until the owner explicitly types INSTALL into this console.
"""
from __future__ import annotations

import argparse
from pathlib import Path
import sys

from apollo_voicestudio_installer import diagnose, guided_install
from apollo_voicestudio_runtime import find_downloaded_checkout


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--path", type=Path, help="Previously downloaded VoiceStudio source folder")
    parser.add_argument("--install", action="store_true", help="Ask for installation consent")
    parser.add_argument("--with-prerequisites", action="store_true",
                        help="Also use WinGet for missing Bun and uv after confirmation")
    args = parser.parse_args(argv)

    base = Path(__file__).resolve().parent
    folder = str(args.path or find_downloaded_checkout(base))
    if not folder:
        print("[STOPPED] No VoiceStudio source checkout detected. Use --path with your downloaded folder.")
        return 2
    try:
        state = diagnose(folder)
    except (OSError, ValueError) as exc:
        print("[STOPPED] VoiceStudio source check failed: " + str(exc))
        return 2
    print("VoiceStudio source: " + state["checkout"])
    print("Bun present:", state["bun"], "| uv present:", state["uv"])
    print("Python backend prepared:", state["backend_venv"])
    if not args.install:
        print("Read-only check complete. Run again with --install to prepare the backend.")
        return 0
    if state["missing"] and not args.with_prerequisites:
        print("[STOPPED] Missing tools: " + ", ".join(state["missing"]) +
              ". Use --with-prerequisites or install the tools manually.")
        return 2
    print("This runs third-party installers and VoiceStudio source setup scripts.")
    print("They can download several gigabytes. Apollo's own environment is not replaced.")
    if input("Type INSTALL to authorise on this PC: ").strip() != "INSTALL":
        print("Cancelled. No installation initiated.")
        return 2
    try:
        result = guided_install(folder, base / "storage" / "logs", approved=True,
                                install_missing=args.with_prerequisites)
    except (RuntimeError, OSError, ValueError, PermissionError) as exc:
        print("[STOPPED] VoiceStudio setup failed: " + str(exc))
        return 1
    print("[PREPARED]", result["checkout"])
    print("Setup log:", result["setup_log"])
    print("Open Voice Centre in Apollo to start and test your new backend.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
