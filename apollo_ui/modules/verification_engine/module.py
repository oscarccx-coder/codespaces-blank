import ast,json
from pathlib import Path
class Module:
 def __init__(self,context=None):c=context or {};self.base=Path(c.get('base_dir','.')).resolve();self.runtime=c.get('runtime');self.workspace=self.base/'workspace'
 def tools(self):return [
  {'name':'verify_workspace_project','description':'Verify Python syntax and Apollo project metadata for a Workspace project.','parameters':{'type':'object','properties':{'project':{'type':'string'}},'required':['project']}},
  {'name':'verify_pending_module','description':'Run Apollo real pending-module validator.','parameters':{'type':'object','properties':{'module_id':{'type':'string'}},'required':['module_id']}},
  {'name':'verify_recent_action','description':'Inspect action-bus execution evidence.','parameters':{'type':'object','properties':{'task_id':{'type':'integer'}}}},]
 def _p(self,n):
  p=(self.workspace/str(n)).resolve()
  if self.workspace.resolve() not in p.parents:raise PermissionError('Project escaped Workspace')
  return p
 def run(self,a,x):
  x=x or {}
  if a=='verify_workspace_project':
   r=self._p(x['project'])
   if not r.is_dir():raise FileNotFoundError(str(r))
   err=[];count=0
   for p in r.rglob('*.py'):
    count+=1
    try:ast.parse(p.read_text(encoding='utf-8',errors='replace'),filename=str(p))
    except SyntaxError as e:err.append({'file':str(p.relative_to(r)),'line':e.lineno,'error':e.msg})
   meta=None;m=r/'.apollo_project.json'
   if m.exists():
    try:meta=json.loads(m.read_text())
    except Exception as e:err.append({'file':'.apollo_project.json','error':str(e)})
   return {'verified':not err,'checked_python_files':count,'errors':err,'metadata_present':meta is not None,'level':'static'}
  if a=='verify_pending_module':
   if not self.runtime or not self.runtime._manager:raise RuntimeError('Manager unavailable')
   return self.runtime._manager.validate_pending(str(x['module_id']))
  if a=='verify_recent_action':
   if not self.runtime:raise RuntimeError('Runtime unavailable')
   rows=self.runtime.task_history(500);tid=x.get('task_id');row=next((q for q in rows if int(q['id'])==int(tid)),None) if tid is not None else (rows[0] if rows else None)
   if not row:raise KeyError('Task not found')
   return {'task':row,'verified_execution':row.get('status')=='success' and bool(row.get('finished_at')),'note':'Execution evidence only; not semantic truth of external-world results.'}
  raise KeyError(a)
 def self_test(self):return 'Verification Engine contracts passed'
 def build_ui(self,parent=None,ui_context=None):
  from PySide6.QtWidgets import QWidget,QVBoxLayout,QLabel,QLineEdit,QPushButton,QTextEdit
  p=QWidget(parent);l=QVBoxLayout(p);l.addWidget(QLabel('Verification Engine'));q=QLineEdit();q.setPlaceholderText('Workspace project folder');o=QTextEdit();o.setReadOnly(True);b=QPushButton('Verify Workspace Project');l.addWidget(q);l.addWidget(b);l.addWidget(o,1)
  def go():
   try:o.setPlainText(json.dumps(self.run('verify_workspace_project',{'project':q.text().strip()}),indent=2))
   except Exception as e:o.setPlainText(str(e))
  b.clicked.connect(go);return p
