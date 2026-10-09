"""Apollo Growth Lab UI and read/propose-only assistant capabilities.

A work proposal cannot contact anyone. The money ledger, client approval,
project delivery and receipt of money are exclusively user-facing GUI actions.
"""
import json
from pathlib import Path

from apollo_growth import GrowthStore, OPPORTUNITY_TEMPLATES, hardware_snapshot, gbp


class Module:
    def __init__(self, context=None):
        self.context = context or {}
        self.base = Path(self.context.get("base_dir") or ".").resolve()
        self.store = GrowthStore(self.base)

    def tools(self):
        return [
            {
                "name": "growth_hardware_snapshot",
                "description": "Read local CPU, RAM and available NVIDIA GPU telemetry. "
                               "Does not buy hardware or estimate an unverified speedup.",
                "parameters": {"type": "object", "properties": {}},
            },
            {
                "name": "growth_opportunity_ideas",
                "description": "Suggest possible work services Apollo could help the user prepare. "
                               "Examples only, not real vacancies, clients, contracts or guaranteed income.",
                "parameters": {"type": "object", "properties": {}},
            },
            {
                "name": "growth_propose_work",
                "description": "Save one DRAFT paid-work idea for the human to review. "
                               "Does not approve, execute, advertise or accept work.",
                "parameters": {"type": "object", "properties": {
                    "title": {"type": "string"},
                    "description": {"type": "string"},
                    "category": {"type": "string"},
                    "estimated_gbp": {"type": "string"},
                }, "required": ["title", "description"]},
            },
            {
                "name": "growth_work_queue",
                "description": "Read locally proposed work and human-marked workflow status.",
                "parameters": {"type": "object", "properties": {}},
            },
            {
                "name": "growth_fund_status",
                "description": "Read the manually entered Apollo upgrade fund and goals. "
                               "This is not a bank balance or a payment account.",
                "parameters": {"type": "object", "properties": {}},
            },
        ]

    def run(self, action, arguments):
        args = arguments or {}
        if action == "growth_hardware_snapshot":
            return hardware_snapshot()
        if action == "growth_opportunity_ideas":
            return {
                "opportunities": list(OPPORTUNITY_TEMPLATES),
                "earnings_guaranteed": False, "clients_found": False,
                "note": "Local brainstorming only; user must secure and approve real work.",
            }
        if action == "growth_propose_work":
            return self.store.propose(
                args.get("title", ""), args.get("description", ""),
                args.get("category", "General"), args.get("estimated_gbp", "0"),
            )
        if action == "growth_work_queue":
            return {"work": self.store.list_work()}
        if action == "growth_fund_status":
            return self.store.summary()
        raise KeyError(action)

    def self_test(self):
        assert {v["name"] for v in self.tools()} == {
            "growth_hardware_snapshot", "growth_opportunity_ideas",
            "growth_propose_work", "growth_work_queue", "growth_fund_status",
        }
        assert not self.run("growth_opportunity_ideas", {})["earnings_guaranteed"]
        return "Read-only metrics and proposals; payments and approvals are UI-only."

    def build_ui(self, parent=None, ui_context=None):
        from PySide6.QtCore import Qt
        from PySide6.QtWidgets import (
            QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
            QTabWidget, QTableWidget, QTableWidgetItem, QHeaderView,
            QInputDialog, QMessageBox, QPlainTextEdit,
        )

        page = QWidget(parent)
        root = QVBoxLayout(page)
        heading = QLabel("Apollo Growth Lab")
        heading.setStyleSheet("font-size: 24px; font-weight: 800;")
        root.addWidget(heading)
        notice = QLabel(
            "Find useful work, fund better hardware, and measure what actually helps. "
            "Apollo drafts proposals but never sends client messages, accepts "
            "contracts, moves money or purchases hardware. All fund entries "
            "are YOUR local records, not a verified bank balance."
        )
        notice.setWordWrap(True)
        root.addWidget(notice)

        tabs = QTabWidget()
        root.addWidget(tabs, 1)

        work_tab = QWidget()
        work_layout = QVBoxLayout(work_tab)
        work_buttons = QHBoxLayout()
        refresh_work = QPushButton("Refresh")
        examples = QPushButton("Work Ideas")
        add_work = QPushButton("Create Draft")
        approve = QPushButton("Approve Selected")
        delivered = QPushButton("Mark Delivered")
        paid = QPushButton("Record Payment")
        archive = QPushButton("Archive")
        for button in (refresh_work, examples, add_work, approve, delivered, paid, archive):
            work_buttons.addWidget(button)
        work_layout.addLayout(work_buttons)
        work_table = QTableWidget(0, 5)
        work_table.setHorizontalHeaderLabels(
            ["ID", "Proposal", "Category", "Potential fee", "State"]
        )
        work_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        work_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        work_table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        work_table.horizontalHeader().setSectionResizeMode(
            1, QHeaderView.ResizeMode.Stretch
        )
        work_layout.addWidget(work_table, 1)
        work_info = QPlainTextEdit()
        work_info.setReadOnly(True)
        work_info.setMinimumHeight(100)
        work_layout.addWidget(work_info)
        tabs.addTab(work_tab, "Paid Work Plans")

        money_tab = QWidget()
        money_layout = QVBoxLayout(money_tab)
        balance = QLabel("Upgrade fund: £0.00")
        balance.setStyleSheet("font-size: 19px; font-weight: 700;")
        money_layout.addWidget(balance)
        fund_buttons = QHBoxLayout()
        refresh_fund = QPushButton("Refresh")
        goal = QPushButton("Set Upgrade Target")
        deposit = QPushButton("Record Deposit")
        withdraw = QPushButton("Record Withdrawal")
        for button in (refresh_fund, goal, deposit, withdraw):
            fund_buttons.addWidget(button)
        money_layout.addLayout(fund_buttons)
        fund_info = QPlainTextEdit()
        fund_info.setReadOnly(True)
        money_layout.addWidget(fund_info, 1)
        tabs.addTab(money_tab, "Upgrade Fund")

        hardware_tab = QWidget()
        hardware_layout = QVBoxLayout(hardware_tab)
        hardware_info = QPlainTextEdit()
        hardware_info.setReadOnly(True)
        hardware_layout.addWidget(QLabel(
            "Read-only hardware snapshot. Plan upgrades after measured Ollama, "
            "VRAM, disk and model speed benchmarks, not guesses."
        ))
        view_hardware = QPushButton("Scan Hardware")
        hardware_layout.addWidget(view_hardware)
        hardware_layout.addWidget(hardware_info, 1)
        tabs.addTab(hardware_tab, "Hardware & Bottlenecks")

        def error(exc):
            QMessageBox.warning(page, "Apollo Growth Lab", str(exc))

        def confirm(title, question):
            return QMessageBox.question(
                page, title, question,
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            ) == QMessageBox.StandardButton.Yes

        def require_selected():
            selected = work_table.selectionModel().selectedRows()
            if not selected:
                raise ValueError("Select a proposed work item first.")
            return int(work_table.item(selected[0].row(), 0).text())

        def require_input(title, prompt, value=""):
            answer, ok = QInputDialog.getText(page, title, prompt, text=value)
            return answer.strip() if ok else None

        def refresh_work_table():
            try:
                items = self.store.list_work()
                work_table.setRowCount(len(items))
                for row, item in enumerate(items):
                    for column, value in enumerate((
                        item["id"], item["title"], item["category"],
                        item["estimate_gbp"], item["status"]
                    )):
                        cell = QTableWidgetItem(str(value))
                        cell.setFlags(cell.flags() & ~Qt.ItemFlag.ItemIsEditable)
                        work_table.setItem(row, column, cell)
                work_info.setPlainText(
                    "Estimated fees are hypothetical. A proposal is not a "
                    "customer booking or confirmed income. Only you can "
                    "approve work, mark delivery and record received funds."
                )
            except (OSError, ValueError) as exc:
                error(exc)

        def show_ideas():
            work_info.setPlainText("\n\n".join(
                f"{item['title']}  [{item['category']}]\n"
                f"Deliverable: {item['deliverable']}\nWhy: {item['why']}"
                for item in OPPORTUNITY_TEMPLATES
            ))

        def add_proposal():
            title = require_input("Work proposal", "What could Apollo help deliver?")
            if not title:
                return
            description = require_input(
                "Deliverables", "What would be handed to a paying customer?"
            )
            if not description:
                return
            estimate = require_input(
                "Estimated fee", "Possible price in GBP (not earned income):", "0"
            )
            if estimate is None:
                return
            try:
                self.store.propose(title, description, "User planned", estimate)
                refresh_work_table()
            except (ValueError, OSError) as exc:
                error(exc)

        def advance(to_status):
            try:
                work_id = require_selected()
                prompt = {
                    "approved": "Have you personally reviewed and authorised this work?",
                    "delivered": "Have you actually completed and delivered the work?",
                    "archived": "Archive this work proposal without deleting its history?",
                }[to_status]
                if not confirm("Confirm Work Status", prompt):
                    return
                self.store.transition_from_ui(work_id, to_status)
                refresh_work_table()
            except (ValueError, KeyError) as exc:
                error(exc)

        def record_paid():
            try:
                work_id = require_selected()
                amount = require_input(
                    "Paid work", "Amount ACTUALLY received in GBP:"
                )
                if amount is None:
                    return
                evidence = require_input(
                    "Manual receipt note", "How did you verify receipt? "
                    "(Avoid personal account numbers.)"
                )
                if not evidence:
                    return
                if not confirm(
                    "Confirm Real Income",
                    "Record this amount as received? Apollo has NOT checked a bank "
                    "account, and this only changes a local tracking ledger."
                ):
                    return
                self.store.record_payment_from_ui(work_id, amount, evidence)
                refresh_work_table()
                refresh_fund_info()
            except (ValueError, KeyError, OSError) as exc:
                error(exc)

        def refresh_fund_info():
            summary = self.store.summary()
            balance.setText("Upgrade fund (manual ledger): " + summary["balance_gbp"])
            lines = [
                "Paid work entered: " + summary["paid_work_recorded_gbp"],
                summary["fund_method"], "",
                "UPGRADE TARGETS"
            ]
            lines.extend(
                f"• {item['title']}: {item['target_gbp']} "
                f"(shortfall {item['shortfall_gbp']})"
                for item in summary["goals"] if item["status"] == "active"
            )
            lines.append("\nRECENT MANUAL ENTRIES")
            lines.extend(
                f"{row['created_at'][:10]}  {row['kind']}: {row['amount_gbp']} "
                f"({row['note']})"
                for row in summary["recent_entries"]
            )
            fund_info.setPlainText("\n".join(lines))

        def add_goal():
            title = require_input("Upgrade target", "What hardware upgrade?")
            if not title:
                return
            amount = require_input(
                "Upgrade target", "Target budget in GBP (research current prices):"
            )
            if amount is None:
                return
            reason = require_input(
                "Upgrade target", "What tested bottleneck would this solve?", ""
            )
            if reason is None:
                return
            try:
                self.store.create_goal_from_ui(title, amount, reason)
                refresh_fund_info()
            except (ValueError, OSError) as exc:
                error(exc)

        def change_balance(kind):
            amount = require_input(
                "Manual upgrade fund entry",
                "Amount in GBP " + ("added:" if kind == "deposit" else "removed:")
            )
            if amount is None:
                return
            note = require_input(
                "Manual upgrade fund entry", "Reason (without account details):"
            )
            if not note:
                return
            if not confirm(
                "Confirm Ledger Change",
                "Record a manual bookkeeping entry only? "
                "No transfer, purchase or payment will occur."
            ):
                return
            try:
                self.store.record_fund_from_ui(kind, amount, note)
                refresh_fund_info()
            except (ValueError, OSError) as exc:
                error(exc)

        def refresh_hardware():
            hardware_info.setPlainText(json.dumps(
                hardware_snapshot(), indent=2
            ))

        refresh_work.clicked.connect(refresh_work_table)
        examples.clicked.connect(show_ideas)
        add_work.clicked.connect(add_proposal)
        approve.clicked.connect(lambda: advance("approved"))
        delivered.clicked.connect(lambda: advance("delivered"))
        paid.clicked.connect(record_paid)
        archive.clicked.connect(lambda: advance("archived"))
        refresh_fund.clicked.connect(refresh_fund_info)
        goal.clicked.connect(add_goal)
        deposit.clicked.connect(lambda: change_balance("deposit"))
        withdraw.clicked.connect(lambda: change_balance("withdrawal"))
        view_hardware.clicked.connect(refresh_hardware)
        refresh_work_table()
        refresh_fund_info()
        return page

    def close(self):
        self.store.close()
