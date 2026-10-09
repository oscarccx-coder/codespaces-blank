"""Apollo local setup CLI and optional PySide6 wizard.

Usage: python apollo_setup.py diagnose | wizard | backup PATH |
       inspect PATH | restore PATH --yes | profile NAME
"""
from pathlib import Path
import argparse
import json
import sys

BASE = Path(__file__).resolve().parent


def main(argv=None):
    p = argparse.ArgumentParser(description="Apollo Setup & Recovery")
    sub = p.add_subparsers(dest="command", required=True)
    sub.add_parser("wizard")
    diag = sub.add_parser("diagnose")
    diag.add_argument("--deep", action="store_true")
    backup = sub.add_parser("backup")
    backup.add_argument("path")
    inspect = sub.add_parser("inspect")
    inspect.add_argument("path")
    restore = sub.add_parser("restore")
    restore.add_argument("path")
    restore.add_argument("--yes", action="store_true")
    profile = sub.add_parser("profile")
    profile.add_argument("name", choices=["desktop", "laptop", "pi"])
    args = p.parse_args(argv)

    if args.command == "wizard":
        from PySide6.QtWidgets import QApplication
        from apollo_setup_ui import show_setup
        app = QApplication.instance() or QApplication(sys.argv)
        dialog = show_setup(None, BASE)
        return app.exec()
    if args.command == "diagnose":
        from apollo_setup_core import system_checks
        result = system_checks(BASE, deep_voice=args.deep)
    elif args.command == "profile":
        from apollo_setup_core import save_profile
        result = save_profile(BASE, args.name)
    elif args.command == "backup":
        from apollo_backup import make_backup
        result = make_backup(BASE, args.path)
    elif args.command == "inspect":
        from apollo_backup import inspect_backup
        data = inspect_backup(args.path)
        result = {k: v for k, v in data.items() if k != "entries"}
    else:
        from apollo_backup import inspect_backup, restore_backup
        preview = inspect_backup(args.path)
        print(f"Backup: {preview['files']} files, {preview['bytes']} bytes.")
        if not args.yes:
            print("No files changed. Close Apollo and re-run with --yes to restore.")
            return 2
        response = input("Apollo must be CLOSED. Type RESTORE to replace saved data: ")
        if response != "RESTORE":
            print("Cancelled.")
            return 2
        result = restore_backup(BASE, args.path, confirmed=True)
    print(json.dumps(result, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
