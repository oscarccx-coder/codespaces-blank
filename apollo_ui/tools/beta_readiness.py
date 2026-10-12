"""Evidence-based beta gate for the Apollo roadmap.

No remote publishing, local user data access, or automatic checkbox changes.
The beta release pipeline invokes this immediately before packaging.
"""
from __future__ import annotations

import argparse
from datetime import date
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
STATUS_FILE = ROOT / "docs" / "architecture" / "beta_status.json"
VERSION_FILE = ROOT / "config.json"
GROUPS = {"R": 14, "U": 14, "L": 15, "V": 15, "A": 14, "F": 14}
GOALS = tuple(f"{prefix}{number:02d}" for prefix, count in GROUPS.items()
              for number in range(1, count + 1))
STATES = {"pending", "built", "blocked", "verified"}
METHODS = {
    "automated", "manual", "real-windows", "real-camera", "real-pi",
    "fault-injection", "privacy-review", "safety-review", "signed-release-dry-run",
}
# Automated CI cannot substitute for these physical, security or failure tests.
SPECIAL_METHODS = {
    "R02": "real-windows", "R03": "privacy-review",
    "R13": "fault-injection", "R14": "signed-release-dry-run",
    "U10": "real-windows", "V01": "real-windows",
    "V06": "real-camera", "V15": "safety-review",
    "F01": "real-pi", "F10": "safety-review",
}


def assess(status_document: dict, version: str, channel: str | None = None) -> dict:
    if not isinstance(status_document, dict) or status_document.get("schema_version") != 1:
        raise ValueError("Expected beta_status.json with schema_version: 1")
    records = status_document.get("goals")
    if not isinstance(records, dict):
        raise ValueError("Expected a goals object")
    unexpected = sorted(set(records) - set(GOALS))
    if unexpected:
        raise ValueError("Unknown roadmap goal IDs: " + ", ".join(unexpected))
    pending, built, blocked, verified = [], [], [], []
    problems = []
    for goal in GOALS:
        item = records.get(goal, {"status": "pending"})
        if not isinstance(item, dict):
            raise ValueError(f"{goal}: status must be an object")
        status = item.get("status", "pending")
        if status not in STATES:
            raise ValueError(f"{goal}: invalid status {status!r}")
        if status == "pending":
            pending.append(goal)
        elif status == "blocked":
            blocked.append(goal)
        elif status == "built":
            built.append(goal)
        else:
            problems_for_goal = []
            if not isinstance(item.get("evidence"), str) or len(item["evidence"].strip()) < 12:
                problems_for_goal.append("specific test/review evidence required")
            if not isinstance(item.get("reviewed_by"), str) or not item["reviewed_by"].strip():
                problems_for_goal.append("reviewed_by required")
            method = item.get("method")
            if method not in METHODS:
                problems_for_goal.append("valid method required")
            required = SPECIAL_METHODS.get(goal)
            if required and method != required:
                problems_for_goal.append("requires method " + required)
            try:
                checked = date.fromisoformat(item["reviewed_on"])
                if checked > date.today():
                    problems_for_goal.append("review cannot be dated in the future")
            except (TypeError, ValueError, KeyError):
                problems_for_goal.append("reviewed_on must be an ISO date")
            if problems_for_goal:
                problems.append(f"{goal}: " + "; ".join(problems_for_goal))
            else:
                verified.append(goal)
    complete = len(verified) == len(GOALS) and not problems
    if channel == "stable" and not str(version).startswith("1."):
        complete = False
        problems.append("Apollo 1.x is the first allowed stable release; Build 8 remains alpha/beta")
    return {
        "channel": channel or "report",
        "version": str(version),
        "total": len(GOALS),
        "verified": len(verified),
        "built_not_verified": len(built),
        "pending": len(pending),
        "blocked": len(blocked),
        "eligible": complete,
        "outstanding_ids": pending + built + blocked,
        "evidence_errors": problems,
    }


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--gate", choices=("beta", "stable"), help="Refuse release until all verified")
    parser.add_argument("--status-file", type=Path, default=STATUS_FILE)
    parser.add_argument("--version-file", type=Path, default=VERSION_FILE)
    args = parser.parse_args(argv)
    status = json.loads(args.status_file.read_text(encoding="utf-8"))
    version = json.loads(args.version_file.read_text(encoding="utf-8"))["version"]
    summary = assess(status, version, args.gate)
    print(json.dumps(summary, indent=2))
    if args.gate and not summary["eligible"]:
        print("RELEASE BLOCKED: complete criteria and attach real evidence before publishing.")
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
