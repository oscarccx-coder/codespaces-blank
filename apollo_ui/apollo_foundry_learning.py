"""Evidence-based coding practice feedback for Apollo Foundry.

This module does not train model weights or execute project code. Only structured,
fingerprinted Docker run outcomes enter the skill ledger; model-written claims
and copied console text are never counted as verified demonstrations.
"""
from __future__ import annotations

import re

SKILLS = {
    "docker-unit": {
        "name": "Python logic and unit testing",
        "advice": "Split logic into small functions, write boundary and negative tests, then run the isolated unit suite.",
        "exercise": "Create a pure Python calculation module with at least three edge-case unit tests.",
    },
    "docker-ui": {
        "name": "PySide6 UI-to-backend wiring",
        "advice": "Trace Qt widget signals into handlers and injected backend methods; keep the foundry.json contract current.",
        "exercise": "Build a button and text input connected to a testable backend with a foundry.json interaction contract.",
    },
    "docker-gui": {
        "name": "Desktop application startup",
        "advice": "Check launcher imports, QApplication lifetime and exception handling; verify startup separately from UI interactions.",
        "exercise": "Create launch.py and a PySide6 window that survives isolated GUI startup checks.",
    },
}

_DIGEST = re.compile(r"^[0-9a-f]{64}$")


def evidence_row(report):
    """Convert a sandbox report to bounded evidence; no log text is retained."""
    kind = report.get("kind")
    if kind not in SKILLS:
        raise ValueError("Unknown coding evaluation kind")
    digest = report.get("source_digest")
    executed = report.get("executed_project_code") is True
    status = report.get("status")
    if (not executed or not isinstance(digest, str) or
            _DIGEST.fullmatch(digest) is None or
            status not in ("passed", "failed", "timeout")):
        return {"kind": kind, "status": "unverified", "source_digest": None}
    return {"kind": kind, "status": status, "source_digest": digest}


def summarize_coding_progress(rows):
    """Count actual tested revisions and evidence-backed repairs by skill.

    A repair requires a failed executed test followed by a passing test of
    DIFFERENT source for the same check. Same-source retries are not learning.
    Unavailable Docker and missing test suites never reduce skill scores.
    """
    groups = {key: [] for key in SKILLS}
    for row in rows:
        kind = row["kind"]
        if kind in groups:
            groups[kind].append(dict(row))
    skills = []
    guidance = []
    for kind, meta in SKILLS.items():
        history = groups[kind]
        verified = [x for x in history if x["status"] in ("passed", "failed", "timeout")
                    and isinstance(x.get("source_digest"), str)
                    and _DIGEST.fullmatch(x["source_digest"])]
        passed = sum(x["status"] == "passed" for x in verified)
        failures = len(verified) - passed
        blocked = len(history) - len(verified)
        repairs = 0
        regressions = 0
        previous_failure = None
        previous_pass = None
        for entry in verified:
            digest = entry["source_digest"]
            if entry["status"] == "passed":
                if previous_failure is not None:
                    if digest != previous_failure:
                        repairs += 1
                    # The failure has now been followed by a successful run.
                    # Same-source pass is a retry, not a coding repair.
                    previous_failure = None
                previous_pass = digest
            else:
                if previous_pass is not None and digest != previous_pass:
                    regressions += 1
                    previous_pass = None
                previous_failure = digest
        last = verified[-1]["status"] if verified else "not-tested"
        skill = {
            "id": kind, "name": meta["name"], "tested_runs": len(verified),
            "passed_runs": passed, "failed_runs": failures,
            "unverified_runs": blocked, "verified_repairs": repairs,
            "detected_regressions": regressions,
            "latest_verified_status": last,
            "pass_rate_percent": round(100 * passed / len(verified)) if verified else None,
            "practice_exercise": meta["exercise"],
        }
        skills.append(skill)
        if not verified:
            guidance.append(f"{meta['name']}: no verified evidence yet. {meta['advice']}")
        elif failures:
            guidance.append(
                f"{meta['name']}: {passed}/{len(verified)} executed checks passed; "
                f"{repairs} later-source repairs recorded. {meta['advice']}")
        else:
            guidance.append(f"{meta['name']}: {passed} executed checks passed. "
                            f"Keep regression tests for every change.")
    rank = {name: order for order, name in enumerate(SKILLS)}
    weakest = sorted(skills, key=lambda x: (
        0 if x["latest_verified_status"] in ("failed", "timeout") else
        1 if not x["tested_runs"] else
        2 if x["failed_runs"] else 3,
        x["pass_rate_percent"] if x["pass_rate_percent"] is not None else 0,
        rank[x["id"]],
    ))
    chosen = weakest[0]
    return {
        "skills": skills,
        "next_practice": {"skill": chosen["name"], "task": chosen["practice_exercise"]},
        "worker_guidance": "\n".join(guidance)[:1800],
        "note": ("Skill estimates use executed Docker checks and source hashes, not "
                 "LLM self-reports. No model-weight training, general intelligence "
                 "gain or full app correctness is implied."),
    }
