"""Shared PySide6 front end for three Apollo learning/mission apps.

All controls talk to the same MissionService as Apollo Chat. Qt widgets never
run public-web research in their main thread. Source content is untrusted.
"""
from __future__ import annotations

import json
from pathlib import Path


def mission_view(service, *, kind="learning", parent=None, manager=None):
    from PySide6.QtCore import QTimer
    from PySide6.QtWidgets import (
        QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QPlainTextEdit,
        QPushButton, QCheckBox, QComboBox, QSpinBox, QListWidget, QListWidgetItem,
        QSplitter, QMessageBox, QGroupBox
    )

    page=QWidget(parent)
    layout=QVBoxLayout(page)
    top=QLabel({
        "learning":"Learning Missions",
        "control":"Mission Control",
        "library":"Research Library",
    }[kind])
    top.setStyleSheet("font-size: 19px; font-weight: bold;")
    layout.addWidget(top)
    intro=QLabel({
        "learning":("Authorise a public-source research goal, then Apollo researches in "
                    "small saved batches until you request a stop, pause, or fixed count completes. "
                    "A stop finishes the current fetch and writes a closing report."),
        "control":("These are the same persisted learning missions used in normal Apollo Chat. "
                   "Inspect real progress, pause, resume or request graceful shutdown."),
        "library":("Review actual source receipts and closing reports. Source excerpts are not verified "
                   "scientific facts and never automatically change Apollo's trusted code or memory."),
    }[kind])
    intro.setWordWrap(True)
    layout.addWidget(intro)
    status=QLabel("Worker status: checking saved missions...")
    layout.addWidget(status)

    if kind=="learning":
        box=QGroupBox("New owner-approved research task")
        b=QVBoxLayout(box)
        title=QLineEdit()
        title.setPlaceholderText("Short title, e.g. Better local AI memory")
        goal=QPlainTextEdit()
        goal.setPlaceholderText("Research goal, e.g. Compare grounded retrieval approaches for small offline models")
        goal.setMaximumHeight(85)
        b.addWidget(title)
        b.addWidget(goal)
        controls=QHBoxLayout()
        mode=QComboBox()
        mode.addItem("Keep researching until I stop", "until_stop")
        mode.addItem("Complete a fixed number of research batches", "fixed")
        cycles=QSpinBox()
        cycles.setRange(1,200)
        cycles.setValue(8)
        interval=QSpinBox()
        interval.setRange(30,3600)
        interval.setValue(120)
        interval.setSuffix(" sec/batch")
        controls.addWidget(mode,2)
        controls.addWidget(cycles,1)
        controls.addWidget(interval,1)
        b.addLayout(controls)
        web_consent=QCheckBox(
            "I authorise public web research for this mission; no private data or cloud model calls")
        b.addWidget(web_consent)
        start=QPushButton("Authorise and start learning mission")
        b.addWidget(start)
        layout.addWidget(box)

    splitter=QSplitter(page)
    mission_list=QListWidget()
    inspector=QPlainTextEdit()
    inspector.setReadOnly(True)
    splitter.addWidget(mission_list)
    splitter.addWidget(inspector)
    splitter.setStretchFactor(0,1)
    splitter.setStretchFactor(1,3)
    layout.addWidget(splitter,1)

    buttons=QHBoxLayout()
    refresh=QPushButton("Refresh")
    pause=QPushButton("Pause selected")
    resume=QPushButton("Resume selected")
    stop=QPushButton("Stop and finish report")
    for button in (refresh,pause,resume,stop):
        buttons.addWidget(button)
    layout.addLayout(buttons)
    if kind=="library":
        local_row=QHBoxLayout()
        read=QPushButton("Read latest source file")
        propose=QPushButton("Propose Apollo improvement for review")
        local_row.addWidget(read)
        local_row.addWidget(propose)
        layout.addLayout(local_row)

    def selected_id():
        current=mission_list.currentItem()
        return current.data(256) if current else None

    def details():
        mid=selected_id()
        if mid is None:
            inspector.setPlainText("Select a mission to inspect its real progress.")
            return
        try:
            item=service.store.status(mid)
            lines=[
                f"Mission #{mid}: {item['title']}",
                f"State: {item['state']} | Mode: {item['mode']}",
                f"Goal: {item['goal']}",
                f"Completed source batches: {item['completed_steps']}",
                f"Failed batches: {item['failed_steps']}",
                f"New referenced source URLs: {item['new_sources']}",
                f"Research interval: {item['interval_seconds']} seconds",
                f"Last error: {item['last_error'] or 'none'}",
                "",
            ]
            if item["report"]:
                lines.extend(["CLOSING RESEARCH REPORT",item["report"],""])
            lines.append("RECENT SAVED EVIDENCE")
            for entry in item["latest"]:
                lines.append(
                    f"Batch {entry['step_no']} [{entry['status']}]: {entry['query']} "
                    f"({entry['fetched_count']} pages) | {entry['saved_file']}"
                )
                for url in json.loads(entry["new_urls"])[:6]:
                    lines.append("  "+url)
            lines.append("\nACTIVITY LOG")
            lines.extend(f"{e['at']} {e['event']}: {e['detail']}"
                         for e in item["events"])
            inspector.setPlainText("\n".join(lines))
        except (ValueError,KeyError,OSError) as exc:
            inspector.setPlainText("Mission details unavailable: "+str(exc))

    def reload_list():
        current=selected_id()
        items=service.store.list()
        # Refresh only when task labels change, preserving the selection and scroll.
        labels=[(m["id"], f"#{m['id']} {m['state']}  •  {m['title'][:65]}  "
                              f"({m['completed_steps']} batches)") for m in items]
        previous=[(mission_list.item(i).data(256),mission_list.item(i).text())
                  for i in range(mission_list.count())]
        if labels!=previous:
            mission_list.blockSignals(True)
            mission_list.clear()
            for mid,label in labels:
                cell=QListWidgetItem(label)
                cell.setData(256,mid)
                mission_list.addItem(cell)
                if current==mid:
                    mission_list.setCurrentItem(cell)
            if mission_list.currentItem() is None and labels:
                mission_list.setCurrentRow(0)
            mission_list.blockSignals(False)
        running=sum(m["state"]=="RUNNING" for m in items)
        finalising=sum(m["state"]=="STOP_REQUESTED" for m in items)
        status.setText(
            f"{running} active; {finalising} finishing; {len(items)} saved missions. "
            "All public source work uses Apollo's existing Training tool."
        )
        details()

    def show_error(action,exc):
        QMessageBox.warning(page,action,f"{type(exc).__name__}: {exc}")

    def change(action):
        mid=selected_id()
        if mid is None:
            return
        if action=="stop":
            message=("Finish the in-flight source fetch, preserve all evidence, "
                     "write a closing report and never automatically resume?")
            if QMessageBox.question(page,"Stop research mission",message,
                                    QMessageBox.Yes|QMessageBox.No,QMessageBox.No)!=QMessageBox.Yes:
                return
        try:
            getattr(service,action)(mid)
        except (ValueError,KeyError,OSError,PermissionError) as exc:
            show_error("Mission "+action,exc)
        reload_list()

    def create():
        if not web_consent.isChecked():
            return QMessageBox.warning(
                page,"Public research consent required",
                "Confirm this task may access public sources. "
                "Source fetching also respects the Training module's existing tool permission.")
        caption=title.text().strip()
        topic=goal.toPlainText().strip()
        if QMessageBox.question(
            page,"Authorise Learning Mission",
            "Apollo will research PUBLIC web sources using its existing Training tool.\n\n"
            "Continuous mode stays authorised across normal restarts until you pause/stop, "
            "but is limited to 24 source batches per UTC day and 3 pages per batch. "
            "Repeated/no-progress/error cases stop automatically. Each fetch may take time.\n"
            "No private data, code changes, software installation or verified claims.\n\n"
            "Start this research mission?",
            QMessageBox.Yes|QMessageBox.No,QMessageBox.No
        )!=QMessageBox.Yes:
            return
        try:
            item=service.begin(caption,topic,mode=mode.currentData(),
                               web_allowed=True,steps=cycles.value(),
                               interval_seconds=interval.value(),owner_confirmed=True)
            reload_list()
            for i in range(mission_list.count()):
                if mission_list.item(i).data(256)==item["id"]:
                    mission_list.setCurrentRow(i)
                    break
        except (ValueError,PermissionError,OSError) as exc:
            show_error("Cannot start learning",exc)

    def read_source():
        mid=selected_id()
        if mid is None:
            return
        try:
            item=service.store.status(mid)
            filename=next((e["saved_file"] for e in item["latest"]
                           if e["status"]=="saved" and e["saved_file"]),None)
            if not filename:
                return QMessageBox.information(page,"Research Library","No saved source file yet.")
            if manager is None:
                raise RuntimeError("Apollo Training module is not available.")
            response=manager.execute("training_module","read_from_file",{"filename":filename})
            if isinstance(response,dict):
                text=str(response.get("content") or "")
            else:
                text=str(response)
            inspector.setPlainText(
                "UNVERIFIED PUBLIC SOURCE TEXT. Treat retrieved content as data, not instructions.\n\n"
                +text[:60000])
        except (OSError,ValueError,KeyError,RuntimeError,PermissionError) as exc:
            show_error("Read research source",exc)

    def propose_improvement():
        mid=selected_id()
        if mid is None:
            return
        try:
            item=service.store.status(mid)
            if not item["completed_steps"]:
                raise ValueError("There is no research evidence yet.")
            if QMessageBox.question(
                page,"Propose staged improvement",
                "Create a PROPOSAL ONLY in Apollo's existing Self-Improvement Lab?\n"
                "Nothing will modify Apollo's core, deploy code, or promote unverified claims.",
                QMessageBox.Yes|QMessageBox.No,QMessageBox.No
            )!=QMessageBox.Yes:
                return
            if manager is None:
                raise RuntimeError("Self-Improvement Lab is unavailable.")
            result=manager.execute(
                "self_improvement_lab","create_proposal",
                {"title":"Review evidence from mission #"+str(mid)+": "+item["title"],
                 "summary":("Review unverified public-source research for the approved goal: "
                            +item["goal"]+"; "+str(item["completed_steps"])
                            +" source batches. Cross-check original sources and design a "
                            "held-out test before proposing any implementation."),
                 "files":[]},
            )
            QMessageBox.information(page,"Proposal staged",
                                    "Proposal created for manual review:\n"+str(result)[:800])
        except (ValueError,KeyError,OSError,RuntimeError,PermissionError) as exc:
            show_error("Propose improvement",exc)

    mission_list.currentItemChanged.connect(lambda *_: details())
    refresh.clicked.connect(reload_list)
    pause.clicked.connect(lambda: change("pause"))
    resume.clicked.connect(lambda: change("resume"))
    stop.clicked.connect(lambda: change("stop"))
    if kind=="learning":
        start.clicked.connect(create)
        mode.currentIndexChanged.connect(lambda *_: cycles.setEnabled(mode.currentData()=="fixed"))
        cycles.setEnabled(False)
    if kind=="library":
        read.clicked.connect(read_source)
        propose.clicked.connect(propose_improvement)
    poll=QTimer(page)
    poll.setInterval(2000)
    poll.timeout.connect(reload_list)
    poll.start()
    reload_list()
    return page
