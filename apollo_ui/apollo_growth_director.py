"""Read-only Growth Director: join reasoning evidence, proposed work, and hardware.

No autonomous outreach, code execution, changes to user funds or purchases.
"""
from apollo_growth import GrowthStore, hardware_snapshot
from apollo_reasoning import ReasoningStore


def direction_report(base_dir, include_hardware=False):
    growth = GrowthStore(base_dir)
    reason = ReasoningStore(base_dir)
    try:
        jobs = growth.list_work()
        account = growth.summary()
        learning = reason.progress()
        tasks = reason.due_questions(limit=10)
        steps = []
        if tasks:
            steps.append({
                "priority": 1, "area": "learning",
                "action": "Review a queued research question; identify primary evidence before saving claims.",
                "why": str(len(tasks)) + " questions are due for investigation or review.",
                "permission": "user-selected research only",
            })
        skills = [x for x in learning["skills"] if x["attempts"] >= 3]
        weak = sorted(skills, key=lambda x: x["practice_accuracy_pct"])
        if weak and weak[0]["practice_accuracy_pct"] < 75:
            lowest = weak[0]
            steps.append({
                "priority": 1, "area": "reasoning",
                "action": "Practise " + lowest["skill"] + " with self-review, "
                          "then compare repeated direct vs reviewed scores.",
                "why": "Practice accuracy is " + str(lowest["practice_accuracy_pct"])
                       + "% over " + str(lowest["attempts"]) + " attempts.",
                "permission": "manual benchmark run; local model only",
            })
        proposals = [q for q in jobs if q["status"] == "proposed"]
        approved = [q for q in jobs if q["status"] == "approved"]
        if approved:
            steps.append({
                "priority": 2, "area": "work",
                "action": "Prepare a testable deliverable for an approved work project.",
                "why": str(len(approved)) + " user-approved projects have not been delivered.",
                "permission": "user approvals required for code execution and customer contact",
            })
        elif proposals:
            steps.append({
                "priority": 2, "area": "work",
                "action": "Review project feasibility, deliverable, scope and real customer need.",
                "why": str(len(proposals)) + " draft paid-work proposals exist; no income implied.",
                "permission": "user must approve every work proposal",
            })
        else:
            steps.append({
                "priority": 3, "area": "work",
                "action": "Select one tiny service idea and build a demonstrable sample before advertising.",
                "why": "No proposed work in the Growth Lab queue.",
                "permission": "draft proposal only",
            })
        if account["goals"]:
            steps.append({
                "priority": 3, "area": "hardware",
                "action": "Collect repeatable task accuracy, model tokens/s and VRAM use before buying anything.",
                "why": "Hardware goals exist; available funds are only a manually entered ledger.",
                "permission": "purchase requires owner's decision; no autonomous spending",
            })
        if not skills:
            steps.append({
                "priority": 2, "area": "measurement",
                "action": "Run at least three baseline reasoning questions before evaluating self-review.",
                "why": "No reasoning domain has enough attempts for even preliminary practice feedback.",
                "permission": "explicit local model test",
            })
        machine = hardware_snapshot() if include_hardware else None
        return {
            "title": "Apollo Growth Director",
            "development_state": "planning and measurement; no autonomous business execution",
            "active_research_topics": learning["active_topics"],
            "due_research_questions": len(tasks),
            "reasoning_practice": learning["skills"],
            "draft_work_count": len(proposals),
            "approved_work_count": len(approved),
            "upgrade_fund": account["balance_gbp"],
            "upgrade_goals": account["goals"],
            "hardware": machine,
            "recommended_next": sorted(steps, key=lambda x: x["priority"])[:8],
            "limits": [
                "Benchmark skill improvement is provisional, not proof of general intelligence.",
                "No client search, bank integration or purchases are performed.",
                "Hardware recommendations need measured workload results and verified prices.",
                "No autonomous medical decisions or safety-critical device control.",
            ],
        }
    finally:
        growth.close()
        reason.close()
