from pathlib import Path
class Module:
    def __init__(self,context=None):
        c=context or {}; self.base_dir=Path(c.get('base_dir','.')).resolve(); self.runtime=c.get('runtime')
    def tools(self): return [
        {'name':'list_capabilities','description':'List Apollo capabilities, risk levels and permission decisions.','parameters':{'type':'object','properties':{}}},
        {'name':'get_health','description':'Return Apollo runtime/module health.','parameters':{'type':'object','properties':{}}},
        {'name':'recent_events','description':'Read recent internal event-bus messages.','parameters':{'type':'object','properties':{'limit':{'type':'integer'}}}},
        {'name':'blackboard_get','description':'Read shared Apollo blackboard state.','parameters':{'type':'object','properties':{'key':{'type':'string'}},'required':['key']}},
        {'name':'blackboard_set','description':'Write shared Apollo blackboard state.','parameters':{'type':'object','properties':{'key':{'type':'string'},'value':{}},'required':['key','value']}},
        {'name':'create_snapshot','description':'Create a recovery ZIP of Apollo core and modules.','parameters':{'type':'object','properties':{'name':{'type':'string'}}}},
        {'name':'set_permission','description':'Change one capability permission.','parameters':{'type':'object','properties':{'capability':{'type':'string'},'decision':{'type':'string','enum':['allow','deny']}},'required':['capability','decision']}},
        {'name':'apply_permission_profile','description':'Apply Safe, Normal or Developer permission profile.','parameters':{'type':'object','properties':{'profile':{'type':'string','enum':['safe','normal','developer']}},'required':['profile']}},
        {'name':'module_failures','description':'List installed-module failure/quarantine records.','parameters':{'type':'object','properties':{}}},
        {'name':'clear_module_quarantine','description':'Clear a module quarantine so Apollo can retry it.','parameters':{'type':'object','properties':{'module_id':{'type':'string'}},'required':['module_id']}},
        {'name':'operational_summary','description':'Compact Apollo health/goals/actions/shared-state summary.','parameters':{'type':'object','properties':{}}},
    ]
    def _rt(self):
        if self.runtime is None: raise RuntimeError('Apollo runtime unavailable')
        return self.runtime
    def run(self,a,x):
        x=x or {}; rt=self._rt()
        if a=='list_capabilities': return {'capabilities':rt.capability_records()}
        if a=='get_health': return rt.health()
        if a=='recent_events': return {'events':rt.recent_events(x.get('limit',100))}
        if a=='blackboard_get': return {'key':x['key'],'value':rt.blackboard_get(x['key'])}
        if a=='blackboard_set': rt.blackboard_set(x['key'],x.get('value'),'core_services'); return {'saved':True}
        if a=='create_snapshot': return {'file':rt.create_snapshot(x.get('name','manual'))}
        if a=='set_permission': return rt.set_permission(x['capability'],x['decision'])
        if a=='apply_permission_profile': return rt.apply_permission_profile(x['profile'])
        if a=='module_failures': return {'modules':rt.module_failure_records()}
        if a=='clear_module_quarantine': return rt.clear_module_failure(x['module_id'])
        if a=='operational_summary': return rt.operational_summary()
        raise KeyError(a)
    def self_test(self): assert len(self.tools())==11; return 'Core Services 7.5 contracts passed'
    def build_ui(self,parent=None,ui_context=None):
        from PySide6.QtWidgets import QWidget,QVBoxLayout,QHBoxLayout,QLabel,QListWidget,QPushButton,QMessageBox,QComboBox,QTabWidget
        page=QWidget(parent); out=QVBoxLayout(page); title=QLabel('Apollo 7.5 Control Center'); title.setStyleSheet('font-size:24px;font-weight:800;'); out.addWidget(title)
        info=QLabel('Every live action uses the same capability/permission layer. Repeated module crashes are quarantined instead of endlessly poisoning startup.'); info.setWordWrap(True); out.addWidget(info)
        prow=QHBoxLayout(); prow.addWidget(QLabel('Permission profile:')); profile=QComboBox(); profile.addItems(['safe','normal','developer']);
        if self.runtime: profile.setCurrentText(self.runtime.permission_profile())
        apply=QPushButton('Apply Profile'); prow.addWidget(profile); prow.addWidget(apply); prow.addStretch(1); out.addLayout(prow)
        tabs=QTabWidget(); out.addWidget(tabs,1)
        cp=QWidget(); cl=QVBoxLayout(cp); caps=QListWidget(); cl.addWidget(caps,1); row=QHBoxLayout(); allow=QPushButton('Allow Selected'); deny=QPushButton('Deny Selected'); refresh=QPushButton('Refresh'); snap=QPushButton('Recovery Snapshot');
        for b in (allow,deny,refresh,snap): row.addWidget(b)
        cl.addLayout(row); tabs.addTab(cp,'Capabilities')
        fp=QWidget(); fl=QVBoxLayout(fp); failures=QListWidget(); fl.addWidget(failures,1); clear=QPushButton('Clear Selected Quarantine'); fl.addWidget(clear); tabs.addTab(fp,'Module Recovery')
        # Consolidated System UI: preserve underlying module APIs, but put
        # their panels under one Control Center instead of opening four apps.
        manager = (ui_context or {}).get("module_manager") if isinstance(ui_context,dict) else None
        if manager is not None:
            for module_id, tab_name in (
                ("gpu_monitor", "GPU & VRAM"),
                ("activity_trace", "Activity & Errors"),
                ("notification_center", "Notifications"),
            ):
                record = manager.get_module(module_id)
                instance = record.get("instance") if record and record.get("enabled") else None
                if instance is None or not hasattr(instance, "build_ui"):
                    continue
                try:
                    tabs.addTab(instance.build_ui(parent=tabs, ui_context=ui_context), tab_name)
                except Exception as exc:
                    fallback=QWidget(); v=QVBoxLayout(fallback)
                    message=QLabel(f"Could not open {tab_name}: {type(exc).__name__}: {exc}")
                    message.setWordWrap(True); v.addWidget(message)
                    tabs.addTab(fallback, tab_name)
        status=QLabel(); out.addWidget(status)
        def reload():
            caps.clear(); failures.clear()
            if not self.runtime: status.setText('Runtime unavailable'); return
            for i in self.runtime.capability_records(): caps.addItem(f"{i['permission'].upper():5} | {i['risk'].upper():6} | {i['capability']}\n{i['description']}")
            for i in self.runtime.module_failure_records(): failures.addItem(f"{i['module_id']} | failures={i['failure_count']} | quarantined={bool(i['quarantined'])}\n{i['last_error'][:500]}")
            h=self.runtime.health(); status.setText(f"{h['loaded_modules']} modules • {h['capability_count']} capabilities • {h['denied_capabilities']} blocked • profile={self.runtime.permission_profile()}")
        def cap():
            i=caps.currentItem(); return i.text().splitlines()[0].split('|',2)[2].strip() if i else None
        def setd(d):
            c=cap()
            if c:self.runtime.set_permission(c,d); reload()
        def dosnap():
            try: QMessageBox.information(page,'Apollo',self.runtime.create_snapshot('control_center'))
            except Exception as e: QMessageBox.warning(page,'Apollo',str(e))
        def doprofile():
            try: self.runtime.apply_permission_profile(profile.currentText()); reload()
            except Exception as e: QMessageBox.warning(page,'Apollo',str(e))
        def doclear():
            i=failures.currentItem()
            if i:self.runtime.clear_module_failure(i.text().split('|',1)[0].strip()); reload()
        allow.clicked.connect(lambda:setd('allow')); deny.clicked.connect(lambda:setd('deny')); refresh.clicked.connect(reload); snap.clicked.connect(dosnap); apply.clicked.connect(doprofile); clear.clicked.connect(doclear); reload(); return page
