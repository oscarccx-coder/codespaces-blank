"""Qt-free presentation rules for a calm, task-focused Apollo Project Studio UI.

UI state is derived from persisted records; it never grants new permissions.
"""
from __future__ import annotations


def project_metrics(project: dict) -> dict:
    tasks = project.get("tasks") or []
    issues = project.get("issues") or []
    total = len(tasks)
    accepted = sum(t.get("state") == "accepted" for t in tasks)
    running = sum(t.get("state") == "running" for t in tasks)
    review = sum(t.get("state") == "review" for t in tasks)
    blocked = sum(t.get("state") == "blocked" for t in tasks)
    open_issues = sum(i.get("state") != "closed" for i in issues)
    return {
        "total": total,
        "accepted": accepted,
        "running": running,
        "review": review,
        "blocked": blocked,
        "open_issues": open_issues,
        "percent": round(100 * accepted / total) if total else 0,
    }


def task_actions(task: dict | None, project: dict, active_worker: bool = False) -> dict:
    if not task:
        return {"subtask": False, "draft": False, "accept": False,
                "rework": False, "retry": False}
    editable = project.get("project", {}).get("state") != "approved"
    state = task.get("state", "")
    running = any(t.get("state") == "running" for t in project.get("tasks", []))
    return {
        "subtask": editable and task.get("parent_id") is None and state != "accepted",
        "draft": editable and state == "todo" and not running and not active_worker,
        "accept": editable and state == "review",
        "rework": editable and state == "review",
        "retry": editable and state in ("blocked", "accepted", "review") and not active_worker,
    }


def issue_actions(issue: dict | None, project: dict) -> dict:
    if not issue or project.get("project", {}).get("state") == "approved":
        return {"assign": False, "close": False}
    tasks = {t.get("id"): t for t in project.get("tasks", [])}
    fix = tasks.get(issue.get("assigned_task"))
    return {
        "assign": issue.get("state") == "open",
        "close": issue.get("state") == "in_progress"
        and fix is not None and fix.get("state") == "accepted",
    }
