from pathlib import Path
from apollo_device_agent import DeviceAgentService


class Module:
    def __init__(self, context=None):
        self.context = context or {}
        self.base = Path(self.context.get('base_dir') or '.').resolve()
        self.service = DeviceAgentService(self.base)
        if not self.context.get('validation') and self.service.config().get('auto_start'):
            self.service.start()

    def tools(self):
        return [
            {"name":"device_agent_status","description":"Return this Apollo node identity/capabilities and worker-agent status.","parameters":{"type":"object","properties":{}}},
            {"name":"start_device_agent","description":"Start the authenticated Fleet/Cluster worker service.","parameters":{"type":"object","properties":{}}},
            {"name":"stop_device_agent","description":"Stop the local Fleet/Cluster worker service.","parameters":{"type":"object","properties":{}}},
            {"name":"configure_device_agent","description":"Configure node name, role, group, host, port and auto-start.","parameters":{"type":"object","properties":{"device_name":{"type":"string"},"role":{"type":"string"},"group":{"type":"string"},"host":{"type":"string"},"port":{"type":"integer"},"auto_start":{"type":"boolean"}}}},
            {"name":"device_enrollment_token","description":"Return this node's enrollment token for adding it to a trusted Fleet Authority.","parameters":{"type":"object","properties":{}}},
            {"name":"rotate_device_token","description":"Rotate this node's Fleet authentication token.","parameters":{"type":"object","properties":{}}}
        ]

    def run(self, action, arguments):
        arguments = arguments or {}
        if action == 'device_agent_status':
            return self.service.status()
        if action == 'start_device_agent':
            return self.service.start()
        if action == 'stop_device_agent':
            return self.service.stop()
        if action == 'configure_device_agent':
            return self.service.configure(**arguments)
        if action == 'device_enrollment_token':
            return {'device_id': self.service.config()['device_id'], 'token': self.service.enrollment_token()}
        if action == 'rotate_device_token':
            return {'device_id': self.service.config()['device_id'], 'token': self.service.rotate_token()}
        raise KeyError(action)

    def self_test(self):
        return bool(self.service.identity().get('device_id'))

    def close(self):
        self.service.stop()

    def build_ui(self, parent=None, ui_context=None):
        from PySide6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QComboBox, QSpinBox, QCheckBox, QPushButton, QPlainTextEdit, QApplication
        page = QWidget(parent)
        root = QVBoxLayout(page)
        title = QLabel('Apollo Device Agent')
        title.setStyleSheet('font-size:22px;font-weight:700;')
        root.addWidget(title)
        info = QLabel('Makes this Apollo installation available as an authenticated worker on your trusted LAN. No remote shell is exposed.')
        info.setWordWrap(True)
        root.addWidget(info)

        cfg = self.service.config()
        name = QLineEdit(str(cfg.get('device_name','')))
        role = QComboBox(); role.addItems(['worker','hybrid','coordinator']); role.setCurrentText(str(cfg.get('role','worker')))
        group = QLineEdit(str(cfg.get('group','Default')))
        host = QLineEdit(str(cfg.get('host','0.0.0.0')))
        port = QSpinBox(); port.setRange(0,65535); port.setValue(int(cfg.get('port',8766)))
        auto = QCheckBox('Start Device Agent automatically with Apollo'); auto.setChecked(bool(cfg.get('auto_start',False)))
        for label, widget in [('Device name',name),('Role',role),('Group',group),('Listen host',host),('Port',port)]:
            row=QHBoxLayout(); row.addWidget(QLabel(label)); row.addWidget(widget,1); root.addLayout(row)
        root.addWidget(auto)

        buttons=QHBoxLayout()
        save=QPushButton('Save'); start=QPushButton('Start Agent'); stop=QPushButton('Stop Agent'); copy=QPushButton('Copy Enrollment Token'); rotate=QPushButton('Rotate Token')
        for b in (save,start,stop,copy,rotate): buttons.addWidget(b)
        root.addLayout(buttons)
        output=QPlainTextEdit(); output.setReadOnly(True); output.setMinimumHeight(220); root.addWidget(output,1)

        def show(value):
            import json
            output.setPlainText(json.dumps(value, indent=2, default=str))
        def do_save():
            show(self.service.configure(device_name=name.text(),role=role.currentText(),group=group.text(),host=host.text(),port=port.value(),auto_start=auto.isChecked()))
        def do_copy():
            token=self.service.enrollment_token(); QApplication.clipboard().setText(token); show({'copied':True,'device_id':self.service.config()['device_id'],'token':token})
        save.clicked.connect(do_save)
        start.clicked.connect(lambda: show(self.service.start()))
        stop.clicked.connect(lambda: show(self.service.stop()))
        copy.clicked.connect(do_copy)
        rotate.clicked.connect(lambda: show({'token':self.service.rotate_token(),'warning':'Re-enrol/update Fleet Authority after rotating.'}))
        show(self.service.status())
        return page
