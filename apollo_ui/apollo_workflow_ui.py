"""Owner interface over the same workflow ledger read by chat."""
import json
from datetime import datetime,timezone
from apollo_workflows import REGISTRY

def workflow_view(module,parent=None):
    from PySide6.QtCore import QTimer,Qt
    from PySide6.QtWidgets import QWidget,QVBoxLayout,QHBoxLayout,QLabel,QLineEdit,QPlainTextEdit,QComboBox,QSpinBox,QCheckBox,QPushButton,QListWidget,QListWidgetItem,QSplitter,QTabWidget,QMessageBox,QInputDialog
    page=QWidget(parent); layout=QVBoxLayout(page); layout.addWidget(QLabel('Workflows & Learning'))
    info=QLabel('Finite local workflows with saved stages, independent checks and persistent handoffs. Continuous study remains in Practice & learning.'); info.setWordWrap(True); layout.addWidget(info)
    tabs=QTabWidget(); layout.addWidget(tabs,1)
    runs_page=QWidget(); outer=QVBoxLayout(runs_page); tabs.addTab(runs_page,'Runs & handoffs')
    choice=QComboBox(); choice.setObjectName('workflow_kind')
    for key,value in REGISTRY.items(): choice.addItem(value['title'],key)
    goal=QLineEdit(); goal.setObjectName('workflow_goal'); goal.setPlaceholderText('Research topic, saved-knowledge question or project goal')
    row=QHBoxLayout(); row.addWidget(choice); row.addWidget(goal,1); outer.addLayout(row)
    project=QSpinBox(); project.setObjectName('workflow_project'); project.setRange(0,999999); project.setPrefix('Foundry project #'); project.setSpecialValueText('No Foundry project')
    destination=QComboBox(); destination.setObjectName('workflow_destination'); destination.addItem('Research → topic automatically',None)
    manager=module._manager()
    if manager:
        try:
            for node in manager.execute('memory_bank','list_knowledge_nodes',{'limit':200}): destination.addItem(f"{node['kind']}: {node['title']} (#{node['id']})",node['id'])
        except Exception: destination.setToolTip('Enable Memory Bank before requesting indexing.')
    scopes=QHBoxLayout(); scopes.addWidget(project); scopes.addWidget(destination,1); outer.addLayout(scopes)
    web=QCheckBox('Allow public web research for this run'); web.setObjectName('workflow_web')
    index=QCheckBox('Save report as unverified topic memory'); index.setObjectName('workflow_index')
    start=QPushButton('Start workflow'); start.setObjectName('workflow_start')
    buttons=QHBoxLayout()
    for w in (web,index,start): buttons.addWidget(w)
    outer.addLayout(buttons)
    splitter=QSplitter(); run_list=QListWidget(); run_list.setObjectName('workflow_runs')
    detail=QPlainTextEdit(); detail.setReadOnly(True); detail.setObjectName('workflow_detail')
    splitter.addWidget(run_list); splitter.addWidget(detail); splitter.setStretchFactor(1,3); outer.addWidget(splitter,1)
    actions=QHBoxLayout(); refresh=QPushButton('Refresh'); pause=QPushButton('Pause'); resume=QPushButton('Resume / retry'); stop=QPushButton('Stop'); handoff=QPushButton('Show latest handoff'); artifact=QPushButton('Read output')
    for b in (refresh,pause,resume,stop,handoff,artifact): actions.addWidget(b)
    outer.addLayout(actions); health=QLabel(); outer.addWidget(health)
    procedures=QWidget(); pl=QVBoxLayout(procedures); tabs.addTab(procedures,'Reviewed procedures')
    notice=QLabel('Two completed, checked runs propose a procedure. Owner approval reuses a known workflow; it grants no permissions or model training.'); notice.setWordWrap(True); pl.addWidget(notice)
    recipes=QListWidget(); recipes.setObjectName('workflow_procedures'); pl.addWidget(recipes)
    recipe_detail=QPlainTextEdit(); recipe_detail.setReadOnly(True); pl.addWidget(recipe_detail)
    approve=QPushButton('Approve procedure'); revoke=QPushButton('Revoke'); use=QPushButton('Run approved procedure'); rb=QHBoxLayout()
    for b in (approve,revoke,use): rb.addWidget(b)
    pl.addLayout(rb)
    knowledge=QPlainTextEdit(); knowledge.setReadOnly(True); tabs.addTab(knowledge,'Knowledge map')
    curriculum=QPlainTextEdit(); curriculum.setReadOnly(True); curriculum.setObjectName('workflow_curriculum'); tabs.addTab(curriculum,'Topic progress')
    route_page=QWidget(); rl=QVBoxLayout(route_page); tabs.addTab(route_page,'Route preview')
    route_input=QLineEdit(); route_input.setPlaceholderText('Preview a request without executing it')
    route_button=QPushButton('Preview route'); route_output=QPlainTextEdit(); route_output.setReadOnly(True)
    for w in (route_input,route_button,route_output): rl.addWidget(w)
    rl.addWidget(QLabel('Configuration audit is available as a finite workflow in Runs.'))
    def selected(): return run_list.currentItem().data(Qt.UserRole) if run_list.currentItem() else None
    def selected_recipe(): return recipes.currentItem().data(Qt.UserRole) if recipes.currentItem() else None
    def error(exc): QMessageBox.warning(page,'Workflow',f'{type(exc).__name__}: {exc}')
    def show_run():
        ident=selected()
        if not ident: return
        try:
            run=module.service.store.status(ident)
            lines=[f"Run {ident} · {run['state']} · {REGISTRY[run['workflow']]['title']}",'Goal: '+run['goal'],f"Stages: {run['completed_stages']}/{len(run['stages'])}",'Current stage: '+run['current_stage'],'Last error: '+(run['last_error'] or 'none'),
              'Last stage activity age: '+(f"{run['heartbeat_age_seconds']:.0f} seconds" if run['heartbeat_age_seconds'] is not None else 'not started'),'']
            for stage in run['stages']:
                duration='not started'
                if stage['started_at'] and stage['state'] in ('RUNNING','DONE','FAILED'):
                    end=datetime.fromisoformat(stage['finished_at']) if stage['state'] in ('DONE','FAILED') else datetime.now(timezone.utc)
                    duration=f"wall time {(end-datetime.fromisoformat(stage['started_at'])).total_seconds():.0f}s"
                lines.extend([f"{stage['ordinal']+1}. {stage['name']} · {stage['role']} · {stage['state']} · attempts {stage['attempts']}",'Timing: '+duration,
                    'Depends on: '+(', '.join(stage['dependencies']) or 'none'),'Receipt: '+str(stage['result'].get('summary') or stage['error'] or 'pending')])
            lines.extend(['','PERSISTENT HANDOFFS'])
            for h in run['handoffs']: lines.extend([h['created_at']+' '+h['role']+': '+h['summary'],'Next: '+h['next_action'],'Receipt SHA256: '+h['receipt_sha256']])
            detail.setPlainText('\n'.join(lines))
        except Exception as exc: detail.setPlainText(str(exc))
    def reload():
        current=selected(); items=module.service.store.list()
        labels=[(r['id'],f"{r['id']} · {r['state']} · {r['goal'][:55]}") for r in items]
        existing=[(run_list.item(i).data(Qt.UserRole),run_list.item(i).text()) for i in range(run_list.count())]
        if existing!=labels:
            run_list.blockSignals(True); run_list.clear()
            for ident,label in labels:
                cell=QListWidgetItem(label); cell.setData(Qt.UserRole,ident); run_list.addItem(cell)
                if ident==current: run_list.setCurrentItem(cell)
            if not run_list.currentItem() and labels: run_list.setCurrentRow(0)
            run_list.blockSignals(False)
        show_run(); health.setText(f'{len(items)} saved runs. Worker error: '+(module.service.last_worker_error or 'none'))
        if tabs.currentIndex()==1:
            recipe=selected_recipe(); current_id=recipe['id'] if recipe else None
            recipes.blockSignals(True); recipes.clear()
            for recipe in module.service.store.procedures():
                cell=QListWidgetItem(f"#{recipe['id']} {recipe['state']} · {recipe['title']}"); cell.setData(Qt.UserRole,recipe); recipes.addItem(cell)
                if recipe['id']==current_id: recipes.setCurrentItem(cell)
            recipes.blockSignals(False)
        if tabs.currentIndex()==2: knowledge.setPlainText(json.dumps(module.memory_map(),indent=2,ensure_ascii=False))
        if tabs.currentIndex()==3: curriculum.setPlainText(json.dumps(module.curriculum(),indent=2,ensure_ascii=False))
    def begin(recipe=None):
        try:
            kind=recipe['workflow'] if recipe else choice.currentData()
            run=module.owner_action('start',workflow=kind,goal=goal.text(),web_allowed=web.isChecked(),index_memory=index.isChecked(),target_node_id=destination.currentData(),project_id=project.value() or None,recipe_id=recipe['id'] if recipe else None)
            reload()
            for i in range(run_list.count()):
                if run_list.item(i).data(Qt.UserRole)==run['id']: run_list.setCurrentRow(i)
            tabs.setCurrentIndex(0)
        except Exception as exc: error(exc)
    def control(action):
        if not selected(): return
        try: module.owner_action(action,run_id=selected()); reload()
        except Exception as exc: error(exc)
    def show_handoff():
        if not selected(): return
        run=module.service.store.status(selected()); detail.setPlainText(json.dumps(run['handoffs'][-1] if run['handoffs'] else {'notice':'No committed handoff yet.'},indent=2,ensure_ascii=False))
    def show_artifact():
        if not selected(): return
        run=module.service.store.status(selected()); output=next((s['result'] for s in run['stages'] if s['name']=='output' and s['state']=='DONE'),{})
        detail.setPlainText(output.get('body') or 'No completed output; inspect stage errors for partial work.')
    def review(approved):
        recipe=selected_recipe()
        if not recipe: return
        title=recipe['title']
        if approved:
            title,ok=QInputDialog.getText(page,'Approve procedure','Name this reusable procedure:',text=title)
            if not ok: return
        try: module.owner_action('review_procedure',ident=recipe['id'],approve=approved,title=title); reload()
        except Exception as exc: error(exc)
    start.clicked.connect(lambda:begin()); refresh.clicked.connect(reload)
    pause.clicked.connect(lambda:control('pause')); resume.clicked.connect(lambda:control('resume')); stop.clicked.connect(lambda:control('stop'))
    handoff.clicked.connect(show_handoff); artifact.clicked.connect(show_artifact); run_list.currentItemChanged.connect(lambda *_:show_run())
    recipes.currentItemChanged.connect(lambda *_:recipe_detail.setPlainText(json.dumps(selected_recipe() or {},indent=2,ensure_ascii=False)))
    approve.clicked.connect(lambda:review(True)); revoke.clicked.connect(lambda:review(False)); use.clicked.connect(lambda:begin(selected_recipe()) if selected_recipe() else None)
    route_button.clicked.connect(lambda:route_output.setPlainText(json.dumps(module.run('workflow_route',{'question':route_input.text()}),indent=2)))
    tabs.currentChanged.connect(lambda *_:reload()); timer=QTimer(page); timer.setInterval(1500); timer.timeout.connect(reload); timer.start(); reload(); return page
