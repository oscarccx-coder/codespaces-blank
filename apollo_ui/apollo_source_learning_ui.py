"""Owner controls; the language model has read-only access to the study journal."""
import json
from PySide6.QtCore import QTimer, Qt
from PySide6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
                               QListWidget, QListWidgetItem, QPlainTextEdit, QSplitter)


def source_learning_view(service, parent=None):
    page = QWidget(parent)
    layout = QVBoxLayout(page)
    notice = QLabel('Standing mission: learn from open-source AI to help Oscar and ZSS. '
                    'Starts after five idle minutes; up to four attempts per day. '
                    'Experiments require an installed Foundry Docker image. Findings and test '
                    'results stay local; production changes require your review.')
    notice.setWordWrap(True)
    layout.addWidget(notice)
    start = QPushButton('Self Upgrade Plan')
    start.setObjectName('self_upgrade_plan')
    start.setToolTip('Start the standing plan and up to 3 public funding research batches when idle. No spending, publishing or customer contact.')
    start.clicked.connect(lambda: start_plan())
    layout.addWidget(start)
    plan_status = QLabel()
    plan_status.setWordWrap(True)
    layout.addWidget(plan_status)
    status = QLabel()
    status.setObjectName('source_learning_status')
    status.setWordWrap(True)
    layout.addWidget(status)
    upgrades = QLabel()
    upgrades.setWordWrap(True)
    upgrades.setObjectName('source_upgrade_case')
    layout.addWidget(upgrades)
    row = QHBoxLayout()
    for action, title in (('pause', 'Pause'), ('resume', 'Resume'), ('stop', 'Stop')):
        button = QPushButton(title)
        button.setObjectName('source_learning_' + action)
        button.clicked.connect(lambda checked=False, a=action: control(a))
        row.addWidget(button)
    layout.addLayout(row)
    split = QSplitter()
    listing = QListWidget()
    listing.setObjectName('source_learning_list')
    detail = QPlainTextEdit()
    detail.setReadOnly(True)
    detail.setObjectName('source_learning_detail')
    split.addWidget(listing)
    split.addWidget(detail)
    split.setStretchFactor(1, 3)
    layout.addWidget(split, 1)
    layout.addWidget(QLabel('Funding proposals — approval here permits free local draft preparation only'))
    funding_list = QListWidget()
    funding_list.setMaximumHeight(100)
    funding_list.setObjectName('source_funding_list')
    layout.addWidget(funding_list)
    funding_detail = QPlainTextEdit()
    funding_detail.setReadOnly(True)
    funding_detail.setMaximumHeight(130)
    funding_detail.setObjectName('source_funding_detail')
    layout.addWidget(funding_detail)
    funding_row = QHBoxLayout()
    for action, title in (('approve_local', 'Approve £0 local preparation'), ('dismiss', 'Dismiss funding plan')):
        button = QPushButton(title)
        button.setObjectName('source_funding_' + action)
        button.clicked.connect(lambda checked=False, a=action: funding_control(a))
        funding_row.addWidget(button)
    layout.addLayout(funding_row)
    entries = {}
    funding = {}

    def inspect():
        item = listing.currentItem()
        if item is None:
            detail.setPlainText(service.status()['prompt'])
            return
        record = service.study_detail(item.data(Qt.UserRole))
        if not record:
            return
        source = record['source']
        content = {'state': record['state'], 'repo': record['repo'],
                   'source_url': source['url'], 'commit': source['commit'],
                   'licence': source['licence'], 'scope': source['scope'],
                   'source_and_licence_files': source['files'],
                   'analysis': record['analysis'], 'sandbox': record['receipt'],
                   'error': record['error']}
        detail.setPlainText(json.dumps(content, indent=2, ensure_ascii=False))

    def refresh():
        nonlocal entries, funding
        data = service.status()
        status.setText(f"{data['mode']} · {data['attempts_today']}/4 attempts today · "
                       f"{data['phase']}\n{data['last_error']}")
        plan_status.setText('Plan file: ' + data['plan_file'] + '\nFunding research: ' + str(data['funding_research'].get('state', 'Not started — use Self Upgrade Plan')))
        case = data['upgrade_case']
        upgrades.setText(('Upgrade case: ' + case['proposal'] + ' ' + case['limits']) if case else 'No measured upgrade case yet. Hardware purchases need a budget and owner approval.')
        selected = listing.currentItem().data(Qt.UserRole) if listing.currentItem() else None
        entries = {r['id']: r for r in data['studies']}
        listing.blockSignals(True)
        listing.clear()
        for r in data['studies']:
            item = QListWidgetItem(f"#{r['id']} [{r['state']}] {r['repo']}")
            item.setData(Qt.UserRole, r['id'])
            listing.addItem(item)
            if r['id'] == selected:
                listing.setCurrentItem(item)
        listing.blockSignals(False)
        inspect()
        selected_funding = funding_list.currentItem().data(Qt.UserRole) if funding_list.currentItem() else None
        funding = {r['id']: r for r in data['funding']}
        funding_list.blockSignals(True)
        funding_list.clear()
        for r in data['funding']:
            item = QListWidgetItem(f"#{r['id']} [{r['state']}] {r['plan']['title']}")
            item.setData(Qt.UserRole, r['id'])
            funding_list.addItem(item)
            if r['id'] == selected_funding:
                funding_list.setCurrentItem(item)
        funding_list.blockSignals(False)
        inspect_funding()

    def inspect_funding():
        item = funding_list.currentItem()
        funding_detail.setPlainText(json.dumps(funding.get(item.data(Qt.UserRole)), indent=2,
                                              ensure_ascii=False) if item else 'Select a proposal to review its offer, risks and validation plan.')

    def funding_control(action):
        item = funding_list.currentItem()
        if item is None:
            return
        try:
            service.owner_funding_control(item.data(Qt.UserRole), action)
            refresh()
        except Exception as exc:
            funding_detail.setPlainText(str(exc))

    def start_plan():
        service.start_upgrade_plan()
        refresh()

    def control(action):
        service.control(action)
        refresh()

    listing.currentRowChanged.connect(inspect)
    funding_list.currentRowChanged.connect(inspect_funding)
    timer = QTimer(page)
    timer.timeout.connect(refresh)
    timer.start(3000)
    refresh()
    return page
