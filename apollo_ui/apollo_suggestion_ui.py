"""Owner inbox for proposals, self-prompts and guidance answers."""
import json
from PySide6.QtCore import QTimer,Qt,QDateTime
from PySide6.QtWidgets import QWidget,QVBoxLayout,QHBoxLayout,QLabel,QListWidget,QListWidgetItem,QPlainTextEdit,QPushButton,QCheckBox,QSplitter,QInputDialog,QMessageBox,QComboBox,QDialog,QFormLayout,QLineEdit,QDateTimeEdit,QSpinBox

def suggestion_view(module,parent=None):
    page=QWidget(parent); layout=QVBoxLayout(page); layout.addWidget(QLabel('Apollo Initiative Director'))
    notice=QLabel('Apollo proposes research and asks for guidance. Proposals are not completed work or approval to act. Answers stay local; optional saved guidance can be recalled in later chats.'); notice.setWordWrap(True); layout.addWidget(notice)
    enabled=QCheckBox('Allow occasional idle local reflection (up to 4 attempts/day)'); enabled.setChecked(module.store.state('enabled','1')=='1'); layout.addWidget(enabled)
    goal_row=QHBoxLayout()
    goal_pick=QComboBox(); goal_pick.setObjectName('initiative_goal_selector'); goal_row.addWidget(goal_pick,1)
    add_goal=QPushButton('Add goal'); next_step=QPushButton('Propose next step'); pause_goal=QPushButton('Pause/resume')
    for button in (add_goal,next_step,pause_goal): goal_row.addWidget(button)
    layout.addLayout(goal_row)
    goal_status=QLabel('Strategic goals are owner-directed and do not grant execution permission.')
    goal_status.setWordWrap(True); layout.addWidget(goal_status)
    schedules_button=QPushButton('Scheduled tasks…'); schedules_button.setObjectName('initiative_schedules'); layout.addWidget(schedules_button)
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
    def reload_goals(data):
        current=goal_pick.currentData()
        goals=data['goals']
        items=[(g['id'],f"#{g['id']} [{g['status']}] P{g['priority']} {g['title']}") for g in goals]
        previous=[(goal_pick.itemData(i),goal_pick.itemText(i)) for i in range(goal_pick.count())]
        if previous!=items:
            goal_pick.blockSignals(True); goal_pick.clear()
            for ident,label in items: goal_pick.addItem(label,ident)
            found=next((i for i,(ident,_) in enumerate(items) if ident==current),0)
            if items: goal_pick.setCurrentIndex(found)
            goal_pick.blockSignals(False)
        enabled=module.initiative is not None
        add_goal.setEnabled(enabled)
        next_step.setEnabled(enabled and goal_pick.count()>0 and next((g['status']=='active' for g in goals if g['id']==goal_pick.currentData()),False))
        pause_goal.setEnabled(enabled and goal_pick.count()>0 and next((g['status'] in ('active','paused') for g in goals if g['id']==goal_pick.currentData()),False))
        ranked=data['ranked_proposals']
        goal_status.setText(f"{len(goals)} initiative goal(s) · {len(ranked)} ranked proposals. Planning is review-only; nothing starts without approval.")

    def reload():
        data=module.initiative_status(); reload_goals(data)
        ranks={p['suggestion_id']:p['score'] for p in data['ranked_proposals']}
        current=selected()
        entries=module.store.list()
        entries.sort(key=lambda item:(-ranks.get(item['id'],0),-item['id']))
        labels=[(i['id'],f"{'P'+str(ranks[i['id']])+' · ' if i['id'] in ranks else ''}#{i['id']} {i['kind']} · {i['status']} · {i['title']}") for i in entries]
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
    def add_owner_goal():
        title,ok=QInputDialog.getText(page,'Add Apollo goal','Goal title:')
        if not ok or not title.strip(): return
        outcome,ok=QInputDialog.getMultiLineText(page,'Desired outcome','What measurable improvement or result should Apollo pursue?')
        if not ok or not outcome.strip(): return
        try: module.owner_create_goal(title,outcome); reload()
        except Exception as exc: error(exc)

    def propose_owner_step():
        ident=goal_pick.currentData()
        if ident is None: return
        try: module.owner_propose_step(ident); reload()
        except Exception as exc: error(exc)

    def toggle_owner_goal():
        ident=goal_pick.currentData()
        if ident is None: return
        try:
            current=next(g for g in module.initiative_status()['goals'] if g['id']==ident)
            module.owner_set_goal_status(ident,'paused' if current['status']=='active' else 'active')
            reload()
        except Exception as exc: error(exc)

    def schedule_dialog():
        dlg=QDialog(page)
        dlg.setWindowTitle('Apollo scheduled missions')
        dlg.resize(660,570)
        dl=QVBoxLayout(dlg)
        info=QLabel('Set a local date/time and repeat pattern. Apollo must be running; '
                    'a missed run may catch up once within 24 hours. '
                    'Each schedule has a finite run limit.')
        info.setWordWrap(True); dl.addWidget(info)
        form=QFormLayout()
        kind=QComboBox()
        kind.addItem('Public research (Learning Missions)','research')
        kind.addItem('Local Apollo health check','health')
        name=QLineEdit()
        name.setObjectName('schedule_title')
        prompt=QPlainTextEdit()
        prompt.setObjectName('schedule_goal')
        prompt.setMaximumHeight(75)
        ident=selected()
        if ident is not None:
            item=module.store.get(ident)
            if item['kind']=='proposal' and item['status']!='dismissed':
                name.setText(item['title'])
                prompt.setPlainText(item['prompt'])
        date_time=QDateTimeEdit(QDateTime.currentDateTime().addSecs(300))
        date_time.setObjectName('schedule_date_time')
        date_time.setCalendarPopup(True)
        date_time.setDisplayFormat('dd MMM yyyy HH:mm')
        repeat=QComboBox()
        repeat.addItem('Once','once')
        repeat.addItem('Every day','daily')
        repeat.addItem('Every week','weekly')
        max_runs=QSpinBox()
        max_runs.setObjectName('schedule_max_runs')
        max_runs.setRange(1,365)
        max_runs.setValue(30)
        web_approval=QCheckBox('I authorise public web research for this recurring schedule')
        form.addRow('Task type',kind)
        form.addRow('Task title',name)
        form.addRow('Task / research instructions',prompt)
        form.addRow('Starting date and local time',date_time)
        form.addRow('Repeat',repeat)
        form.addRow('Maximum runs',max_runs)
        form.addRow('',web_approval)
        dl.addLayout(form)
        message=QLabel('Research is executed through the existing permission-gated Learning Missions service.')
        message.setWordWrap(True); dl.addWidget(message)
        create=QPushButton('Create approved schedule')
        dl.addWidget(create)
        dl.addWidget(QLabel('Existing schedules'))
        records=QListWidget()
        records.setObjectName('scheduled_missions_list')
        dl.addWidget(records,1)
        history=QLabel('')
        history.setWordWrap(True); dl.addWidget(history)
        controls=QHBoxLayout()
        pause_schedule=QPushButton('Pause')
        resume_schedule=QPushButton('Resume')
        stop_schedule=QPushButton('Stop')
        close_schedule=QPushButton('Close')
        for b in (pause_schedule,resume_schedule,stop_schedule,close_schedule):
            controls.addWidget(b)
        dl.addLayout(controls)

        def kind_changed():
            is_research=kind.currentData()=='research'
            prompt.setEnabled(is_research)
            web_approval.setEnabled(is_research)
            if not is_research:
                if not name.text().strip(): name.setText('Apollo system health check')
                web_approval.setChecked(False)
            message.setText('Approved public-source research becomes a one-step Learning Mission; '
                            'results appear in Learning Missions.' if is_research
                            else 'Runs Apollo local health snapshot only, without public web access.')

        def refresh_schedule_list():
            keep=records.currentItem().data(Qt.UserRole) if records.currentItem() else None
            records.clear()
            for task in module.schedules_status():
                stamp=task['next_local'] or 'No further runs'
                row=QListWidgetItem(f"#{task['id']} [{task['state']}] {task['name']} · "
                                     f"{task['repeat_mode']} · next {stamp} · "
                                     f"{task['run_count']}/{task['max_runs']} runs")
                row.setData(Qt.UserRole,task['id'])
                records.addItem(row)
                if task['id']==keep: records.setCurrentItem(row)
            if not records.currentItem() and records.count(): records.setCurrentRow(0)
            inspect_schedule()

        def inspect_schedule():
            selected_row=records.currentItem()
            if not selected_row:
                history.setText('No scheduled tasks.')
                for b in (pause_schedule,resume_schedule,stop_schedule): b.setEnabled(False)
                return
            sid=selected_row.data(Qt.UserRole)
            task=module.schedules.get(sid)
            latest=module.schedule_history(sid)
            last=latest[0] if latest else None
            message_text=f"Last result: {last['state']} · {last['error'] or last['receipt_json'][:160]}" if last else 'No runs yet.'
            if task['last_error']: message_text+=' · '+task['last_error']
            history.setText(message_text)
            pause_schedule.setEnabled(task['state']=='active')
            resume_schedule.setEnabled(task['state'] in ('paused','blocked'))
            stop_schedule.setEnabled(task['state'] in ('active','paused','blocked'))

        def create_schedule():
            is_research=kind.currentData()=='research'
            title=name.text().strip()
            if not is_research and not title: title='Apollo system health check'
            try:
                created=module.owner_create_schedule(
                    kind=kind.currentData(),name=title,
                    goal=prompt.toPlainText() if is_research else '',
                    start_day=date_time.date().toString('yyyy-MM-dd'),
                    local_time=date_time.time().toString('HH:mm'),
                    repeat=repeat.currentData(),max_runs=max_runs.value(),
                    web_allowed=web_approval.isChecked() if is_research else False)
                message.setText(f"Schedule #{created['id']} created. "
                                "Apollo will run it at the approved local time while running.")
                refresh_schedule_list()
            except Exception as exc: error(exc)

        def change_schedule(action):
            row=records.currentItem()
            if not row: return
            try:
                module.owner_control_schedule(row.data(Qt.UserRole),action)
                refresh_schedule_list()
            except Exception as exc: error(exc)

        kind.currentIndexChanged.connect(lambda *_:kind_changed())
        repeat.currentIndexChanged.connect(lambda *_:max_runs.setEnabled(repeat.currentData()!='once'))
        create.clicked.connect(create_schedule)
        records.currentItemChanged.connect(lambda *_:inspect_schedule())
        pause_schedule.clicked.connect(lambda:change_schedule('pause'))
        resume_schedule.clicked.connect(lambda:change_schedule('resume'))
        stop_schedule.clicked.connect(lambda:change_schedule('stop'))
        close_schedule.clicked.connect(dlg.accept)
        kind_changed()
        refresh_schedule_list()
        dlg.exec()

    schedules_button.clicked.connect(schedule_dialog)
    add_goal.clicked.connect(add_owner_goal)
    next_step.clicked.connect(propose_owner_step)
    pause_goal.clicked.connect(toggle_owner_goal)
    goal_pick.currentIndexChanged.connect(lambda *_:reload_goals(module.initiative_status()))
    enabled.toggled.connect(lambda value:module.store.set_state('enabled','1' if value else '0'))
    listing.currentItemChanged.connect(lambda *_:inspect()); reply.clicked.connect(respond); keep.clicked.connect(lambda:review('accepted')); dismiss.clicked.connect(lambda:review('dismissed')); start.clicked.connect(research); refresh.clicked.connect(reload)
    timer=QTimer(page); timer.setInterval(3000); timer.timeout.connect(reload); timer.start(); reload(); return page
