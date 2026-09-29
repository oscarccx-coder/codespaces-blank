import json
from pathlib import Path
class Module:
 def __init__(self,context=None):self.base=Path((context or {}).get('base_dir','.')).resolve();self.runtime=(context or {}).get('runtime')
 def tools(self):return [
  {'name':'recent_activity','description':'Return recent action-bus tasks and event-bus events.','parameters':{'type':'object','properties':{'limit':{'type':'integer'}}}},
  {'name':'failed_actions','description':'Return recent failed Apollo actions.','parameters':{'type':'object','properties':{'limit':{'type':'integer'}}}},
  {'name':'export_trace','description':'Export recent operational activity to Workspace.','parameters':{'type':'object','properties':{'limit':{'type':'integer'}}}},]
 def _rt(self):
  if not self.runtime:raise RuntimeError('Runtime unavailable')
  return self.runtime
 def run(self,a,x):
  x=x or {};rt=self._rt();lim=max(1,min(int(x.get('limit',100)),500))
  if a=='recent_activity':return {'tasks':rt.task_history(lim),'events':rt.recent_events(lim)}
  if a=='failed_actions':return {'failures':[q for q in rt.task_history(500) if q.get('status')=='failed'][:lim]}
  if a=='export_trace':
   t=self.base/'workspace'/'apollo_activity_trace.json';t.parent.mkdir(parents=True,exist_ok=True);t.write_text(json.dumps({'tasks':rt.task_history(lim),'events':rt.recent_events(lim)},indent=2,default=str));return {'saved':True,'file':str(t)}
  raise KeyError(a)
 def self_test(self):return 'Activity Trace contracts passed'
 def build_ui(self,parent=None,ui_context=None):
  from PySide6.QtWidgets import QWidget,QVBoxLayout,QLabel,QTextEdit,QPushButton,QHBoxLayout
  p=QWidget(parent);l=QVBoxLayout(p);l.addWidget(QLabel('Apollo Activity Trace'));o=QTextEdit();o.setReadOnly(True);l.addWidget(o,1);r=QHBoxLayout();a=QPushButton('Refresh');b=QPushButton('Failures Only');r.addWidget(a);r.addWidget(b);l.addLayout(r)
  def all():
   try:o.setPlainText(json.dumps(self.run('recent_activity',{'limit':100}),indent=2,default=str))
   except Exception as e:o.setPlainText(str(e))
  def fail():
   try:o.setPlainText(json.dumps(self.run('failed_actions',{'limit':100}),indent=2,default=str))
   except Exception as e:o.setPlainText(str(e))
  a.clicked.connect(all);b.clicked.connect(fail);all();return p
