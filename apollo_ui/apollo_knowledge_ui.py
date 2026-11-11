"""Qt browser for the local knowledge nodes. Imported lazily by Memory Bank."""
import json
import math
from pathlib import Path


def knowledge_view(bank, parent=None):
    from PySide6.QtCore import Qt, QTimer
    from PySide6.QtGui import QColor, QPen, QBrush
    from PySide6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
        QPushButton, QComboBox, QTreeWidget, QTreeWidgetItem, QListWidget,
        QListWidgetItem, QTextBrowser, QSplitter, QInputDialog, QMessageBox,
        QFileDialog, QGraphicsScene, QGraphicsView, QGraphicsRectItem, QHeaderView)
    from apollo_knowledge_nodes import KINDS, RELATIONS

    page = QWidget(parent)
    layout = QVBoxLayout(page)
    layout.addWidget(QLabel("Knowledge Nodes — sections, topics and linked memories"))
    hint = QLabel("Tags and memory types organise automatically. Confirmed links can help recall; a link does not prove a fact.")
    hint.setWordWrap(True)
    layout.addWidget(hint)
    controls = QHBoxLayout()
    search = QLineEdit(); search.setPlaceholderText("Filter nodes by name")
    kind = QComboBox(); kind.addItem("All types", "")
    for value in KINDS:
        kind.addItem(value.title(), value)
    refresh_btn = QPushButton("Refresh")
    create_btn = QPushButton("New node")
    controls.addWidget(search, 1); controls.addWidget(kind)
    controls.addWidget(refresh_btn); controls.addWidget(create_btn)
    layout.addLayout(controls)
    split = QSplitter(Qt.Horizontal)
    tree = QTreeWidget(); tree.setHeaderLabels(["Node", "Memories"])
    tree.header().setSectionResizeMode(0, QHeaderView.Stretch)
    tree.header().setSectionResizeMode(1, QHeaderView.ResizeToContents)
    tree.setObjectName("knowledge_nodes_tree")
    split.addWidget(tree)
    centre = QWidget(); mid = QVBoxLayout(centre)
    mid.addWidget(QLabel("Memories in selected node"))
    memories = QListWidget(); memories.setObjectName("knowledge_node_memories")
    mid.addWidget(memories)
    row = QHBoxLayout()
    attach_btn = QPushButton("Link memory")
    detach_btn = QPushButton("Unlink memory")
    row.addWidget(attach_btn); row.addWidget(detach_btn); mid.addLayout(row)
    mid.addWidget(QLabel("Connections • select one to review"))
    edges = QListWidget(); mid.addWidget(edges)
    row = QHBoxLayout()
    connect_btn = QPushButton("Connect nodes")
    confirm_btn = QPushButton("Confirm link")
    dismiss_btn = QPushButton("Dismiss link")
    for button in (connect_btn, confirm_btn, dismiss_btn):
        row.addWidget(button)
    mid.addLayout(row)
    split.addWidget(centre)
    right = QWidget(); rhs = QVBoxLayout(right)
    scene = QGraphicsScene(page)
    graph = QGraphicsView(scene); graph.setMinimumHeight(200)
    graph.setObjectName("knowledge_node_map")
    rhs.addWidget(graph, 1)
    details = QTextBrowser(); details.setObjectName("knowledge_node_details")
    rhs.addWidget(details, 1)
    export_btn = QPushButton("Export selected node as Markdown")
    rhs.addWidget(export_btn)
    split.addWidget(right)
    split.setSizes([230, 350, 450]); layout.addWidget(split, 1)
    state = {"node_id": None, "data": None, "nodes": []}

    def guarded(fn):
        def call(*_):
            try:
                fn()
            except (ValueError, KeyError, OSError) as exc:
                QMessageBox.warning(page, "Knowledge nodes", str(exc))
        return call

    def refresh():
        selected_id = state["node_id"]
        state["nodes"] = bank.list_knowledge_nodes(search.text(), kind.currentData(), 1000)
        tree.blockSignals(True)
        tree.clear()
        items = {}
        for node in state["nodes"]:
            item = QTreeWidgetItem([f"{node['title']} ({node['kind']})", str(node["memory_count"])])
            item.setData(0, Qt.UserRole, node["id"])
            items[node["id"]] = item
        for node in state["nodes"]:
            item = items[node["id"]]
            parent_item = items.get(node["parent_id"])
            if parent_item is None:
                tree.addTopLevelItem(item)
            else:
                parent_item.addChild(item)
        tree.expandAll()
        selected = items.get(selected_id)
        if selected is None and tree.topLevelItemCount():
            selected = tree.topLevelItem(0)
        if selected:
            tree.setCurrentItem(selected)
            tree.blockSignals(False)
            tree_selected()
        else:
            tree.blockSignals(False)
            state.update(node_id=None, data=None)
            memories.clear(); edges.clear(); scene.clear(); details.clear()

    def select_node(node_id):
        state["node_id"] = node_id
        def walk(item):
            if item.data(0, Qt.UserRole) == node_id:
                tree.setCurrentItem(item)
                return True
            return any(walk(item.child(i)) for i in range(item.childCount()))
        if not any(walk(tree.topLevelItem(i)) for i in range(tree.topLevelItemCount())):
            show_node(node_id)

    class MapNode(QGraphicsRectItem):
        def __init__(self, node_id, x, y, selected=False):
            super().__init__(x, y, 150, 44)
            self.node_id = node_id
            self.setBrush(QBrush(QColor("#164b4b" if selected else "#25364b")))
            self.setPen(QPen(QColor("#64e5ce")))
        def mousePressEvent(self, event):
            node_id = self.node_id
            QTimer.singleShot(0, lambda: select_node(node_id))
            event.accept()

    def draw_map(data):
        scene.clear()
        node = data["node"]
        positions = {node["id"]: (0, 0, node["title"])}
        neighbours = {}
        for edge in data["edges"]:
            other_id = edge["object_id"] if edge["subject_id"] == node["id"] else edge["subject_id"]
            neighbours[other_id] = edge["object"] if edge["subject_id"] == node["id"] else edge["subject"]
        for i, (node_id, title) in enumerate(list(neighbours.items())[:6]):
            angle = 2 * math.pi * i / max(1, min(len(neighbours), 6))
            positions[node_id] = (240 * math.cos(angle), 135 * math.sin(angle), title)
        for edge in data["edges"]:
            if edge["subject_id"] not in positions or edge["object_id"] not in positions:
                continue
            sx, sy, _ = positions[edge["subject_id"]]; ox, oy, _ = positions[edge["object_id"]]
            pen = QPen(QColor("#64e5ce" if edge["status"] == "confirmed" else "#a0a7b5"))
            if edge["status"] == "suggested":
                pen.setStyle(Qt.DashLine)
            scene.addLine(sx + 75, sy + 22, ox + 75, oy + 22, pen)
        for node_id, (x, y, title) in positions.items():
            rect = MapNode(node_id, x, y, node_id == node["id"])
            rect.setToolTip(title); scene.addItem(rect)
            text = scene.addText(title[:20] + ("…" if len(title) > 20 else ""))
            text.setDefaultTextColor(QColor("#effffa")); text.setPos(x + 5, y + 10)
            # Let the rectangle receive clicks even on its label.
            text.setAcceptedMouseButtons(Qt.NoButton)
        graph.fitInView(scene.itemsBoundingRect().adjusted(-10, -10, 10, 10), Qt.KeepAspectRatio)

    def show_node(node_id):
        data = bank.inspect_knowledge_node(node_id, 200)
        state.update(node_id=node_id, data=data)
        memories.clear(); edges.clear()
        for memory in data["memories"]:
            item = QListWidgetItem(f"{memory['name']} [memory:{memory['id']}]\n{memory['source'] or 'Local'}")
            item.setData(Qt.UserRole, memory); memories.addItem(item)
        for edge in data["edges"]:
            item = QListWidgetItem(f"{edge['subject']} → {edge['relation']} → {edge['object']}\n{edge['status']} • {edge['source']}")
            item.setData(Qt.UserRole, edge); edges.addItem(item)
        node = data["node"]
        details.setPlainText(f"{node['title']}\nType: {node['kind']}\n{node['description']}\n\nShowing up to 200 memories and 200 connections.")
        draw_map(data)
        if memories.count():
            memories.setCurrentRow(0)

    def tree_selected():
        item = tree.currentItem()
        if item:
            show_node(item.data(0, Qt.UserRole))

    def memory_selected():
        item = memories.currentItem()
        if not item:
            return
        data = item.data(Qt.UserRole)
        history = bank.memory_history(data["id"])
        details.setPlainText(
            f"[memory:{data['id']}] {data['name']}\nType: {data['memory_type']}\n"
            f"Source: {data['source']} {data['source_ref']}\nUpdated: {data['updated_at']}\n"
            f"Nodes: {', '.join(n['title'] for n in data['nodes'])}\n\n{data['content'][:12000]}\n\n"
            + ("Previous versions:\n" + "\n\n".join(
                f"{r['replaced_at']} • {r['source']} {r['source_ref']}\n{r['content'][:2000]}" for r in history[:5])
               if history else "No corrections recorded since knowledge nodes were enabled."))

    def new_node():
        title, ok = QInputDialog.getText(page, "New knowledge node", "Name:")
        if not ok:
            return
        selected_kind, ok = QInputDialog.getItem(page, "Node type", "Type:", list(KINDS), 1, False)
        if not ok:
            return
        use_parent = state["node_id"] is not None and QMessageBox.question(
            page, "Parent section", "Place inside the selected node?", QMessageBox.Yes | QMessageBox.No,
            QMessageBox.Yes) == QMessageBox.Yes
        node = bank.create_knowledge_node(title, selected_kind,
                                          parent_id=state["node_id"] if use_parent else None)
        state["node_id"] = node["id"]; search.clear(); kind.setCurrentIndex(0); refresh()

    def attach():
        if state["node_id"] is None:
            return
        # Numeric ID allows any memory to be attached, not only a recent subset.
        memory_id, ok = QInputDialog.getInt(page, "Link memory", "Existing memory ID:", 1, 1, 2147483647)
        if ok:
            bank.link_memory_node(memory_id, state["node_id"]); refresh()

    def detach():
        item = memories.currentItem()
        if item and state["node_id"]:
            bank.link_memory_node(item.data(Qt.UserRole)["id"], state["node_id"], unlink=True)
            refresh()

    def connect_nodes():
        if state["node_id"] is None:
            return
        choices = bank.list_knowledge_nodes(limit=1000)
        choices = [node for node in choices if node["id"] != state["node_id"]]
        if not choices:
            return
        labels = [f"{node['title']} ({node['kind']}) #{node['id']}" for node in choices]
        label, ok = QInputDialog.getItem(page, "Connect nodes", "Other node:", labels, 0, False)
        if not ok:
            return
        relation, ok = QInputDialog.getItem(page, "Relationship", "Selected node → other node:", list(RELATIONS), 0, False)
        if ok:
            bank.link_knowledge_nodes(state["node_id"], choices[labels.index(label)]["id"], relation,
                                       source="User linked in Knowledge Nodes", status="confirmed")
            refresh()

    def confirm():
        item = edges.currentItem()
        if item:
            edge = item.data(Qt.UserRole)
            bank.link_knowledge_nodes(edge["subject_id"], edge["object_id"], edge["relation"],
                source="User confirmed in Knowledge Nodes; original: " + edge["source"],
                confidence=edge["confidence"], status="confirmed")
            show_node(state["node_id"])

    def dismiss():
        item = edges.currentItem()
        if item:
            bank.remove_knowledge_link(item.data(Qt.UserRole)["id"])
            show_node(state["node_id"])

    def export():
        if state["node_id"] is None:
            return
        filename, _ = QFileDialog.getSaveFileName(page, "Export knowledge node", "Apollo_Knowledge.md", "Markdown (*.md)")
        if filename:
            Path(filename).write_text(bank.export_knowledge_markdown(state["node_id"])["markdown"], encoding="utf-8")

    tree.itemSelectionChanged.connect(guarded(tree_selected))
    memories.itemSelectionChanged.connect(guarded(memory_selected))
    edges.itemSelectionChanged.connect(lambda: details.setPlainText(json.dumps(
        edges.currentItem().data(Qt.UserRole), indent=2)) if edges.currentItem() else None)
    for button, fn in ((refresh_btn, refresh), (create_btn, new_node), (attach_btn, attach),
                       (detach_btn, detach), (connect_btn, connect_nodes), (confirm_btn, confirm),
                       (dismiss_btn, dismiss), (export_btn, export)):
        button.clicked.connect(guarded(fn))
    search.returnPressed.connect(guarded(refresh)); kind.currentIndexChanged.connect(guarded(refresh))
    page.refresh_nodes = guarded(refresh)
    refresh()
    return page
