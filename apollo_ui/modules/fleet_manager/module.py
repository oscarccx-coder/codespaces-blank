from pathlib import Path
from apollo_fleet import FleetAuthority


class Module:
    def __init__(self, context=None):
        self.context=context or {}
        self.base=Path(self.context.get('base_dir') or '.').resolve()
        self.fleet=FleetAuthority(self.base)

    def tools(self):
        return [
            {"name":"fleet_devices","description":"List enrolled Apollo devices and their last known status.","parameters":{"type":"object","properties":{"refresh":{"type":"boolean"}}}},
            {"name":"enroll_fleet_device","description":"Enroll a trusted Apollo Device Agent using its URL and enrollment token.","parameters":{"type":"object","properties":{"url":{"type":"string"},"token":{"type":"string"},"name":{"type":"string"},"role":{"type":"string"},"group":{"type":"string"}},"required":["url","token"]}},
            {"name":"refresh_fleet","description":"Refresh status for all enrolled devices.","parameters":{"type":"object","properties":{}}},
            {"name":"update_fleet_device","description":"Rename/regroup/change logical role of an enrolled device.","parameters":{"type":"object","properties":{"device_id":{"type":"string"},"name":{"type":"string"},"role":{"type":"string"},"group":{"type":"string"}},"required":["device_id"]}},
            {"name":"revoke_fleet_device","description":"Revoke a device from Fleet/Cluster use.","parameters":{"type":"object","properties":{"device_id":{"type":"string"}},"required":["device_id"]}},
            {"name":"remove_fleet_device","description":"Remove a device record from the local Fleet registry.","parameters":{"type":"object","properties":{"device_id":{"type":"string"}},"required":["device_id"]}}
        ]

    def run(self, action, arguments):
        x=arguments or {}
        if action=='fleet_devices':
            return {'devices': self.fleet.refresh_all() if x.get('refresh') else self.fleet.devices()}
        if action=='enroll_fleet_device':
            return self.fleet.enroll(x['url'],x['token'],x.get('name'),x.get('role','worker'),x.get('group','Default'))
        if action=='refresh_fleet': return {'devices':self.fleet.refresh_all()}
        if action=='update_fleet_device': return self.fleet.update_metadata(x['device_id'],x.get('name'),x.get('role'),x.get('group'))
        if action=='revoke_fleet_device': return self.fleet.revoke(x['device_id'])
        if action=='remove_fleet_device': return self.fleet.remove(x['device_id'])
        raise KeyError(action)

    def self_test(self):
        return isinstance(self.fleet.devices(), list)

    def build_ui(self,parent=None,ui_context=None):
        from PySide6.QtCore import Qt
        from PySide6.QtWidgets import QWidget,QVBoxLayout,QHBoxLayout,QLabel,QLineEdit,QComboBox,QPushButton,QListWidget,QListWidgetItem,QPlainTextEdit,QMessageBox
        page=QWidget(parent); root=QVBoxLayout(page)
        title=QLabel('Apollo Fleet Manager'); title.setStyleSheet('font-size:22px;font-weight:700;'); root.addWidget(title)
        note=QLabel('Enrol trusted Apollo nodes, see which are online, and group them for future rollout/cluster work.'); note.setWordWrap(True); root.addWidget(note)
        url=QLineEdit(); url.setPlaceholderText('http://192.168.1.50:8766')
        token=QLineEdit(); token.setPlaceholderText('Enrollment token from Device Agent')
        name=QLineEdit(); name.setPlaceholderText('Workshop Apollo')
        group=QLineEdit('Default')
        role=QComboBox(); role.addItems(['worker','hybrid','coordinator'])
        for label,w in [('Device URL',url),('Enrollment token',token),('Display name',name),('Group',group),('Role',role)]:
            r=QHBoxLayout(); r.addWidget(QLabel(label)); r.addWidget(w,1); root.addLayout(r)
        actions=QHBoxLayout(); enroll=QPushButton('Enroll Device'); refresh=QPushButton('Refresh Fleet'); revoke=QPushButton('Revoke Selected'); remove=QPushButton('Remove Selected')
        for b in (enroll,refresh,revoke,remove): actions.addWidget(b)
        root.addLayout(actions)
        devices=QListWidget(); devices.setMinimumHeight(180); root.addWidget(devices)
        output=QPlainTextEdit(); output.setReadOnly(True); output.setMinimumHeight(180); root.addWidget(output,1)
        def show(v):
            import json; output.setPlainText(json.dumps(v,indent=2,default=str))
        def selected_id():
            item=devices.currentItem(); return item.data(Qt.UserRole) if item else None
        def redraw(rows=None):
            rows=self.fleet.devices() if rows is None else rows
            devices.clear()
            for d in rows:
                status=d.get('status') or {}; hw=status.get('hardware') or {}
                state='ONLINE' if d.get('online') else 'OFFLINE'
                label=f"{d.get('name')}  |  {state}  |  Apollo {status.get('apollo_version','?')}  |  {d.get('group','Default')}"
                item=QListWidgetItem(label); item.setData(Qt.UserRole,d.get('device_id')); devices.addItem(item)
            show({'devices':rows})
        def do_enroll():
            try:
                result=self.fleet.enroll(url.text(),token.text(),name.text() or None,role.currentText(),group.text() or 'Default'); redraw(); show(result)
            except Exception as exc: QMessageBox.warning(page,'Fleet Manager',f'{type(exc).__name__}: {exc}')
        def do_refresh():
            try: redraw(self.fleet.refresh_all())
            except Exception as exc: QMessageBox.warning(page,'Fleet Manager',f'{type(exc).__name__}: {exc}')
        def do_revoke():
            did=selected_id();
            if did: show(self.fleet.revoke(did)); redraw()
        def do_remove():
            did=selected_id();
            if did: show(self.fleet.remove(did)); redraw()
        enroll.clicked.connect(do_enroll); refresh.clicked.connect(do_refresh); revoke.clicked.connect(do_revoke); remove.clicked.connect(do_remove)
        redraw(); return page
