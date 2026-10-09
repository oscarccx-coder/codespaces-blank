"""Apollo Circuit Lab: simulator-neutral planning and bounded CRUMB inspection.

All CRUMB interactions are read-only. Never create/edit .cru saves, infer
electrical correctness from XML, or grant the LLM control of the user's desktop.
This module is also importable without Qt, CRUMB or an internet connection.
"""
from collections import Counter
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path
import re
import uuid
import xml.etree.ElementTree as ET

MAX_SAVE_BYTES = 8 * 1024 * 1024
MAX_XML_NODES = 90000
MAX_COMPONENTS = 200
MAX_PARTS = 100
MAX_DESCRIPTION = 4000

EXAMPLES = {
    "led": {
        "name": "Single LED with resistor",
        "supply": "5 V DC bench supply, current limited",
        "parts": [
            {"name": "Red LED", "qty": 1, "notes": "Confirm forward voltage and polarity"},
            {"name": "330 Ω resistor", "qty": 1, "notes": "Series with LED, 1/4 W"},
            {"name": "Breadboard", "qty": 1, "notes": "Use disconnected power while wiring"},
            {"name": "Jumper wires", "qty": 3, "notes": "Inspect polarity before turning on power"},
        ],
        "steps": [
            "Connect bench supply positive to the breadboard positive rail, supply off.",
            "Connect positive rail to a 330 Ω resistor.",
            "Connect resistor's far end to the LED anode (long lead).",
            "Connect LED cathode (short lead or flat side) to the negative rail.",
            "Connect negative rail to supply ground.",
            "Current-limit the supply, then power on and check LED brightness and heating.",
        ],
        "scope": "Low-voltage 5 V DC example only. No mains/battery-charging or safety-critical use.",
    },
    "555_clock": {
        "name": "555 timer astable oscillator (planning template)",
        "supply": "5 V regulated, current limited",
        "parts": [
            {"name": "NE555 timer IC", "qty": 1, "notes": "Check exact device datasheet"},
            {"name": "10 kΩ resistor", "qty": 1, "notes": "RA"},
            {"name": "47 kΩ resistor", "qty": 1, "notes": "RB"},
            {"name": "10 µF capacitor", "qty": 1, "notes": "C, confirm polarity/rating"},
            {"name": "100 nF ceramic capacitor", "qty": 1, "notes": "Bypass across power pins"},
            {"name": "Breadboard + jumpers", "qty": 1, "notes": "Review connections before power"},
        ],
        "steps": [
            "Read the NE555 datasheet and identify VCC, GND, TRIG, THR, DISCH and OUT.",
            "Wire the standard datasheet astable topology with power disconnected.",
            "Place the bypass capacitor close to VCC/GND and observe capacitor polarity.",
            "Check each component and node against the chosen datasheet circuit.",
            "Power from a current-limited 5 V supply and observe OUT on an oscilloscope.",
        ],
        "scope": "Guided planning only: verify pinout, timing equations and wiring with datasheet.",
    },
}


def resistor_for_led(supply_v, forward_v=2.0, target_ma=10.0):
    supply_v, forward_v, target_ma = float(supply_v), float(forward_v), float(target_ma)
    if not all(map(math.isfinite, (supply_v, forward_v, target_ma))):
        raise ValueError("Voltages and LED current must be finite numbers")
    if not (1.0 <= supply_v <= 24.0 and 0.5 <= forward_v < supply_v and 0.1 <= target_ma <= 30.0):
        raise ValueError("Use 1-24 V DC, forward voltage below supply, and 0.1-30 mA.")
    drop = supply_v - forward_v
    minimum = drop / (target_ma / 1000)
    standard = (10, 12, 15, 18, 22, 27, 33, 39, 47, 56, 68, 82)
    choices = [base * 10**exp for exp in range(-1, 6) for base in standard
               if base * 10**exp >= minimum]
    ohms = min(choices)
    current_ma = drop / ohms * 1000
    dissipated_w = (drop**2) / ohms
    return {
        "supply_v": supply_v, "led_forward_v": forward_v,
        "target_ma": target_ma, "minimum_resistance_ohms": round(minimum, 2),
        "suggested_e12_ohms": round(ohms, 2),
        "estimated_current_ma": round(current_ma, 2),
        "resistor_dissipation_w": round(dissipated_w, 4),
        "suggested_resistor_rating_w": 0.25 if dissipated_w <= 0.125 else (
            0.5 if dissipated_w <= 0.25 else 1.0),
        "notice": "Estimate only. Check LED absolute maximum ratings, supply tolerance and wiring."
    }


def inspect_crumb_save(path):
    """Display safe structural metadata only; XML is NOT an electrical simulation.

    Accepts a file explicitly selected by a human in the desktop UI, not an
    arbitrary LLM-provided path. Any format not recognised is shown as unknown.
    """
    file = Path(path)
    if not file.is_file() or file.suffix.lower() != ".cru":
        raise ValueError("Select a local .cru CRUMB circuit-save file.")
    size = file.stat().st_size
    if not 0 < size <= MAX_SAVE_BYTES:
        raise ValueError("CRUMB save is empty or larger than the 8 MiB inspection limit.")
    raw = file.read_bytes()
    if b"<!DOCTYPE" in raw.upper() or b"<!ENTITY" in raw.upper():
        raise ValueError("XML DTD/entity declarations are not allowed.")
    try:
        root = ET.fromstring(raw)
    except ET.ParseError as exc:
        raise ValueError("Selected .cru file is not a supported XML save.") from exc
    counts = Counter()
    node_count = 0
    for item in root.iter():
        node_count += 1
        if node_count > MAX_XML_NODES:
            raise ValueError("CRUMB save has too many XML elements.")
        tag = item.tag.split("}")[-1] if isinstance(item.tag, str) else "unknown"
        # Tag count reveals only XML structure; not a BOM or connected netlist.
        if len(counts) < MAX_COMPONENTS or tag in counts:
            counts[tag[:64]] += 1
    return {
        "format": "CRUMB .cru (XML, structural inspection only)",
        "source": "selected_local_save", "file_name": file.name[:180],
        "size_bytes": len(raw), "sha256": hashlib.sha256(raw).hexdigest(),
        "xml_root": str(root.tag).split("}")[-1][:80],
        "xml_element_count": node_count,
        "xml_tag_frequencies": dict(counts.most_common(30)),
        "compatibility": "unknown until validated against this CRUMB game version",
        "claims": {
            "electrical_wiring_verified": False,
            "simulator_running": False, "supports_live_control": False,
            "project_modified": False,
        },
        "message": (
            "Read-only structural snapshot. Node counts are not components or verified "
            "connections. Open CRUMB yourself to test the simulated circuit."
        ),
    }


class CircuitProjectStore:
    def __init__(self, base_dir):
        self.root = Path(base_dir).resolve() / "storage" / "projects" / "electronics"
        self.root.mkdir(parents=True, exist_ok=True)

    def _file(self, project_id):
        if not isinstance(project_id, str) or not re.fullmatch(r"[a-f0-9]{32}", project_id):
            raise ValueError("Invalid project identifier")
        path = (self.root / (project_id + ".json")).resolve()
        if path.parent != self.root.resolve():
            raise ValueError("Invalid project path")
        return path

    def list_projects(self):
        records = []
        for file in sorted(self.root.glob("*.json")):
            if not re.fullmatch(r"[a-f0-9]{32}\.json", file.name) or file.is_symlink():
                continue
            try:
                obj = json.loads(file.read_text(encoding="utf-8"))
                records.append({"id": obj["id"], "name": obj["name"],
                                "updated_at": obj["updated_at"]})
            except (OSError, ValueError, KeyError, TypeError):
                continue
        return sorted(records, key=lambda x: x["updated_at"], reverse=True)

    def create_project(self, name, description="", template=None):
        name = " ".join(str(name or "").split())
        description = str(description or "").strip()
        if not 1 <= len(name) <= 80 or any(ord(x) < 32 for x in name):
            raise ValueError("Name must be 1-80 printable characters.")
        if len(description) > MAX_DESCRIPTION:
            raise ValueError("Project description too long.")
        if template not in (None, *EXAMPLES):
            raise ValueError("Unknown project template.")
        info = EXAMPLES.get(template) if template else None
        now = datetime.now(timezone.utc).isoformat(timespec="seconds")
        project = {
            "id": uuid.uuid4().hex, "name": name, "description": description,
            "created_at": now, "updated_at": now, "template": template,
            "components": [dict(part) for part in info["parts"]] if info else [],
            "steps": list(info["steps"]) if info else [],
            "notes": "", "state": "design",
            "notice": "Electronic design notes, not a validated circuit or CRUMB save.",
        }
        self._file(project["id"]).write_text(json.dumps(project, indent=2) + "\n", encoding="utf-8")
        return project

    def get_project(self, project_id):
        return json.loads(self._file(project_id).read_text(encoding="utf-8"))

    def set_notes(self, project_id, notes):
        notes = str(notes or "").strip()
        if len(notes) > 8000:
            raise ValueError("Project notes must be 8,000 characters or fewer.")
        obj = self.get_project(project_id)
        obj["notes"] = notes
        obj["updated_at"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
        path = self._file(project_id)
        tmp = path.with_suffix(".json.tmp")
        try:
            tmp.write_text(json.dumps(obj, indent=2) + "\n", encoding="utf-8")
            tmp.replace(path)
        finally:
            tmp.unlink(missing_ok=True)
        return obj
