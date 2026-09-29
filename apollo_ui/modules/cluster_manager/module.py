from pathlib import Path
from apollo_cluster import ClusterCoordinator


class Module:
    def __init__(self,context=None):
        self.context=context or {}
        self.base=Path(self.context.get('base_dir') or '.').resolve()
        self.cluster=ClusterCoordinator(self.base)

    def tools(self):
        return [
            {"name":"cluster_workers","description":"List online Apollo worker nodes and capabilities.","parameters":{"type":"object","properties":{"refresh":{"type":"boolean"}}}},
            {"name":"cluster_plan","description":"Plan assignments for explicit task envelopes without running them.","parameters":{"type":"object","properties":{"tasks":{"type":"array"}},"required":["tasks"]}},
            {"name":"cluster_run_tasks","description":"Run an explicit list of allow-listed worker tasks in parallel across capable Apollo nodes.","parameters":{"type":"object","properties":{"tasks":{"type":"array"},"timeout_per_task":{"type":"integer"}},"required":["tasks"]}},
            {"name":"cluster_parallel_prompts","description":"Send independent prompt subtasks to available Ollama worker nodes in parallel and aggregate results.","parameters":{"type":"object","properties":{"subtasks":{"type":"array"},"shared_context":{"type":"string"},"timeout_per_task":{"type":"integer"}},"required":["subtasks"]}}
        ]

    def run(self,action,arguments):
        x=arguments or {}
        if action=='cluster_workers': return {'workers':self.cluster.workers(refresh=x.get('refresh',True))}
        if action=='cluster_plan': return self.cluster.plan(x['tasks'],refresh=True)
        if action=='cluster_run_tasks': return self.cluster.run_tasks(x['tasks'],timeout_per_task=x.get('timeout_per_task',600))
        if action=='cluster_parallel_prompts': return self.cluster.parallel_prompts(x['subtasks'],x.get('shared_context',''),x.get('timeout_per_task',600))
        raise KeyError(action)

    def self_test(self):
        return isinstance(self.cluster.fleet.devices(),list)

    def build_ui(self,parent=None,ui_context=None):
        from PySide6.QtWidgets import QWidget,QVBoxLayout,QHBoxLayout,QLabel,QPushButton,QPlainTextEdit,QSpinBox,QMessageBox
        page=QWidget(parent); root=QVBoxLayout(page)
        title=QLabel('Apollo Cluster Manager'); title.setStyleSheet('font-size:22px;font-weight:700;'); root.addWidget(title)
        note=QLabel('One subtask per line. Apollo distributes independent work across enrolled Ollama workers and aggregates the evidence.'); note.setWordWrap(True); root.addWidget(note)
        context=QPlainTextEdit(); context.setPlaceholderText('Optional shared project context...'); context.setMaximumHeight(150); root.addWidget(context)
        subtasks=QPlainTextEdit(); subtasks.setPlaceholderText('Design the backend interface\nReview likely failure modes\nDraft regression tests'); subtasks.setMinimumHeight(160); root.addWidget(subtasks)
        row=QHBoxLayout(); refresh=QPushButton('Show Workers'); run=QPushButton('Run Distributed Prompts'); timeout=QSpinBox(); timeout.setRange(30,3600); timeout.setValue(600); row.addWidget(refresh); row.addWidget(QLabel('Timeout/task')); row.addWidget(timeout); row.addWidget(run); root.addLayout(row)
        output=QPlainTextEdit(); output.setReadOnly(True); output.setMinimumHeight(240); root.addWidget(output,1)
        def show(v):
            import json; output.setPlainText(json.dumps(v,indent=2,default=str))
        refresh.clicked.connect(lambda: show({'workers':self.cluster.workers(refresh=True)}))
        def do_run():
            lines=[x.strip() for x in subtasks.toPlainText().splitlines() if x.strip()]
            if not lines:
                QMessageBox.warning(page,'Cluster Manager','Add at least one subtask.'); return
            try: show(self.cluster.parallel_prompts(lines,context.toPlainText(),timeout.value()))
            except Exception as exc: QMessageBox.warning(page,'Cluster Manager',f'{type(exc).__name__}: {exc}')
        run.clicked.connect(do_run)
        show({'workers':self.cluster.workers(refresh=False)})
        return page
