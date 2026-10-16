"""Explicit owner-approved local preview for reviewed Foundry project source.

This is NOT a sandbox. Only the user-facing UI may call this helper; AI tools
and automatic workers must never start generated code on the host.
"""
from __future__ import annotations

from pathlib import Path

from apollo_foundry_checks import scan_project


def prepare_local_preview(project_folder):
    """Validate the launch target and rerun static checks before user consent.

    Returns an absolute launch.py path. This does NOT make the code safe:
    generated Python will retain the current Windows user's permissions.
    """
    root = Path(project_folder)
    if not root.is_dir() or root.is_symlink():
        raise ValueError("Project workspace is missing or linked elsewhere.")
    root = root.resolve()
    launcher = root / "launch.py"
    if launcher.is_symlink() or not launcher.is_file():
        raise ValueError("A regular project-local launch.py is required.")
    if launcher.resolve().parent != root:
        raise ValueError("Launcher must stay in the project workspace.")
    report = scan_project(root)
    if report["status"] != "passed":
        raise ValueError(
            "Static checks must pass before a local preview. "
            "Fix the generated files and UI/backend contract first. "
            f"Current result: {report['status']}."
        )
    return launcher
