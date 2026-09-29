import ast,json,time
from datetime import datetime
from pathlib import Path
class Module:
 CRITICAL={'core_services','file_builder','module_factory','memory_bank','orchestrator','file_manager','context_manager','verification_engine','task_engine','model_runtime','self_improvement_lab'}
 def __init__(self,context=None):c=context or {};self.base=Path(c.get('base_dir','.')).resolve();self.runtime=c.get('runtime');self.out=self.base/'storage'/'reports'/'benchmarks';self.out.mkdir(parents=True,exist_ok=True)
 def tools(self):return [{'name':'run_benchmarks','description':'Run Apollo infrastructure regression checks without invoking an LLM.','parameters':{'type':'object','properties':{}}},{'name':'last_report','description':'Read most recent benchmark report.','parameters':{'type':'object','properties':{}}}]
 def run(self,a,x):
  if a=='run_benchmarks':
   st=time.perf_counter();checks=[];errs=[];cnt=0
   for p in self.base.rglob('*.py'):
    if '__pycache__' in p.parts or 'workspace' in p.parts:continue
    cnt+=1
    try:ast.parse(p.read_text(encoding='utf-8',errors='replace'),filename=str(p))
    except Exception as e:errs.append({'file':str(p.relative_to(self.base)),'error':str(e)})
   checks.append({'name':'python_syntax','ok':not errs,'files':cnt,'errors':errs[:20]});m=self.runtime._manager if self.runtime else None;loaded=set();me={}
   if m:loaded={q['id'] for q in m.list_modules() if q.get('loaded')};me=m.errors()
   miss=sorted(self.CRITICAL-loaded);checks.append({'name':'critical_modules_loaded','ok':not miss,'missing':miss,'manager_errors':me});caps=self.runtime.capability_records(m) if self.runtime and m else [];names={q['capability'] for q in caps};req={'file_manager__move_item','context_manager__build_context','verification_engine__verify_workspace_project','task_engine__create_plan','module_factory__create_candidate'};checks.append({'name':'critical_capabilities','ok':req.issubset(names),'missing':sorted(req-names)})
   report={'created_at':datetime.now().isoformat(timespec='seconds'),'version':'7.5.0','ok':all(q['ok'] for q in checks),'elapsed_seconds':round(time.perf_counter()-st,4),'checks':checks};t=self.out/f"benchmark_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json";t.write_text(json.dumps(report,indent=2,default=str));
   if self.runtime:self.runtime.blackboard_set('benchmarks.last',report,'benchmark_suite')
   return {**report,'file':str(t)}
  if a=='last_report':
   fs=sorted(self.out.glob('benchmark_*.json'),reverse=True);return {'available':False} if not fs else {'available':True,'file':str(fs[0]),'report':json.loads(fs[0].read_text())}
  raise KeyError(a)
 def self_test(self):return 'Benchmark Suite contracts passed'
 def build_ui(self,parent=None,ui_context=None):
  from PySide6.QtWidgets import QWidget,QVBoxLayout,QLabel,QPushButton,QTextEdit
  p=QWidget(parent);l=QVBoxLayout(p);l.addWidget(QLabel('Apollo 7.5 Benchmark Suite'));b=QPushButton('Run Infrastructure Benchmarks');o=QTextEdit();o.setReadOnly(True);l.addWidget(b);l.addWidget(o,1)
  def go():
   try:o.setPlainText(json.dumps(self.run('run_benchmarks',{}),indent=2,default=str))
   except Exception as e:o.setPlainText(str(e))
  b.clicked.connect(go);return p
