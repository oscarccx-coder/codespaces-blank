"""Safe, deterministic routing for ordinary Apollo business-planning chat.

Planning is useful even when The Pile, the web or all tools are offline.
This module does not contact potential clients, alter financial records,
start work, or assume income was received.
"""
from __future__ import annotations

import re
from typing import Any, Mapping, Sequence

# Only an explicit sentence-level command addressed to The Pile may start
# retrieval. Mentions in earlier context, pasted errors or general questions
# about "learning" are NEVER sufficient to invoke its network services.
PILE_LEARN = re.compile(
    r"^\s*(?:please\s+)?(?:learn|study|research|remember|absorb|gain\s+knowledge)\s+"
    r"(?:about\s+)?(?:from\s+)?(?:the\s+)?pile\b", re.I,
)
PILE_SEARCH = re.compile(
    r"^\s*(?:please\s+)?(?:search|query|access|use|look\s+in|look\s+through)\s+"
    r"(?:the\s+)?pile\b", re.I,
)

GROWTH_PATTERNS = (
    r"\b(?:make|earn|generate|bring\s+in)\s+(?:some\s+|more\s+)?(?:money|income|revenue|cash)\b",
    r"\b(?:paid\s+work|paying\s+clients?|moneti[sz](?:e|ation)|side\s+(?:gig|hustle)s?)\b",
    r"\b(?:fund|finance|pay\s+for)\s+(?:your|apollo(?:'s)?|our|the)\s+"
    r"(?:hardware|compute|upgrades?|development)\b",
    r"\b(?:income|revenue)\s+(?:ideas|plan|opportunities|streams)\b",
)
GROWTH_RE = tuple(re.compile(pattern, re.I) for pattern in GROWTH_PATTERNS)


def explicit_pile_command(text: str) -> str | None:
    """Return learn/search for an intentional Pile operation, else None."""
    current = " ".join(str(text or "").split())
    if PILE_LEARN.search(current):
        return "learn"
    if PILE_SEARCH.search(current):
        return "search"
    return None


def wants_growth_advice(text: str) -> bool:
    """Recognise business/funding advice, not a bank balance or price lookup."""
    current = " ".join(str(text or "").split())[:2000]
    if explicit_pile_command(current):
        return False
    return any(regex.search(current) for regex in GROWTH_RE)


# A deliberately small, offline-only fallback if Growth Lab is disabled.
# These are possible deliverables, not claims of real clients or market pricing.
FALLBACK_IDEAS = (
    {"title": "Reusable pre-order and stock tracker", "category": "Business spreadsheet",
     "deliverable": "Custom spreadsheet with validation, reporting, examples and instructions"},
    {"title": "Quote, booking and workflow automation", "category": "Small business automation",
     "deliverable": "Scoped Python tool with tests, usage guide and human review"},
    {"title": "Restaurant event social-content pack", "category": "Content production",
     "deliverable": "Original captions, content calendar and asset briefs for approval"},
    {"title": "Small website issue fix and testing report", "category": "Developer services",
     "deliverable": "Reviewable code fixes, automated tests and handover documentation"},
)


def growth_advice(ideas: Sequence[Mapping[str, Any]] | None = None,
                  fund: Mapping[str, Any] | None = None,
                  *, source: str = "Growth Lab") -> str:
    """Build an honest answer, with no external promises or sales claims."""
    valid = [item for item in (ideas or FALLBACK_IDEAS)
             if isinstance(item, Mapping) and item.get("title") and item.get("deliverable")]
    if not valid:
        valid = list(FALLBACK_IDEAS)
    lines = [
        "I can help **build useful products and services that people might pay for**, "
        "then put a documented proposal into Growth Lab for your approval. "
        "I cannot earn money merely by learning new facts, and I have no authority "
        "to contact customers, accept contracts, move money or buy my own upgrades.",
        "",
        "My strongest starting options:",
    ]
    for i, idea in enumerate(valid[:4], 1):
        title = " ".join(str(idea["title"]).split())[:105]
        deliverable = " ".join(str(idea["deliverable"]).split())[:215]
        lines.append(f"{i}. **{title}**: {deliverable}.")
    lines.extend([
        "",
        "**A practical first experiment:** choose one service, build a reusable "
        "demonstration in Foundry, test it, estimate the hours and running costs, "
        "research actual demand, and agree a fair price. You decide whether to "
        "offer it to real customers. After delivery, only you can mark a payment "
        "as received in Growth Lab.",
        "",
        "**How I'd improve:** keep a record of which proposals become real jobs, "
        "time spent, revisions, customer feedback and verified profit. Retain "
        "the workflows that reliably produce quality work; retire the wasteful "
        "ones. Treat these as business performance measurements, not a survival instinct.",
    ])
    if isinstance(fund, Mapping):
        balance = str(fund.get("balance_gbp", "")).strip()
        if balance:
            lines.append(
                "\n**Upgrade fund:** " + balance
                + " in the *manual Growth Lab ledger*, not a verified bank balance."
            )
        goals = fund.get("goals")
        if isinstance(goals, list) and goals:
            goal = goals[0] if isinstance(goals[0], Mapping) else None
            if goal:
                lines.append(
                    "First recorded hardware goal: "
                    + str(goal.get("title", "Upgrade"))[:100]
                    + " (shortfall " + str(goal.get("shortfall_gbp", "unknown")) + ")."
                )
    lines.append(
        "\nThese are **potential** services, not guaranteed earnings or identified "
        "clients. The Pile dataset is not needed for this planning."
    )
    return "\n".join(lines)
