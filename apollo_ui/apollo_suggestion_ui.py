"""Owner inbox for proposals, self-prompts and guidance answers."""
import json
from PySide6.QtCore import QTimer,Qt
from PySide6.QtWidgets import QWidget,QVBoxLayout,QHBoxLayout,QLabel,QListWidget,QListWidgetItem,QPlainTextEdit,QPushButton,QCheckBox,QSplitter,QInputDialog,QMessageBox

def suggestion_view(module,parent=None):
    page=QWidget(parent); layout=QVBoxLayout(page); layout.addWidget(QLabel('Apollo Suggestions'))
    notice=QLabel('Apollo proposes research and asks for guidance. Proposals are not completed work or approval to act. Answers stay local; optional saved guidance can be recalled in later chats.'); notice.setWordWrap(True); layout.addWidget(notice)
    enabled=QCheckBox('Allow occasional idle local reflection (up to 4 attempts/day)'); enabled.setChecked(module.store.state('enabled','1')=='1'); layout.addWidget(enabled)
    split=QSplitter(); listing=QListWidget(); listing.setObjectName('suggestion_list'); detail=QPlainTextEdit(); detail.setReadOnly(True); detail.setObjectName('suggestion_detail'); split.addWidget(listing); split.addWidget(detail); split.setStretchFactor(1,3); layout.addWidget(split,1)
    answer=QPlainTextEdit(); answer.setObjectName('guidance_answer'); answer.setPlaceholderText('Answer Apollo’s selected question, or correct earlier guidance.'); answer.setMaximumHeight(100); layout.addWidget(answer)
    save=QCheckBox('Also save my answer as explicit guidance in Memory Bank'); layout.addWidget(save)
    web=QCheckBox('I authorise public web research for the selected proposal'); layout.addWidget(web)
    row=QHBoxLayout(); reply=QPushButton('Save answer'); keep=QPushButton('Keep suggestion'); dismiss=QPushButton('Dismiss'); start=QPushButton('Edit prompt and start idle research'); refresh=QPushButton('Refresh')
    for b in (reply,keep,dismiss,start,refresh): row.addWidget(b)
    layout.addLayout(row); status=QLabel(); status.setWordWrap(True); layout.addWidget(status)
    def selected(): return listing.currentItem().data(Qt.UserRole) if listing.currentItem() else None
    def inspect():
        ident=selected()
        if ident is None: return
        item=module.store.get(ident)
        lines=[f"#{ident} · {item['kind']} · {item['status']}",item['title'],'','PROMPT / QUESTION',item['prompt'],'','WHY APOLLO PROPOSED THIS',item['reason'],'','Observed mission references: '+str(item['evidence']),'Linked research mission: '+str(item['mission_id'] or 'none'),'','OWNER ANSWERS']
        lines += [a['created_at']+' '+a['answer'] for a in item['answers']]; detail.setPlainText('\n'.join(lines))
    def reload():
        current=selected(); labels=[(i['id'],f"#{i['id']} {i['kind']} · {i['status']} · {i['title']}") for i in module.store.list()]
        old=[(listing.item(i).data(Qt.UserRole),listing.item(i).text()) for i in range(listing.count())]
        if old!=labels:
            listing.blockSignals(True); listing.clear()
            for ident,label in labels:
                cell=QListWidgetItem(label); cell.setData(Qt.UserRole,ident); listing.addItem(cell)
                if ident==current: listing.setCurrentItem(cell)
            if not listing.currentItem() and labels: listing.setCurrentRow(0)
            listing.blockSignals(False)
        inspect(); status.setText('Reflection error: '+(module.store.state('last_error') or 'none')+' · New reflection waits for five idle minutes and its hourly/daily budget. No cloud calls or automatic code changes.')
    def error(exc): QMessageBox.warning(page,'Apollo Suggestions',str(exc))
    def respond():
        if selected() is None: return
        try:
            result=module.owner_answer(selected(),answer.toPlainText(),save.isChecked()); answer.clear(); reload()
            if result.get('memory_error'): QMessageBox.warning(page,'Guidance saved locally','Memory Bank save failed: '+result['memory_error'])
        except Exception as exc: error(exc)
    def review(state):
        if selected() is None: return
        try: module.store.review(selected(),state); reload()
        except Exception as exc: error(exc)
    def research():
        if selected() is None: return
        item=module.store.get(selected()); prompt,ok=QInputDialog.getMultiLineText(page,'Review Apollo’s self-prompt','Research goal (public topic):',item['prompt'])
        if not ok: return
        try: module.start_research(item['id'],prompt,web.isChecked()); reload()
        except Exception as exc: error(exc)
    enabled.toggled.connect(lambda value:module.store.set_state('enabled','1' if value else '0'))
    listing.currentItemChanged.connect(lambda *_:inspect()); reply.clicked.connect(respond); keep.clicked.connect(lambda:review('accepted')); dismiss.clicked.connect(lambda:review('dismissed')); start.clicked.connect(research); refresh.clicked.connect(reload)
    timer=QTimer(page); timer.setInterval(3000); timer.timeout.connect(reload); timer.start(); reload(); return page
