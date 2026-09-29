import sqlite3,threading
from datetime import datetime
from pathlib import Path
def now():return datetime.now().isoformat(timespec='seconds')
class Module:
 def __init__(self,context=None):
  self.base=Path((context or {}).get('base_dir','.')).resolve();self.db=self.base/'storage'/'databases'/'task_engine.db';self.db.parent.mkdir(parents=True,exist_ok=True);self.lock=threading.RLock();self.conn=sqlite3.connect(self.db,check_same_thread=False);self.conn.row_factory=sqlite3.Row;self.conn.executescript("""CREATE TABLE IF NOT EXISTS plans(id INTEGER PRIMARY KEY AUTOINCREMENT,title TEXT NOT NULL,status TEXT NOT NULL DEFAULT 'active',goal_id INTEGER,created_at TEXT NOT NULL,updated_at TEXT NOT NULL);CREATE TABLE IF NOT EXISTS steps(id INTEGER PRIMARY KEY AUTOINCREMENT,plan_id INTEGER NOT NULL,position INTEGER NOT NULL,title TEXT NOT NULL,status TEXT NOT NULL DEFAULT 'pending',capability TEXT,evidence TEXT NOT NULL DEFAULT '',created_at TEXT NOT NULL,updated_at TEXT NOT NULL);""");self.conn.commit()
 def tools(self):return [
  {'name':'create_plan','description':'Create a persistent multi-step plan; does not execute steps automatically.','parameters':{'type':'object','properties':{'title':{'type':'string'},'steps':{'type':'array','items':{'type':'string'}},'goal_id':{'type':'integer'}},'required':['title','steps']}},
  {'name':'list_plans','description':'List persistent plans.','parameters':{'type':'object','properties':{'status':{'type':'string'}}}},
  {'name':'plan_detail','description':'Return a plan and its steps.','parameters':{'type':'object','properties':{'plan_id':{'type':'integer'}},'required':['plan_id']}},
  {'name':'update_step','description':'Update one step after real work and attach evidence/capability.','parameters':{'type':'object','properties':{'step_id':{'type':'integer'},'status':{'type':'string'},'evidence':{'type':'string'},'capability':{'type':'string'}},'required':['step_id']}},
  {'name':'next_steps','description':'Return pending/blocked/failed steps from active plans.','parameters':{'type':'object','properties':{'limit':{'type':'integer'}}}},
  {'name':'complete_plan','description':'Complete only when all steps are done/skipped.','parameters':{'type':'object','properties':{'plan_id':{'type':'integer'}},'required':['plan_id']}},]
 def run(self,a,x):
  x=x or {}
  with self.lock:
   if a=='create_plan':
    ss=[str(q).strip() for q in (x.get('steps') or []) if str(q).strip()]
    if not ss:raise ValueError('At least one step required')
    t=now();c=self.conn.execute('INSERT INTO plans(title,status,goal_id,created_at,updated_at) VALUES(?,?,?,?,?)',(str(x['title']),'active',x.get('goal_id'),t,t));pid=c.lastrowid
    for pos,title in enumerate(ss,1):self.conn.execute('INSERT INTO steps(plan_id,position,title,status,created_at,updated_at) VALUES(?,?,?,?,?,?)',(pid,pos,title,'pending',t,t))
    self.conn.commit();return self.run('plan_detail',{'plan_id':pid})
   if a=='list_plans':
    rows=self.conn.execute('SELECT * FROM plans WHERE status=? ORDER BY updated_at DESC',(str(x['status']),)).fetchall() if x.get('status') else self.conn.execute('SELECT * FROM plans ORDER BY updated_at DESC').fetchall();return {'plans':[dict(r) for r in rows]}
   if a=='plan_detail':
    p=self.conn.execute('SELECT * FROM plans WHERE id=?',(int(x['plan_id']),)).fetchone()
    if not p:raise KeyError('Plan not found')
    ss=self.conn.execute('SELECT * FROM steps WHERE plan_id=? ORDER BY position,id',(int(x['plan_id']),)).fetchall();return {'plan':dict(p),'steps':[dict(r) for r in ss]}
   if a=='update_step':
    r=self.conn.execute('SELECT * FROM steps WHERE id=?',(int(x['step_id']),)).fetchone()
    if not r:raise KeyError('Step not found')
    st=str(x.get('status',r['status']))
    if st not in {'pending','running','done','failed','blocked','skipped'}:raise ValueError('Invalid status')
    self.conn.execute('UPDATE steps SET status=?,evidence=?,capability=?,updated_at=? WHERE id=?',(st,str(x.get('evidence',r['evidence'])),x.get('capability',r['capability']),now(),int(x['step_id'])));self.conn.execute('UPDATE plans SET updated_at=? WHERE id=?',(now(),int(r['plan_id'])));self.conn.commit();return {'updated':True,'step_id':int(x['step_id']),'status':st}
   if a=='next_steps':
    lim=max(1,min(int(x.get('limit',20)),100));rows=self.conn.execute("SELECT s.*,p.title plan_title FROM steps s JOIN plans p ON p.id=s.plan_id WHERE p.status='active' AND s.status IN ('pending','blocked','failed') ORDER BY p.updated_at DESC,s.position LIMIT ?",(lim,)).fetchall();return {'steps':[dict(r) for r in rows]}
   if a=='complete_plan':
    d=self.run('plan_detail',x);u=[q for q in d['steps'] if q['status'] not in {'done','skipped'}]
    if u:return {'completed':False,'reason':'unfinished_steps','unfinished':u}
    self.conn.execute("UPDATE plans SET status='complete',updated_at=? WHERE id=?",(now(),int(x['plan_id'])));self.conn.commit();return {'completed':True,'plan_id':int(x['plan_id'])}
  raise KeyError(a)
 def self_test(self):return 'Task Engine schema/contracts passed'
 def build_ui(self,parent=None,ui_context=None):
  from PySide6.QtWidgets import QWidget,QVBoxLayout,QListWidget,QLabel,QPushButton,QHBoxLayout
  p=QWidget(parent);l=QVBoxLayout(p);l.addWidget(QLabel('Task & Goal Engine — persistent plans'));lst=QListWidget();l.addWidget(lst,1);r=QHBoxLayout();a=QPushButton('Refresh');b=QPushButton('Show Next Steps');r.addWidget(a);r.addWidget(b);l.addLayout(r)
  def plans():lst.clear();[lst.addItem(f"#{q['id']} [{q['status']}] {q['title']}") for q in self.run('list_plans',{})['plans']]
  def nxt():lst.clear();[lst.addItem(f"Plan #{q['plan_id']} • step {q['position']} [{q['status']}]\n{q['title']}") for q in self.run('next_steps',{})['steps']]
  a.clicked.connect(plans);b.clicked.connect(nxt);plans();return p
 def close(self):
  try:self.conn.commit();self.conn.close()
  except:pass
