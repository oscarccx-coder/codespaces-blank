"""Foundry Interpreter: evidence-first project assessment in natural language.

This module NEVER runs generated code, calls an LLM, grants approval or treats
worker conversation as test evidence. Source results come from an independent
static scan and source-hash-matched Docker test records.
"""
from __future__ import annotations

from datetime import datetime, timezone

TEST_NAMES = {
    "docker-unit": "Python unit tests",
    "docker-ui": "Qt button-to-backend interactions",
    "docker-gui": "GUI startup smoke",
}
STATES = {"todo", "running", "review", "accepted", "blocked"}


def _clean(value, limit=160):
    return " ".join(str(value or "").split())[:limit]


def assess_project(state, static_report, readiness, sandbox_runs, meetings, audit,
                   *, active_operations=0):
    """Make a truthful, small and serialisable assessment of the entire project."""
    if not isinstance(state, dict) or not isinstance(state.get("project"), dict):
        raise ValueError("Foundry Interpreter requires an actual project.")
    project = state["project"]
    pid = int(project["id"])
    tasks = state.get("tasks") or []
    issues = state.get("issues") or []
    counts = {status: 0 for status in STATES}
    role_counts = {}
    pending = []
    blocked_tasks = []
    for task in tasks:
        status = task.get("state")
        if status not in STATES:
            raise ValueError("Unknown Foundry task state")
        counts[status] += 1
        role = _clean(task.get("role"), 30)
        role_counts[role] = role_counts.get(role, 0) + 1
        if status == "review":
            pending.append({"id": int(task["id"]), "title": _clean(task.get("title")),
                            "decision": "Accept or request revisions after inspecting source and tests."})
        elif status == "blocked":
            blocked_tasks.append({"id": int(task["id"]), "title": _clean(task.get("title")),
                                  "reason": _clean(task.get("feedback") or task.get("evidence"), 260)})
    open_issues = [
        {"id": int(issue["id"]), "title": _clean(issue.get("title"))}
        for issue in issues if issue.get("state") != "closed"
    ][:12]
    tests = []
    current_source = readiness.get("source_digest")
    current_valid = isinstance(current_source, str) and len(current_source) == 64
    for kind, label in TEST_NAMES.items():
        # release_readiness checks only source-fingerprint-matched reports and
        # invalidates older passing runs after a failed run on the same source.
        passed = bool(readiness.get(kind.removeprefix("docker-"))) if current_valid else False
        matching = [
            x for x in sandbox_runs if x.get("kind") == kind
            and isinstance(x.get("report"), dict)
            and x["report"].get("source_digest") == current_source
        ] if current_valid else []
        latest = matching[0] if matching else None
        observed = latest.get("status", "not-tested") if latest else "not-tested"
        tests.append({
            "id": kind, "label": label, "status": "passed" if passed else observed,
            "current_source": bool(latest),
            "note": ("Checked in Docker for this revision" if passed else
                     "No passing Docker evidence for the current revision"),
        })
    # The static scanner inventories each Python file it actually parsed.
    # Share filenames/check outcomes only, never arbitrary source content.
    source_files = [
        {"path": _clean(item["check"][7:], 140), "status": _clean(item.get("status"), 24)}
        for item in static_report.get("checks", [])
        if isinstance(item, dict) and isinstance(item.get("check"), str)
        and item["check"].startswith("syntax:")
    ][:60]
    static_status = static_report.get("status", "unavailable")
    if static_status not in ("passed", "failed", "incomplete", "unavailable"):
        static_status = "unavailable"
    app_ready = bool(readiness.get("ready")) and current_valid
    active = min(100, max(0, int(active_operations)))
    blockers = len(blocked_tasks) + len(open_issues)
    if active or counts["running"]:
        status = "work-in-progress"
    elif static_status == "failed" or blockers:
        status = "needs-repair"
    elif not app_ready:
        status = "verification-needed"
    elif pending or counts["todo"]:
        status = "review-needed"
    else:
        status = "ready-for-owner-decision"

    latest_meeting = meetings[0] if meetings else None
    speaker_notes = []
    if latest_meeting:
        for turn in latest_meeting.get("turns", [])[-6:]:
            if isinstance(turn, dict) and turn.get("role") and turn.get("message"):
                speaker_notes.append({
                    "role": _clean(turn["role"], 24),
                    "message": _clean(turn["message"], 450),
                    "classification": "AI worker opinion, not verified evidence",
                })

    actions = []
    if active:
        actions.append("Allow the current operation to finish or refresh the brief after it stops.")
    if static_status == "failed":
        actions.append("Resolve the failing static syntax or UI/backend checks.")
    if open_issues:
        actions.append(f"Resolve {len(open_issues)} open issue(s) through reviewed fix tasks.")
    if blocked_tasks:
        actions.append(f"Review and retry {len(blocked_tasks)} blocked task(s) if appropriate.")
    if not app_ready:
        actions.append("Run Docker unit, Qt-interaction and GUI-startup checks on the current source.")
    if pending:
        actions.append(f"Review {len(pending)} submitted draft(s) and accept or request changes.")
    if counts["todo"]:
        actions.append(f"Complete or explicitly cancel {counts['todo']} pending task(s).")
    if not actions and app_ready:
        actions.append("Inspect the working app yourself; approve the project only if satisfied.")

    done = counts["accepted"]
    total = len(tasks)
    title = _clean(project.get("title"), 100)
    tested = sum(test["status"] == "passed" for test in tests)
    sentences = [
        f"Here's where {title} stands: {done} of {total} tasks have been accepted.",
        f"{len(open_issues)} open issues, {counts['blocked']} blocked tasks and "
        f"{counts['review']} drafts waiting for your review.",
        f"Static code inspection: {static_status}. "
        f"Current-revision Docker checks: {tested} of 3 passed.",
    ]
    if app_ready:
        sentences.append(
            "All three required Docker checks have passed for the current source. "
            "That does not prove visual quality, usability or real-world correctness.")
    else:
        sentences.append("The current application is not yet verified by all three Docker checks.")
    if active:
        sentences.append("A worker or test was still active when this snapshot was taken.")
    sentences.append("Next: " + actions[0])

    return {
        "schema_version": 1,
        "project_id": pid,
        "title": title,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "status": status,
        "project_state": _clean(project.get("state"), 40),
        "task_counts": {**counts, "total": total},
        "role_counts": role_counts,
        "open_issues": open_issues,
        "blocked_tasks": blocked_tasks[:12],
        "awaiting_review": pending[:12],
        "static_status": static_status,
        "source_files": source_files,
        "tests": tests,
        "source_digest": current_source if current_valid else None,
        "source_release_checks_passed": app_ready,
        "active_operations": active,
        "recent_team_conversation": speaker_notes,
        "recent_activity": [
            {"kind": _clean(item.get("kind"), 40), "detail": _clean(item.get("detail"), 170)}
            for item in audit[:8]
        ],
        "owner_decisions": actions[:7],
        "brief": " ".join(sentences),
        "limitations": (
            "This is an offline evidence-based interpretation, not a new test run. "
            "Meetings are unverified agent opinions; only source-hash-matched "
            "Docker results count as execution evidence. The interpreter never "
            "approves code, executes an app or alters an ongoing session."
        ),
    }


def format_brief(report):
    """A readable, human-first debrief for UI and optional TTS consumers."""
    lines = [
        "APOLLO FOUNDRY | PROJECT INTERPRETER",
        report["title"] + " | " + report["status"].replace("-", " "),
        "",
        report["brief"],
        "",
        "What the testers actually checked:",
    ]
    for item in report["tests"]:
        lines.append(f"  {item['label']}: {item['status'].upper()}")
    lines.extend(["", f"Python files inspected: {report.get('static_files_inspected', 0)}"])
    files = report.get("source_files") or []
    if files:
        lines.append("Source check results:")
        lines.extend(f"  {item['path']}: {item['status']}" for item in files[:20])
        if len(files) > 20:
            lines.append(f"  ...and {len(files) - 20} more source files.")
    lines.extend(["", "What needs your attention:"])
    lines.extend(f"  {index}. {action}" for index, action in enumerate(report["owner_decisions"], 1))
    if report["recent_team_conversation"]:
        lines.extend(["", "Recent worker discussion (opinions, not verified facts):"])
        for note in report["recent_team_conversation"][-3:]:
            lines.append(f"  {note['role'].title()}: {note['message']}")
    lines.extend(["", "Evidence note: " + report["limitations"]])
    return "\n".join(lines)[:11000]
