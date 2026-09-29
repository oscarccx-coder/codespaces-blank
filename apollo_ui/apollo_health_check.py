from pathlib import Path
import argparse
import ast
import json
import sys


def check(root):
    root = Path(root).resolve()
    errors = []
    excluded = {"storage", "workspace", "pending_modules", "__pycache__"}
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        rel = path.relative_to(root)
        if any(part in excluded for part in rel.parts):
            continue
        if path.suffix.lower() in {".py", ".pyw"}:
            try:
                ast.parse(path.read_text(encoding="utf-8"), filename=str(rel))
            except Exception as exc:
                errors.append(f"{rel}: {exc}")
    modules = root / "modules"
    if modules.exists():
        for manifest in modules.glob("*/manifest.json"):
            try:
                data = json.loads(manifest.read_text(encoding="utf-8"))
                for required in ("id", "name", "entrypoint", "class"):
                    if not str(data.get(required, "")).strip():
                        raise ValueError(f"missing {required}")
            except Exception as exc:
                errors.append(f"{manifest.relative_to(root)}: {exc}")
    try:
        json.loads((root / "config.json").read_text(encoding="utf-8"))
    except Exception as exc:
        errors.append(f"config.json: {exc}")
    return errors


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", default=".")
    args = parser.parse_args()
    errors = check(args.root)
    if errors:
        print("Apollo health check FAILED")
        for error in errors:
            print(error)
        raise SystemExit(1)
    print("Apollo health check PASS")
