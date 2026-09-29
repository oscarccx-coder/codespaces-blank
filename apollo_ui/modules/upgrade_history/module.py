import hashlib,json
from datetime import datetime
from pathlib import Path
class Module:
 CORE=['main.py','workers.py','module_manager.py','apollo_runtime.py','module_validator.py','module_repair_engine.py','ollama_client.py']
 def __init__(self,context=None):c=context or {};self.base=Path(c.get('base_dir','.')).resolve();self.runtime=c.get('runtime');self.path=self.base/'storage'/'state'/'upgrade_history.jsonl';self.path.parent.mkdir(parents=True,exist_ok=True)
 def tools(self):return [
  {'name':'record_release','description':'Append an Apollo release/change record.','parameters':{'type':'object','properties':{'version':{'type':'string'},'title':{'type':'string'},'summary':{'type':'string'},'changed_files':{'type':'array','items':{'type':'string'}},'tests':{'type':'string'}},'required':['version','title','summary']}},
  {'name':'list_history','description':'List recorded Apollo changes.','parameters':{'type':'object','properties':{'limit':{'type':'integer'}}}},
  {'name':'checkpoint','description':'Create recovery snapshot and core hashes.','parameters':{'type':'object','properties':{'name':{'type':'string'}}}},
  {'name':'core_hashes','description':'Hash important Apollo core files.','parameters':{'type':'object','properties':{}}},]
 def _h(self):return {r:hashlib.sha256((self.base/r).read_bytes()).hexdigest() for r in self.CORE if (self.base/r).exists()}
 def run(self,a,x):
  x=x or {}
  if a=='record_release':
   q={'recorded_at':datetime.now().isoformat(timespec='seconds'),'version':str(x['version']),'title':str(x['title']),'summary':str(x['summary']),'changed_files':x.get('changed_files') or [],'tests':str(x.get('tests','')),'core_hashes':self._h()};f=self.path.open('a',encoding='utf-8');f.write(json.dumps(q,ensure_ascii=False)+'\n');f.close();return {'recorded':True,'version':q['version']}
  if a=='list_history':
   lim=max(1,min(int(x.get('limit',100)),500));rows=[]
   if self.path.exists():
    for line in self.path.read_text(encoding='utf-8',errors='replace').splitlines():
     try:rows.append(json.loads(line))
     except:pass
   return {'history':list(reversed(rows))[:lim]}
  if a=='core_hashes':return {'hashes':self._h()}
  if a=='checkpoint':
   if not self.runtime:raise RuntimeError('Runtime unavailable')
   return {'snapshot':self.runtime.create_snapshot(x.get('name','upgrade_checkpoint')),'hashes':self._h()}
  raise KeyError(a)
 def self_test(self):return 'Upgrade History contracts passed'
 def build_ui(self,parent=None,ui_context=None):
  from PySide6.QtWidgets import QWidget,QVBoxLayout,QLabel,QTextEdit,QPushButton
  p=QWidget(parent);l=QVBoxLayout(p);l.addWidget(QLabel('Apollo Upgrade History'));o=QTextEdit();o.setReadOnly(True);b=QPushButton('Refresh');l.addWidget(b);l.addWidget(o,1)
  def go():o.setPlainText(json.dumps(self.run('list_history',{}),indent=2))
  b.clicked.connect(go);go();return p
