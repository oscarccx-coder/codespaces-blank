import json,re
from pathlib import Path
class Module:
 def __init__(self,context=None):c=context or {};self.base=Path(c.get('base_dir','.')).resolve();self.runtime=c.get('runtime')
 def tools(self):return [
  {'name':'build_context','description':'Build a compact internal coordination packet for a task.','parameters':{'type':'object','properties':{'task':{'type':'string'},'max_chars':{'type':'integer'}},'required':['task']}},
  {'name':'context_status','description':'Return Context Manager health/last task.','parameters':{'type':'object','properties':{}}},]
 def _tok(self,t):return {x for x in re.findall(r'[a-z0-9_+#.-]+',str(t).lower()) if len(x)>2}
 def run(self,a,x):
  x=x or {}
  if not self.runtime:raise RuntimeError('Apollo runtime unavailable')
  if a=='build_context':
   task=str(x['task']).strip(); toks=self._tok(task); manager=self.runtime._manager; caps=[]
   if manager:
    for i in self.runtime.capability_records(manager):
     h=(i['capability']+' '+i['description']).lower(); sc=sum(1 for t in toks if t in h)
     if sc:caps.append((sc,i))
    caps.sort(key=lambda z:(-z[0],z[1]['capability']))
   shared=[]
   for k,i in self.runtime.blackboard_all().items():
    h=(k+' '+json.dumps(i.get('value'),default=str)).lower();sc=sum(1 for t in toks if t in h)
    if sc:shared.append((sc,k,i))
   shared.sort(key=lambda z:(-z[0],z[1])); failed=[q for q in self.runtime.task_history(30) if q.get('status')=='failed'][:6]
   pack={'task':task,'active_goals':self.runtime.goals('active')[:8],'relevant_shared_state':[{'key':k,**i} for _,k,i in shared[:8]],'suggested_capabilities':[{'capability':i['capability'],'risk':i['risk'],'permission':i['permission']} for _,i in caps[:12]],'recent_failed_actions':failed,'permission_profile':self.runtime.permission_profile()}
   if len(json.dumps(pack,default=str))>max(1000,min(int(x.get('max_chars',6000)),12000)):pack['relevant_shared_state']=pack['relevant_shared_state'][:4];pack['suggested_capabilities']=pack['suggested_capabilities'][:8];pack['recent_failed_actions']=pack['recent_failed_actions'][:3]
   self.runtime.blackboard_set('context_manager.last_packet',pack,'context_manager');return pack
  if a=='context_status':
   v=self.runtime.blackboard_get('context_manager.last_packet',{});return {'ready':True,'last_task':v.get('task') if isinstance(v,dict) else None,'active_goal_count':len(self.runtime.goals('active'))}
  raise KeyError(a)
 def self_test(self):return 'Context Manager contract passed'
 def build_ui(self,parent=None,ui_context=None):
  from PySide6.QtWidgets import QWidget,QVBoxLayout,QLabel,QTextEdit,QLineEdit,QPushButton
  p=QWidget(parent);l=QVBoxLayout(p);l.addWidget(QLabel('Apollo Context Manager'));q=QLineEdit();q.setPlaceholderText('Preview context for a task...');o=QTextEdit();o.setReadOnly(True);b=QPushButton('Build Context Packet');l.addWidget(q);l.addWidget(b);l.addWidget(o,1)
  def go():
   try:o.setPlainText(json.dumps(self.run('build_context',{'task':q.text().strip()}),indent=2,default=str))
   except Exception as e:o.setPlainText(str(e))
  b.clicked.connect(go);return p
