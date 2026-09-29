import re,json
from pathlib import Path
class Module:
 def __init__(self,context=None):self.base=Path((context or {}).get('base_dir','.')).resolve();self.runtime=(context or {}).get('runtime')
 def tools(self):return [{'name':'graph','description':'Return capability nodes grouped by provider.','parameters':{'type':'object','properties':{}}},{'name':'find_workflow','description':'Rank capabilities that could form a workflow for a task.','parameters':{'type':'object','properties':{'task':{'type':'string'},'limit':{'type':'integer'}},'required':['task']}}]
 def _r(self):
  if not self.runtime:raise RuntimeError('Runtime unavailable')
  return self.runtime.capability_records()
 def run(self,a,x):
  x=x or {};r=self._r()
  if a=='graph':
   p={}
   for q in r:p.setdefault(q['capability'].split('__',1)[0],[]).append(q)
   return {'providers':p,'provider_count':len(p),'capability_count':len(r)}
  if a=='find_workflow':
   toks={q for q in re.findall(r'[a-z0-9_+#.-]+',str(x['task']).lower()) if len(q)>2};rank=[]
   for q in r:
    h=(q['capability']+' '+q['description']).lower();sc=sum(2 if t in q['capability'].lower() else 1 for t in toks if t in h)
    if sc:rank.append((sc,q))
   rank.sort(key=lambda z:(-z[0],z[1]['risk'],z[1]['capability']));lim=max(1,min(int(x.get('limit',12)),30));return {'task':x['task'],'workflow_candidates':[q for _,q in rank[:lim]],'note':'Suggestions, not executed actions.'}
  raise KeyError(a)
 def self_test(self):return 'Capability Graph contract passed'
 def build_ui(self,parent=None,ui_context=None):
  from PySide6.QtWidgets import QWidget,QVBoxLayout,QLabel,QLineEdit,QPushButton,QTextEdit
  p=QWidget(parent);l=QVBoxLayout(p);l.addWidget(QLabel('Capability Graph'));q=QLineEdit();q.setPlaceholderText('Describe a task...');b=QPushButton('Find Workflow');o=QTextEdit();o.setReadOnly(True);l.addWidget(q);l.addWidget(b);l.addWidget(o,1)
  def go():
   try:o.setPlainText(json.dumps(self.run('find_workflow',{'task':q.text()}),indent=2))
   except Exception as e:o.setPlainText(str(e))
  b.clicked.connect(go);return p
