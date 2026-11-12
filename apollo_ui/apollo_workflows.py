"""Owner-started finite workflow graphs; no arbitrary shell or model approvals."""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import sqlite3
import threading
import time
import uuid
VERSION=1
ACTIVE=('QUEUED','RUNNING','PAUSED','STOP_REQUESTED')
REGISTRY={
 'research_brief':{'title':'Public research brief','web':True,'stages':[
  ('sources','researcher',(),'Fetch public pages'),('study','analyst',('sources',),'Extract grounded notes'),
  ('verify','verifier',('sources','study'),'Check source quotations'),('output','librarian',('verify',),'Save report and optional topic memory')]},
 'knowledge_brief':{'title':'Saved knowledge brief','web':False,'stages':[
  ('memory','librarian',(),'Retrieve topic memory'),('synthesis','analyst',('memory',),'Draft cited brief'),
  ('verify','verifier',('memory','synthesis'),'Check citation IDs'),('output','librarian',('verify',),'Save brief')]},
 'foundry_assessment':{'title':'Foundry readiness assessment','web':False,'stages':[
  ('project','architect',(),'Read project state'),('verify','verifier',('project',),'Inspect checks and source-matched test history'),('output','integrator',('verify',),'Save readiness handoff')]},
 'application_benchmark':{'title':'Local application benchmark','web':False,'stages':[
  ('questions','tester',(),'Prepare fresh problems'),('answers','analyst',('questions',),'Answer without key'),
  ('verify','verifier',('questions','answers'),'Grade exact results'),('output','librarian',('verify',),'Save measured results')]},
 'configuration_audit':{'title':'Read-only configuration audit','web':False,'stages':[
  ('settings','auditor',(),'Inspect allowlisted settings'),('verify','verifier',('settings',),'Summarise redacted findings'),('output','integrator',('verify',),'Save audit report')]}}

def stamp(): return datetime.now(timezone.utc).isoformat(timespec='seconds')
def text(value,limit=1000,minimum=1):
    value=str(value or '').strip()
    if not minimum<=len(value)<=limit or '\x00' in value: raise ValueError(f'Enter {minimum}-{limit} characters.')
    return value

def route_request(question,*,tools=True,temporary=False):
    q=str(question).strip().lower()
    if temporary or not tools: return {'mode':'Chat','reason':'Tools are unavailable; use the selected model only.'}
    if re.match(r'^(?:start|status|pause|resume|stop|list|show)\b',q) and any(w in q for w in ('workflow','practice','learning mission')):
        return {'mode':'Chat','reason':'Use the deterministic owner-command channel.'}
    if re.match(r'^(?:please\s+)?(?:research|search the web|look up|investigate online)\b',q):
        deep=any(w in q for w in ('compare','in depth','in-depth','deep research','comprehensive'))
        return {'mode':'Deep research' if deep else 'Web research','reason':'The owner explicitly requested public research.'}
    if re.match(r'^(?:please\s+)?(?:write|fix|debug|build|implement|refactor)\b',q) and any(w in q for w in ('code','python','app','program','function','bug','script')):
        return {'mode':'Coding','reason':'Use existing guarded coding tools and the selected model.'}
    return {'mode':'Chat','reason':'Use local chat; no implicit web or paid-model escalation.'}

class WorkflowStore:
    def __init__(self,root,*,memory=False):
        self.root=Path(root).resolve(); self.lock=threading.RLock(); folder=self.root/'storage'/'databases'
        if not memory: folder.mkdir(parents=True,exist_ok=True)
        self.db=sqlite3.connect(':memory:' if memory else str(folder/'apollo_workflows.db'),timeout=15,check_same_thread=False)
        self.db.row_factory=sqlite3.Row
        self.db.executescript('''PRAGMA foreign_keys=ON;
        CREATE TABLE IF NOT EXISTS workflow_runs(
         id TEXT PRIMARY KEY,workflow TEXT NOT NULL,version INTEGER NOT NULL,recipe_id INTEGER,
         goal TEXT NOT NULL,project_id INTEGER,target_node_id INTEGER,index_memory INTEGER NOT NULL,
         web_allowed INTEGER NOT NULL,state TEXT NOT NULL,created_at TEXT NOT NULL,updated_at TEXT NOT NULL,
         heartbeat REAL NOT NULL DEFAULT 0,lease_owner TEXT NOT NULL DEFAULT '',lease_until REAL NOT NULL DEFAULT 0,last_error TEXT NOT NULL DEFAULT '');
        CREATE TABLE IF NOT EXISTS workflow_stages(
         run_id TEXT NOT NULL REFERENCES workflow_runs(id),name TEXT NOT NULL,ordinal INTEGER NOT NULL,
         role TEXT NOT NULL,dependencies TEXT NOT NULL,state TEXT NOT NULL DEFAULT 'PENDING',attempts INTEGER NOT NULL DEFAULT 0,
         started_at TEXT NOT NULL DEFAULT '',finished_at TEXT NOT NULL DEFAULT '',result_json TEXT NOT NULL DEFAULT '{}',error TEXT NOT NULL DEFAULT '',PRIMARY KEY(run_id,name));
        CREATE TABLE IF NOT EXISTS workflow_handoffs(
         id INTEGER PRIMARY KEY,run_id TEXT NOT NULL REFERENCES workflow_runs(id),stage TEXT NOT NULL,role TEXT NOT NULL,
         summary TEXT NOT NULL,receipt_sha256 TEXT NOT NULL,next_action TEXT NOT NULL,created_at TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS workflow_procedures(
         id INTEGER PRIMARY KEY,workflow TEXT NOT NULL,version INTEGER NOT NULL,title TEXT NOT NULL,
         state TEXT NOT NULL DEFAULT 'candidate',support_json TEXT NOT NULL DEFAULT '[]',updated_at TEXT NOT NULL,UNIQUE(workflow,version));''')
    def close(self):
        with self.lock: self.db.close()
    def _run(self,ident):
        row=self.db.execute('SELECT * FROM workflow_runs WHERE id=?',(str(ident),)).fetchone()
        if row is None: raise KeyError('Workflow run not found.')
        return dict(row)
    def start(self,workflow,goal,*,owner_confirmed=False,web_allowed=False,project_id=None,target_node_id=None,index_memory=False,recipe_id=None):
        if owner_confirmed is not True: raise PermissionError('Only the owner can start a workflow.')
        if workflow not in REGISTRY: raise ValueError('Choose a registered workflow.')
        graph=REGISTRY[workflow]['stages']; preceding=set()
        if not 1<=len(graph)<=8: raise ValueError('Workflow graphs require one to eight stages.')
        for name,role,dependencies,description in graph:
            if name in preceding or not set(dependencies)<=preceding: raise ValueError('Invalid graph dependencies or duplicate stage.')
            preceding.add(name)
        goal=text(goal,1000,5)
        if type(web_allowed) is not bool or type(index_memory) is not bool: raise ValueError('Permissions must be explicit booleans.')
        if REGISTRY[workflow]['web'] and not web_allowed: raise PermissionError('Public research needs explicit web authorisation.')
        for value in (project_id,target_node_id):
            if value is not None and (type(value) is not int or value<1): raise ValueError('Choose a positive existing project/node ID.')
        if workflow=='foundry_assessment' and project_id is None: raise ValueError('A Foundry project ID is required.')
        with self.lock,self.db:
            self.db.execute('BEGIN IMMEDIATE')
            if self.db.execute("SELECT count(*) FROM workflow_runs WHERE state IN ('QUEUED','RUNNING','PAUSED','STOP_REQUESTED')").fetchone()[0]>=12: raise ValueError('Maximum twelve active workflows.')
            if recipe_id is not None:
                recipe=self.db.execute('SELECT * FROM workflow_procedures WHERE id=?',(recipe_id,)).fetchone()
                if not recipe or recipe['state']!='approved' or recipe['workflow']!=workflow or recipe['version']!=VERSION: raise PermissionError('Procedure is not approved for the current workflow version.')
            ident=uuid.uuid4().hex[:12]
            self.db.execute('INSERT INTO workflow_runs(id,workflow,version,recipe_id,goal,project_id,target_node_id,index_memory,web_allowed,state,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)',
                (ident,workflow,VERSION,recipe_id,goal,project_id,target_node_id,int(index_memory),int(web_allowed),'QUEUED',stamp(),stamp()))
            for ordinal,(name,role,deps,_) in enumerate(graph): self.db.execute('INSERT INTO workflow_stages(run_id,name,ordinal,role,dependencies) VALUES(?,?,?,?,?)',(ident,name,ordinal,role,json.dumps(deps)))
        return self.status(ident)
    def list(self):
        with self.lock: return [dict(r) for r in self.db.execute('SELECT * FROM workflow_runs ORDER BY created_at DESC,rowid DESC LIMIT 100')]
    def status(self,ident):
        with self.lock:
            run=self._run(ident); run['stages']=[]
            for row in self.db.execute('SELECT * FROM workflow_stages WHERE run_id=? ORDER BY ordinal',(ident,)):
                s=dict(row); s['result']=json.loads(s.pop('result_json')); s['dependencies']=json.loads(s['dependencies']); run['stages'].append(s)
            run['handoffs']=[dict(r) for r in self.db.execute('SELECT * FROM workflow_handoffs WHERE run_id=? ORDER BY id',(ident,))]
            run['completed_stages']=sum(s['state']=='DONE' for s in run['stages'])
            run['current_stage']=next((s['name'] for s in run['stages'] if s['state']!='DONE'),'complete')
            run['heartbeat_age_seconds']=max(0,time.time()-run['heartbeat']) if run['heartbeat'] else None
            return run
    def control(self,ident,action,*,owner_confirmed=False):
        if owner_confirmed is not True: raise PermissionError('An explicit owner action is required.')
        with self.lock,self.db:
            run=self._run(ident)
            if action=='pause' and run['state'] in ('QUEUED','RUNNING'): state='PAUSED'
            elif action=='stop' and run['state'] in ACTIVE+('BLOCKED',): state='STOP_REQUESTED' if run['lease_until']>time.time() else 'STOPPED'
            elif action=='resume' and run['state'] in ('PAUSED','BLOCKED'):
                if run['lease_until']>time.time(): raise ValueError('The current stage is still finishing.')
                self.db.execute("UPDATE workflow_stages SET state='PENDING',error='' WHERE run_id=? AND state='FAILED'",(ident,)); state='QUEUED'
            else: raise ValueError('Action unavailable for the current state.')
            self.db.execute('UPDATE workflow_runs SET state=?,updated_at=? WHERE id=?',(state,stamp(),ident))
        return self.status(ident)
    def pick(self,owner):
        now=time.time()
        with self.lock,self.db:
            self.db.execute('BEGIN IMMEDIATE')
            self.db.execute("UPDATE workflow_runs SET state='STOPPED',lease_owner='',lease_until=0,updated_at=? WHERE state='STOP_REQUESTED' AND lease_until<=?",(stamp(),now))
            for row in self.db.execute("SELECT * FROM workflow_runs WHERE state IN ('QUEUED','RUNNING') AND lease_until<=? ORDER BY created_at,rowid",(now,)).fetchall():
                run=dict(row)
                if run['version']!=VERSION:
                    self.db.execute("UPDATE workflow_runs SET state='BLOCKED',last_error=? WHERE id=?",('Workflow version changed; start a new reviewed run.',run['id'])); continue
                stages=self.db.execute('SELECT * FROM workflow_stages WHERE run_id=? ORDER BY ordinal',(run['id'],)).fetchall()
                done={s['name'] for s in stages if s['state']=='DONE'}
                pending=next((s for s in stages if s['state']!='DONE' and set(json.loads(s['dependencies']))<=done),None)
                if pending is None:
                    if len(done)==len(stages): self.db.execute("UPDATE workflow_runs SET state='COMPLETED',updated_at=? WHERE id=?",(stamp(),run['id']))
                    continue
                self.db.execute("UPDATE workflow_runs SET state='RUNNING',heartbeat=?,lease_owner=?,lease_until=?,updated_at=? WHERE id=?",(now,owner,now+600,stamp(),run['id']))
                self.db.execute("UPDATE workflow_stages SET state='RUNNING',attempts=attempts+1,started_at=?,error='' WHERE run_id=? AND name=?",(stamp(),run['id'],pending['name']))
                return run['id'],pending['name']
        return None
    def finish(self,ident,stage,owner,result=None,error=None):
        encoded=json.dumps(result or {},ensure_ascii=False)
        if len(encoded)>64000: raise ValueError('Stage result exceeds the durable receipt limit.')
        with self.lock,self.db:
            self.db.execute('BEGIN IMMEDIATE'); run=self._run(ident)
            if run['lease_owner']!=owner or run['lease_until']<time.time(): raise PermissionError('Stale worker cannot commit a workflow result.')
            target=self.db.execute('SELECT * FROM workflow_stages WHERE run_id=? AND name=?',(ident,stage)).fetchone()
            if not target or target['state']!='RUNNING': raise ValueError('Stage was not running.')
            failed=str(error or '')[:1000]
            self.db.execute('UPDATE workflow_stages SET state=?,result_json=?,error=?,finished_at=? WHERE run_id=? AND name=?',('FAILED' if failed else 'DONE',encoded,failed,stamp(),ident,stage))
            remaining=self.db.execute("SELECT name FROM workflow_stages WHERE run_id=? AND state<>'DONE' ORDER BY ordinal LIMIT 1",(ident,)).fetchone()
            state='STOPPED' if run['state']=='STOP_REQUESTED' else 'BLOCKED' if failed else 'PAUSED' if run['state']=='PAUSED' else 'RUNNING' if remaining else 'COMPLETED'
            next_action='Owner review/retry: '+failed if failed else 'Run '+remaining['name'] if remaining else 'Complete: inspect output and checks'
            self.db.execute('INSERT INTO workflow_handoffs(run_id,stage,role,summary,receipt_sha256,next_action,created_at) VALUES(?,?,?,?,?,?,?)',
                (ident,stage,target['role'],failed or str((result or {}).get('summary') or 'Stage completed; inspect receipt.')[:1000],hashlib.sha256(encoded.encode()).hexdigest(),next_action[:1200],stamp()))
            self.db.execute("UPDATE workflow_runs SET state=?,lease_owner='',lease_until=0,heartbeat=?,last_error=?,updated_at=? WHERE id=?",(state,time.time(),failed,stamp(),ident))
            if state=='COMPLETED': self._propose(run['workflow'])
        return self.status(ident)
    def _propose(self,workflow):
        supports=[]
        for row in self.db.execute("SELECT r.id,s.result_json FROM workflow_runs r JOIN workflow_stages s ON r.id=s.run_id AND s.name='verify' WHERE r.workflow=? AND r.version=? AND r.state='COMPLETED' ORDER BY r.rowid DESC LIMIT 20",(workflow,VERSION)):
            if json.loads(row['result_json']).get('contract_passed') is True: supports.append(row['id'])
        if len(supports)<2: return
        self.db.execute('INSERT INTO workflow_procedures(workflow,version,title,support_json,updated_at) VALUES(?,?,?,?,?) ON CONFLICT(workflow,version) DO UPDATE SET support_json=excluded.support_json,updated_at=excluded.updated_at',
            (workflow,VERSION,REGISTRY[workflow]['title']+' procedure',json.dumps(supports),stamp()))
    def procedures(self):
        with self.lock:
            rows=[dict(r) for r in self.db.execute('SELECT * FROM workflow_procedures ORDER BY id DESC')]
            for r in rows:
                r['supporting_runs']=json.loads(r.pop('support_json'))
                r['recorded_failed_stages']=self.db.execute("SELECT count(*) FROM workflow_handoffs h JOIN workflow_runs r ON h.run_id=r.id WHERE r.workflow=? AND r.version=? AND h.next_action LIKE 'Owner review/retry:%'",(r['workflow'],r['version'])).fetchone()[0]
                r['confidence_note']=f"{len(r['supporting_runs'])} completed runs passed narrow checks; {r['recorded_failed_stages']} failed stage attempts. Not general reliability or mastery."
            return rows
    def review_procedure(self,ident,approve,*,owner_confirmed=False,title=None):
        if owner_confirmed is not True or type(approve) is not bool: raise PermissionError('Only the owner can approve or revoke procedures.')
        with self.lock,self.db:
            row=self.db.execute('SELECT * FROM workflow_procedures WHERE id=?',(int(ident),)).fetchone()
            if row is None: raise KeyError('Procedure not found.')
            if approve and len(json.loads(row['support_json']))<2: raise ValueError('Two checked successful runs are required.')
            self.db.execute('UPDATE workflow_procedures SET state=?,title=?,updated_at=? WHERE id=?',('approved' if approve else 'revoked',text(title,160) if title else row['title'],stamp(),ident))
        return next(r for r in self.procedures() if r['id']==int(ident))

class WorkflowService:
    def __init__(self,root,executor,*,validation=False,ready=None):
        self.store=WorkflowStore(root,memory=validation); self.executor=executor; self.owner=uuid.uuid4().hex
        self.closed=threading.Event(); self.wake=threading.Event(); self.thread=None
        self.validation=validation; self.ready=ready or (lambda:True); self.last_worker_error=''
    def activate(self):
        if self.closed.is_set(): raise RuntimeError('Workflow service is disabled.')
        with self.store.lock:
            if not self.validation and (self.thread is None or not self.thread.is_alive()):
                self.thread=threading.Thread(target=self._loop,name='ApolloWorkflows',daemon=True); self.thread.start()
    def start(self,workflow,goal,**options):
        if self.closed.is_set(): raise RuntimeError('Workflow service is disabled.')
        run=self.store.start(workflow,goal,**options); self.activate(); self.wake.set(); return run
    def tick(self):
        if self.closed.is_set() or not self.ready(): return None
        job=self.store.pick(self.owner)
        if job is None: return None
        ident,stage=job
        try:
            result=self.executor(self.store.status(ident),stage)
            if not isinstance(result,dict): raise TypeError('Stage must return a receipt object.')
            return self.store.finish(ident,stage,self.owner,result)
        except Exception as exc: return self.store.finish(ident,stage,self.owner,error=f'{type(exc).__name__}: {exc}')
    def _loop(self):
        while not self.closed.is_set():
            try: self.tick()
            except Exception as exc: self.last_worker_error=f'{type(exc).__name__}: {exc}'[:600]
            self.wake.wait(1); self.wake.clear()
    def close(self):
        self.closed.set(); self.wake.set()
        if self.thread: self.thread.join(timeout=0.3)
        if self.validation: self.store.close()
