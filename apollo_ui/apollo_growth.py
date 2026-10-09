"""Apollo Growth Lab: hardware assessment, user-directed paid-work planning and an
OPTIONAL manual upgrade-fund ledger.

No accounts, payments, invoices, emails, proposals to outside parties or
purchases are initiated by this module. A proposed work item is not a contract
or income. Only explicit local UI methods may approve work or record received
funds, and no money is actually moved.
"""
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from pathlib import Path
import json
import re
import sqlite3
import subprocess
import threading

MAX_ACTIVE_PROPOSALS = 100

OPPORTUNITY_TEMPLATES = (
    {
        "category": "Business spreadsheet",
        "title": "Reusable pre-order and stock tracker",
        "deliverable": "Custom Excel workbook, instructions, example data and review checklist",
        "why": "Build once and adapt for small hospitality businesses",
    },
    {
        "category": "Small business automation",
        "title": "Quote, booking and workflow automation",
        "deliverable": "Client-scoped Python tool with tests, README and human handover",
        "why": "Apollo's existing coding tools can help draft, test and document it",
    },
    {
        "category": "Content production",
        "title": "Restaurant event social-content pack",
        "deliverable": "Client-approved captions, timetable and reusable graphics briefs",
        "why": "Repeatable, low-compute content service; customer approval before posting",
    },
    {
        "category": "Education",
        "title": "Beginner breadboard circuit workbook",
        "deliverable": "Original 5 V circuit lessons with component list, screenshots and checks",
        "why": "Use Circuit Lab and CRUMB for demonstrations; validate circuits manually",
    },
    {
        "category": "Developer services",
        "title": "Small website issue fix and testing report",
        "deliverable": "Scoped code changes, automated tests and a documented handover",
        "why": "Verified coding work can be demonstrated with a small portfolio",
    },
)


def utc_now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def pence(value, *, positive=True):
    """Convert a GBP value without binary float error; reject non-monetary input."""
    if isinstance(value, bool) or value is None:
        raise ValueError("A GBP amount is required.")
    raw = str(value).strip()
    if not re.fullmatch(r"(?:0|[1-9]\d{0,6})(?:\.\d{1,2})?", raw):
        raise ValueError("GBP amount must be 0-9999999.99, with up to two decimals.")
    try:
        amount = (Decimal(raw) * 100).quantize(Decimal("1"), rounding=ROUND_HALF_UP)
    except (InvalidOperation, ValueError) as exc:
        raise ValueError("Invalid GBP amount.") from exc
    pennies = int(amount)
    if positive and pennies <= 0:
        raise ValueError("GBP amount must be greater than zero.")
    return pennies


def gbp(pennies):
    return f"£{Decimal(int(pennies)) / 100:,.2f}"


def normalized_text(value, field="Text", minimum=1, maximum=240):
    text = " ".join(str(value or "").split())
    if not minimum <= len(text) <= maximum or any(ord(ch) < 32 for ch in text):
        raise ValueError(f"{field} must be {minimum}-{maximum} printable characters.")
    return text


def hardware_snapshot():
    """Read-only, best-effort local snapshot, not an upgrade recommendation."""
    import platform
    result = {
        "source": "local-device", "os": platform.system(),
        "architecture": platform.machine(), "cpu_threads": None,
        "ram_total_gb": None, "ram_available_gb": None, "gpu": [],
        "notes": ["One instantaneous snapshot does not identify the performance bottleneck. "
                  "Measure model tokens/s, memory pressure and workloads before buying hardware."],
    }
    try:
        import psutil
        ram = psutil.virtual_memory()
        result.update({
            "cpu_threads": psutil.cpu_count(logical=True),
            "ram_total_gb": round(ram.total / 1024**3, 2),
            "ram_available_gb": round(ram.available / 1024**3, 2),
        })
    except (ImportError, OSError, AttributeError):
        result["notes"].append("psutil not available; CPU/RAM values unknown.")
    try:
        kw = {}
        if platform.system() == "Windows":
            kw["creationflags"] = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        proc = subprocess.run(
            ["nvidia-smi", "--query-gpu=name,memory.total,memory.used",
             "--format=csv,noheader,nounits"],
            capture_output=True, text=True, timeout=4, check=False, **kw,
        )
        if proc.returncode == 0:
            for line in proc.stdout.splitlines()[:8]:
                pieces = [x.strip() for x in line.split(",")]
                if len(pieces) < 3:
                    continue
                try:
                    vram, used = int(float(pieces[1])), int(float(pieces[2]))
                except ValueError:
                    continue
                result["gpu"].append({
                    "name": pieces[0][:120], "vram_total_mib": max(0, vram),
                    "vram_used_mib": max(0, used),
                })
    except (OSError, subprocess.TimeoutExpired):
        result["notes"].append("NVIDIA GPU telemetry not available on this host.")
    return result


class GrowthStore:
    def __init__(self, base_dir):
        root = Path(base_dir).resolve() / "storage" / "databases"
        root.mkdir(parents=True, exist_ok=True)
        self.path = root / "apollo_growth.db"
        self.lock = threading.RLock()
        self.db = sqlite3.connect(str(self.path), check_same_thread=False)
        self.db.row_factory = sqlite3.Row
        with self.db:
            self.db.executescript("""
                CREATE TABLE IF NOT EXISTS work (
                    id INTEGER PRIMARY KEY,
                    title TEXT NOT NULL,
                    category TEXT NOT NULL,
                    description TEXT NOT NULL,
                    estimate_pence INTEGER NOT NULL DEFAULT 0
                        CHECK(estimate_pence >= 0),
                    status TEXT NOT NULL DEFAULT 'proposed'
                        CHECK(status IN ('proposed','approved','delivered','paid','archived')),
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS goals (
                    id INTEGER PRIMARY KEY,
                    title TEXT NOT NULL,
                    target_pence INTEGER NOT NULL CHECK(target_pence > 0),
                    note TEXT NOT NULL DEFAULT '',
                    status TEXT NOT NULL DEFAULT 'active'
                        CHECK(status IN ('active','complete','archived')),
                    created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS ledger (
                    id INTEGER PRIMARY KEY,
                    kind TEXT NOT NULL CHECK(kind IN ('deposit','withdrawal','job_payment')),
                    amount_pence INTEGER NOT NULL CHECK(amount_pence != 0),
                    note TEXT NOT NULL DEFAULT '',
                    work_id INTEGER REFERENCES work(id),
                    created_at TEXT NOT NULL
                );
                CREATE UNIQUE INDEX IF NOT EXISTS one_payment_per_job
                ON ledger(work_id) WHERE kind='job_payment';
            """)

    def close(self):
        with self.lock:
            self.db.close()

    def propose(self, title, description, category="General", estimated_gbp="0"):
        title = normalized_text(title, "Work proposal title", 3, 120)
        desc = normalized_text(description, "Deliverable and scope", 10, 2000)
        category = normalized_text(category, "Category", 2, 80)
        estimate = pence(estimated_gbp, positive=False)
        with self.lock, self.db:
            active = self.db.execute(
                "SELECT COUNT(*) FROM work WHERE status != 'archived'"
            ).fetchone()[0]
            if active >= MAX_ACTIVE_PROPOSALS:
                raise ValueError("Work proposal limit reached. Archive older items first.")
            old = self.db.execute(
                "SELECT id FROM work WHERE lower(title)=lower(?) AND status!='archived'",
                (title,),
            ).fetchone()
            if old:
                return {"created": False, "id": old["id"], "status": "already_proposed",
                        "income_confirmed": False}
            now = utc_now()
            cur = self.db.execute(
                "INSERT INTO work(title,category,description,estimate_pence,"
                "status,created_at,updated_at) VALUES(?,?,?,?,'proposed',?,?)",
                (title, category, desc, estimate, now, now),
            )
            return {"created": True, "id": cur.lastrowid, "status": "proposed",
                    "income_confirmed": False}

    def list_work(self):
        with self.lock:
            rows = self.db.execute(
                "SELECT * FROM work ORDER BY id DESC LIMIT 110"
            ).fetchall()
            return [{**dict(r), "estimate_gbp": gbp(r["estimate_pence"])} for r in rows]

    def transition_from_ui(self, work_id, next_status):
        """User-only UI operation; never exported as an AI tool."""
        transitions = {
            "proposed": {"approved", "archived"},
            "approved": {"delivered", "archived"},
            "delivered": {"archived"},
            "paid": {"archived"},
            "archived": set(),
        }
        with self.lock, self.db:
            row = self.db.execute("SELECT * FROM work WHERE id=?", (int(work_id),)).fetchone()
            if row is None:
                raise KeyError("Unknown work proposal.")
            if next_status not in transitions[row["status"]]:
                raise ValueError(f"Cannot transition from {row['status']} to {next_status}")
            self.db.execute(
                "UPDATE work SET status=?, updated_at=? WHERE id=?",
                (next_status, utc_now(), int(work_id)),
            )
            return {"id": int(work_id), "status": next_status}

    def create_goal_from_ui(self, title, target_gbp, note=""):
        title = normalized_text(title, "Upgrade name", 3, 120)
        note = normalized_text(note, "Reason", 0, 400)
        total = pence(target_gbp)
        with self.lock, self.db:
            cur = self.db.execute(
                "INSERT INTO goals(title,target_pence,note,status,created_at) "
                "VALUES(?,?,?,'active',?)", (title, total, note, utc_now())
            )
            return {"id": cur.lastrowid, "title": title,
                    "target_gbp": gbp(total), "status": "active"}

    def record_fund_from_ui(self, kind, amount_gbp, note):
        if kind not in {"deposit", "withdrawal"}:
            raise ValueError("Only local deposits and withdrawals can be recorded here.")
        amount = pence(amount_gbp)
        note = normalized_text(note, "Ledger note", 4, 240)
        with self.lock, self.db:
            balance = self.db.execute(
                "SELECT COALESCE(SUM(amount_pence),0) FROM ledger"
            ).fetchone()[0]
            if kind == "withdrawal" and amount > balance:
                raise ValueError("Cannot withdraw more than the manually recorded balance.")
            signed = -amount if kind == "withdrawal" else amount
            cur = self.db.execute(
                "INSERT INTO ledger(kind,amount_pence,note,created_at) VALUES(?,?,?,?)",
                (kind, signed, note, utc_now()),
            )
            return {"entry_id": cur.lastrowid, "kind": kind, "balance_gbp": gbp(balance + signed)}

    def record_payment_from_ui(self, work_id, confirmed_received_gbp, note):
        """Record user-verified receipt; never initiates or verifies a bank payment."""
        amount = pence(confirmed_received_gbp)
        note = normalized_text(note, "Payment evidence note", 4, 240)
        with self.lock, self.db:
            job = self.db.execute("SELECT * FROM work WHERE id=?", (int(work_id),)).fetchone()
            if job is None or job["status"] != "delivered":
                raise ValueError("Only delivered work can be marked paid by the user.")
            cur = self.db.execute(
                "INSERT INTO ledger(kind,amount_pence,note,work_id,created_at)"
                " VALUES('job_payment',?,?,?,?)", (amount, note, int(work_id), utc_now()),
            )
            self.db.execute(
                "UPDATE work SET status='paid', updated_at=? WHERE id=?",
                (utc_now(), int(work_id)),
            )
            return {"entry_id": cur.lastrowid, "recorded_gbp": gbp(amount),
                    "income_confirmed_by": "manual_user_entry",
                    "note": "Not independently verified against a bank account."}

    def summary(self):
        with self.lock:
            entries = self.db.execute(
                "SELECT kind,amount_pence,note,created_at FROM ledger "
                "ORDER BY id DESC LIMIT 25"
            ).fetchall()
            balance = self.db.execute(
                "SELECT COALESCE(SUM(amount_pence),0) FROM ledger"
            ).fetchone()[0]
            earned = self.db.execute(
                "SELECT COALESCE(SUM(amount_pence),0) FROM ledger "
                "WHERE kind='job_payment'"
            ).fetchone()[0]
            goals = self.db.execute(
                "SELECT * FROM goals ORDER BY id DESC LIMIT 50"
            ).fetchall()
            statuses = self.db.execute(
                "SELECT status,COUNT(*) AS total FROM work GROUP BY status"
            ).fetchall()
            return {
                "balance_gbp": gbp(balance),
                "paid_work_recorded_gbp": gbp(earned),
                "fund_method": "manual ledger only; no bank integration, funds held or payments executed",
                "goals": [{
                    "id": x["id"], "title": x["title"], "target_gbp": gbp(x["target_pence"]),
                    "shortfall_gbp": gbp(max(0, x["target_pence"] - balance)),
                    "status": x["status"], "note": x["note"],
                } for x in goals],
                "work_counts": {x["status"]: x["total"] for x in statuses},
                "recent_entries": [{
                    "kind": x["kind"], "amount_gbp": gbp(x["amount_pence"]),
                    "note": x["note"], "created_at": x["created_at"]
                } for x in entries],
            }
