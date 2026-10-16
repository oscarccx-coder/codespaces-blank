"""Owner-controlled Apollo Discovery experiments panel for the existing Foundry.

All candidate model calls run in QRunnable workers, not in the GUI thread.
No candidate can access Foundry tasks, tools, databases or Apollo core.
"""
from __future__ import annotations

from pathlib import Path

from apollo_discovery_campaign import DiscoveryCampaign
from apollo_project_workers import model_from_config


def build_discovery_panel(base, parent=None, on_proposal=None):
    from PySide6.QtCore import QObject, QRunnable, QThreadPool, QTimer, Signal
    from PySide6.QtWidgets import (
        QWidget, QVBoxLayout, QHBoxLayout, QLabel, QComboBox,
        QPushButton, QMessageBox, QPlainTextEdit, QProgressBar, QInputDialog,
    )

    class ResultSignals(QObject):
        finished = Signal(str, object, str)

    class StepJob(QRunnable):
        def __init__(self, root, campaign_id, signals):
            super().__init__()
            self.root, self.campaign_id, self.signals = root, campaign_id, signals

        def run(self):
            store = None
            try:
                store = DiscoveryCampaign(self.root)
                result = store.step(self.campaign_id)
                self.signals.finished.emit(self.campaign_id, result, "")
            except Exception as exc:
                self.signals.finished.emit(
                    self.campaign_id, None, f"{type(exc).__name__}: {exc}"
                )
            finally:
                if store is not None:
                    store.close()

    base = Path(base).resolve()
    page = QWidget(parent)
    page.setObjectName("foundryDiscoveryAlliance")
    layout = QVBoxLayout(page)
    header = QLabel("Discovery Alliance | Controlled Self-Improvement")
    header.setStyleSheet("font-size:16px;font-weight:600")
    header.setWordWrap(True)
    layout.addWidget(header)
    intro = QLabel(
        "Apollo's version of evolution: local answer-specialist recipes compete on "
        "the same fixed math/Python questions; winners may be logically cloned, "
        "repeated failures are retired. Benchmarks are narrow, not general intelligence. "
        "No core edits, production installs, medical actions or real file deletions."
    )
    intro.setWordWrap(True)
    layout.addWidget(intro)

    selector_row = QHBoxLayout()
    campaigns = QComboBox()
    campaigns.setObjectName("discoveryCampaignSelector")
    campaigns.setMinimumWidth(240)
    new_campaign = QPushButton("New Discovery Campaign")
    refresh = QPushButton("Refresh")
    selector_row.addWidget(campaigns, 1)
    selector_row.addWidget(new_campaign)
    selector_row.addWidget(refresh)
    layout.addLayout(selector_row)

    controls = QHBoxLayout()
    start = QPushButton("Authorise + Start")
    start.setObjectName("discoveryAuthoriseStart")
    pause = QPushButton("Pause")
    pause.setObjectName("discoveryPause")
    stop = QPushButton("Stop")
    stop.setObjectName("discoveryStop")
    single = QPushButton("Run One Test")
    single.setObjectName("discoverySingleStep")
    proposal = QPushButton("Send Proposal to Foundry")
    proposal.setObjectName("discoveryQueueProposal")
    for b in (start, pause, stop, single, proposal):
        controls.addWidget(b)
    layout.addLayout(controls)
    status = QLabel("No campaign selected.")
    status.setObjectName("discoveryStatus")
    status.setWordWrap(True)
    layout.addWidget(status)
    progress = QProgressBar()
    progress.setRange(0, 100)
    progress.setValue(0)
    progress.setFormat("%p% of current-generation tests completed")
    layout.addWidget(progress)
    details = QPlainTextEdit()
    details.setReadOnly(True)
    details.setObjectName("discoveryActivity")
    details.setPlaceholderText("Campaign lineage, results and review-only proposals will appear here.")
    layout.addWidget(details, 1)

    active = {"auto": False, "busy": False, "closed": False, "signals": None,
              "selected_id": None}

    def store_call(method, *args, **kwargs):
        store = DiscoveryCampaign(base)
        try:
            return getattr(store, method)(*args, **kwargs)
        finally:
            store.close()

    def selected_id():
        return campaigns.currentData()

    def view_snapshot():
        ident = selected_id()
        active["selected_id"] = ident
        if not ident:
            status.setText("No Discovery campaign selected.")
            details.clear()
            progress.setValue(0)
            return
        try:
            snap = store_call("snapshot", ident)
        except Exception as exc:
            status.setText("Discovery database error: " + str(exc)[:180])
            return
        agents = [a for a in snap["agents"] if a["generation"] == snap["generation"]]
        total = len(agents) * snap["suite_cases"] * snap["repeats"]
        done = sum(a["trials"] for a in agents)
        progress.setValue(round(100 * done / total) if total else 0)
        status.setText(
            f"State: {snap['state']} | Generation: {snap['generation'] + 1}/3 | "
            f"Local model tests: {snap['steps']} | Current stage: {done}/{total}. "
            "Only this screen initiates the next model request."
        )
        log = [
            "EXPERIMENTAL | fixed authored test suite, no independent holdout",
            "Automatic sessions end after a finite budget or authorization expiry.",
            "Closed or restarted Apollo does not auto-restart Discovery.",
            "",
            "Current generation:",
        ]
        for agent in agents:
            name = "PROTECTED BASELINE" if agent["baseline"] else "CHALLENGER"
            log.append(
                f"  {name} {agent['id'][:8]} | {agent['state']} | "
                f"{agent['trials']}/{snap['suite_cases'] * snap['repeats']} trials | "
                f"strategy={agent['recipe']['strategy']} "
                f"reviews={agent['recipe']['review_passes']} | "
                f"parent={(agent['parent_id'] or 'none')[:8]}"
            )
        if snap["proposal"]:
            log.extend(("", "OWNER REVIEW REQUIRED:",
                        snap["proposal"]["summary"],
                        "This is NOT approved for a live Apollo upgrade."))
        log.extend(("", "Recent evidence / decisions:"))
        for item in snap["events"]:
            log.append(f"  {item['at']} [{item['event_type']}] {item['detail']}")
        details.setPlainText("\n".join(log))
        can_run = snap["state"] == "RUNNING"
        start.setEnabled(snap["state"] in ("DRAFT", "PAUSED") and not active["busy"])
        pause.setEnabled(can_run)
        stop.setEnabled(snap["state"] not in ("STOPPED", "COMPLETE"))
        single.setEnabled(can_run and not active["busy"] and not active["auto"])
        proposal.setEnabled(bool(snap["proposal"]) and not active["busy"])

    def reload_campaigns():
        old = selected_id()
        campaigns.blockSignals(True)
        campaigns.clear()
        try:
            rows = store_call("list_campaigns")
        except Exception as exc:
            status.setText("Discovery database error: " + str(exc)[:180])
            rows = []
        for row in rows:
            campaigns.addItem(
                f"{row['title'][:55]} [{row['state']}]",
                row["id"],
            )
        if old:
            index = campaigns.findData(old)
            if index >= 0:
                campaigns.setCurrentIndex(index)
        campaigns.blockSignals(False)
        view_snapshot()

    def new_campaign_action():
        if active["busy"]:
            return
        title, ok = QInputDialog.getText(
            page, "Create Discovery Campaign", "What should Apollo call this experiment?"
        )
        if not ok or not title.strip():
            return
        try:
            ident = store_call("create", title, model_from_config(base))
            reload_campaigns()
            index = campaigns.findData(ident)
            if index >= 0:
                campaigns.setCurrentIndex(index)
        except Exception as exc:
            QMessageBox.warning(page, "Discovery", str(exc)[:500])

    def queue_step():
        if active["busy"] or active["closed"]:
            return
        ident = selected_id()
        if not ident:
            return
        active["busy"] = True
        signals = ResultSignals()
        active["signals"] = signals
        signals.finished.connect(finished_step)
        QThreadPool.globalInstance().start(StepJob(base, ident, signals))
        view_snapshot()

    def finished_step(campaign_id, result, error):
        active["busy"] = False
        active["signals"] = None
        if error:
            active["auto"] = False
            try:
                snap = store_call("snapshot", campaign_id)
                if snap["state"] == "RUNNING":
                    store_call("pause", campaign_id)
            except Exception:
                pass
            if not active["closed"]:
                QMessageBox.warning(page, "Discovery paused after worker error", error[:950])
        if active["closed"]:
            return
        reload_campaigns()
        if result and result.get("state") != "RUNNING":
            active["auto"] = False
        if active["auto"] and selected_id() == campaign_id:
            QTimer.singleShot(0, queue_step)

    def start_action():
        ident = selected_id()
        if not ident or active["busy"]:
            return
        warning = (
            "Authorise a finite local Discovery session?\n\n"
            "The local Ollama GPU will answer dozens of narrow test cases in the "
            "background while Apollo remains open. One model request runs at a time. "
            "This does NOT change Apollo's code, deploy software, access private "
            "data or execute generated programs. Stop/Pause prevents the NEXT test "
            "but an in-flight Ollama request can take up to 110 seconds.\n\n"
            "Sessions expire after two hours and never auto-resume on restart."
        )
        if QMessageBox.question(
            page, "Start Discovery Alliance", warning,
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No
        ) != QMessageBox.Yes:
            return
        try:
            store_call("begin", ident, owner_confirmed=True)
            active["auto"] = True
            reload_campaigns()
            queue_step()
        except Exception as exc:
            QMessageBox.warning(page, "Discovery", str(exc)[:500])

    def pause_action():
        active["auto"] = False
        ident = selected_id()
        if not ident:
            return
        try:
            if store_call("snapshot", ident)["state"] == "RUNNING":
                store_call("pause", ident)
            reload_campaigns()
        except Exception as exc:
            QMessageBox.warning(page, "Discovery", str(exc)[:500])

    def stop_action():
        ident = selected_id()
        if not ident:
            return
        if QMessageBox.question(
            page, "Stop Discovery", "Stop this campaign permanently? Keep all evidence and scores?",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No
        ) != QMessageBox.Yes:
            return
        active["auto"] = False
        try:
            store_call("stop", ident)
            reload_campaigns()
        except Exception as exc:
            QMessageBox.warning(page, "Discovery", str(exc)[:500])

    def proposal_action():
        ident = selected_id()
        if not ident or on_proposal is None:
            return
        snap = store_call("snapshot", ident)
        report = snap.get("proposal")
        if not report:
            return
        warning = (
            "Create an ordinary owner-reviewable Foundry change request from "
            "this narrow test result? This does NOT install or activate an upgrade."
        )
        if QMessageBox.question(
            page, "Request Foundry Review", warning,
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No
        ) != QMessageBox.Yes:
            return
        on_proposal(report["summary"])

    new_campaign.clicked.connect(new_campaign_action)
    refresh.clicked.connect(reload_campaigns)
    campaigns.currentIndexChanged.connect(lambda _: view_snapshot())
    start.clicked.connect(start_action)
    pause.clicked.connect(pause_action)
    stop.clicked.connect(stop_action)
    single.clicked.connect(queue_step)
    proposal.clicked.connect(proposal_action)

    # Closing the page ends approval, not just the visible UI.
    def on_destroyed(*_args):
        active["auto"] = False
        active["closed"] = True
        ident = active["selected_id"]
        if ident:
            try:
                if store_call("snapshot", ident)["state"] == "RUNNING":
                    store_call("pause", ident)
            except Exception:
                pass

    page.destroyed.connect(on_destroyed)
    reload_campaigns()
    return page
