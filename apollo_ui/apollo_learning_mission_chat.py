"""Deterministic, explicit owner chat commands for Apollo Learning Missions.

The local LLM may describe missions and use read-only status tools; it cannot
grant itself research permissions. Only the newest real user message may
trigger the commands below.
"""
from __future__ import annotations

import re


def parse_owner_command(text):
    value=" ".join(str(text or "").strip().split())
    if len(value)>500:
        return None
    lower=value.casefold()
    if re.fullmatch(r"(?:show|list|status(?: of)?|what is the progress of)\s+(?:my\s+)?(?:apollo\s+)?learning missions[?.!]?",value,re.I):
        return {"action":"list"}
    if re.fullmatch(r"stop\s+all\s+(?:apollo\s+)?learning missions[.!]?",value,re.I):
        return {"action":"stop_all"}
    match=re.fullmatch(
        r"(stop|pause|resume|status|report|progress)\s+(?:apollo\s+)?(?:learning|research)\s+mission\s+#?(\d{1,6})[?.!]?",
        value,re.I,
    )
    if match:
        action="status" if match.group(1).casefold() in ("report","progress") else match.group(1).casefold()
        return {"action":action,"mission_id":int(match.group(2))}
    # Requiring "public" or "online" makes external research approval explicit;
    # no broad "please learn more" match is permitted.
    pattern=(
        r"(?:apollo[, ]+)?(?:start|begin)\s+(?:a\s+)?"
        r"(?:public|online)\s+(?:research|learning)\s+mission\s+"
        r"(?:about|on|for|:)\s*(.{5,250})"
    )
    match=re.fullmatch(pattern,value,re.I)
    if match:
        topic=match.group(1).strip(" .")
        fixed=re.search(r"\s+for\s+(\d{1,3})\s+(?:research\s+)?(?:batches|cycles)$",topic,re.I)
        continuous=re.search(r"\s+until\s+i\s+(?:say|tell\s+you\s+to)\s+stop$",topic,re.I)
        if fixed:
            mode="fixed"
            steps=int(fixed.group(1))
            topic=topic[:fixed.start()].strip(" .,")
        else:
            mode="until_stop"
            steps=8
            if continuous:
                topic=topic[:continuous.start()].strip(" .,")
        if len(topic)<5 or len(topic)>180:
            return {"action":"invalid","reason":"Research goal must be 5-180 characters."}
        if mode=="fixed" and not 1<=steps<=200:
            return {"action":"invalid","reason":"Choose 1-200 research batches."}
        return {"action":"start","title":topic[:120],"goal":topic,
                "mode":mode,"steps":steps}
    return None


def handle_command(text, module):
    action=parse_owner_command(text)
    if action is None:
        return None
    if action["action"]=="invalid":
        return action["reason"]
    if module is None:
        return "Learning Missions app is not available. Enable it in Settings > Apps."
    name=action["action"]
    try:
        result=module.owner_action(name,**{k:v for k,v in action.items() if k!="action"})
    except (ValueError,KeyError,RuntimeError,PermissionError,OSError) as exc:
        return f"Apollo could not {name} the learning mission: {type(exc).__name__}: {exc}."
    if name=="list":
        if not result:
            return "No learning missions yet. Example: **start public research mission about local AI memory until I say stop**."
        return "**Apollo learning missions:**\n"+"\n".join(
            f"- #{m['id']} **{m['title']}**: {m['state']}, "
            f"{m['completed_steps']} saved batches, {m['failed_steps']} failures"
            for m in result[:20]
        )+"\nUse **status learning mission 1** or **stop learning mission 1**, adjusting the ID."
    if name=="stop_all":
        return ("Graceful stop requested for all active learning missions. "
                "Any in-flight public-source fetch finishes first; closing reports are then saved.")
    if name=="start":
        return (
            f"**Learning mission #{result['id']} started:** {result['title']}\n"
            f"Mode: {result['mode']}. Public-source research was explicitly approved, "
            f"with at most 24 batches/day and 3 pages/batch. "
            "The existing Training tool must also permit web research.\n"
            "Apollo will store actual source files and progress. This is not model-weight training "
            "or an automatic Apollo core change.\n"
            f"Use **status learning mission {result['id']}** or "
            f"**stop learning mission {result['id']}** to finish the current batch and write the report."
        )
    if name in ("stop","pause","resume"):
        return (
            f"Mission #{result['id']}: **{result['state']}**. "
            +("The in-flight fetch, if any, may finish before the closing report is saved."
              if name=="stop" else "This change is recorded in the shared mission database.")
        )
    report=result.get("report") or ""
    latest=result.get("latest") or []
    lines=[
        f"**Learning mission #{result['id']}: {result['title']}**",
        f"State: {result['state']}",
        f"Saved research batches: {result['completed_steps']}",
        f"Failed batches: {result['failed_steps']}",
        f"Unique new referenced URLs: {result.get('new_sources',0)}",
    ]
    if result.get("last_error"):
        lines.append("Last error: "+result["last_error"])
    if latest:
        lines.append("Latest source receipt: "+latest[0]["query"]
                     +" ("+str(latest[0]["fetched_count"])+" pages)")
    if report:
        lines.append("\n"+report[:8000])
    else:
        lines.append("Research is in progress. Source findings remain unverified; open Research Library to inspect the files.")
    return "\n".join(lines)
