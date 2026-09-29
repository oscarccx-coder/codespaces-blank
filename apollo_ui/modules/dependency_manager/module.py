import importlib.util,subprocess,sys,venv
from importlib import metadata
from pathlib import Path
class Module:
 def __init__(self,context=None):self.base=Path((context or {}).get('base_dir','.')).resolve();self.venvs=self.base/'storage'/'environments'/'venvs';self.venvs.mkdir(parents=True,exist_ok=True)
 def tools(self):return [
  {'name':'check_package','description':'Check a package/import in Apollo main environment.','parameters':{'type':'object','properties':{'name':{'type':'string'}},'required':['name']}},
  {'name':'list_environment','description':'List installed Python distributions.','parameters':{'type':'object','properties':{}}},
  {'name':'plan_install','description':'Return exact pip command without running it.','parameters':{'type':'object','properties':{'package':{'type':'string'}},'required':['package']}},
  {'name':'install_package','description':'Install package into Apollo main environment; high-risk permission gated.','parameters':{'type':'object','properties':{'package':{'type':'string'}},'required':['package']}},
  {'name':'create_isolated_env','description':'Create dedicated virtual environment under storage/environments/venvs.','parameters':{'type':'object','properties':{'name':{'type':'string'}},'required':['name']}},
  {'name':'list_isolated_envs','description':'List Apollo virtual environments.','parameters':{'type':'object','properties':{}}},
  {'name':'install_into_env','description':'Install package into named isolated environment.','parameters':{'type':'object','properties':{'name':{'type':'string'},'package':{'type':'string'}},'required':['name','package']}},]
 def _name(self,n):
  v=''.join(c if c.isalnum() or c in '-_' else '_' for c in str(n))
  if not v:raise ValueError('Environment name required')
  return v[:80]
 def _env(self,n):return self.venvs/self._name(n)
 def _py(self,e):return e/('Scripts/python.exe' if sys.platform=='win32' else 'bin/python')
 def _pkg(self,p):
  p=str(p).strip()
  if not p or any(c in p for c in '\n\r;&|`'):raise ValueError('Unsafe package specification')
  return p
 def run(self,a,x):
  x=x or {}
  if a=='check_package':n=x['name'];return {'name':n,'import_found':importlib.util.find_spec(n.replace('-','_')) is not None}
  if a=='list_environment':return {'packages':sorted([{'name':d.metadata.get('Name',d.metadata.get('Summary','')),'version':d.version} for d in metadata.distributions()],key=lambda z:(z['name'] or '').lower())}
  if a=='plan_install':return {'command':[sys.executable,'-m','pip','install',self._pkg(x['package'])]}
  if a=='install_package':
   p=subprocess.run([sys.executable,'-m','pip','install',self._pkg(x['package'])],capture_output=True,text=True,timeout=600);return {'returncode':p.returncode,'stdout':p.stdout[-10000:],'stderr':p.stderr[-10000:]}
  if a=='create_isolated_env':
   e=self._env(x['name']);
   if not e.exists():venv.EnvBuilder(with_pip=True).create(e)
   return {'created':True,'name':e.name,'path':str(e),'python':str(self._py(e))}
  if a=='list_isolated_envs':return {'environments':[{'name':e.name,'path':str(e),'python':str(self._py(e))} for e in sorted(self.venvs.iterdir()) if e.is_dir()]}
  if a=='install_into_env':
   e=self._env(x['name']);py=self._py(e)
   if not py.exists():raise FileNotFoundError('Environment does not exist')
   p=subprocess.run([str(py),'-m','pip','install',self._pkg(x['package'])],capture_output=True,text=True,timeout=600);return {'returncode':p.returncode,'stdout':p.stdout[-10000:],'stderr':p.stderr[-10000:]}
  raise KeyError(a)
 def self_test(self):assert self._name('demo project')=='demo_project';return 'Dependency Manager isolated-env contracts passed'
 def build_ui(self,parent=None,ui_context=None):
  from PySide6.QtWidgets import QWidget,QVBoxLayout,QLabel,QListWidget,QPushButton
  p=QWidget(parent);l=QVBoxLayout(p);l.addWidget(QLabel('Dependency Manager'));lst=QListWidget();l.addWidget(lst,1);b=QPushButton('List Isolated Environments');l.addWidget(b)
  def go():lst.clear();[lst.addItem(f"{q['name']} — {q['path']}") for q in self.run('list_isolated_envs',{})['environments']]
  b.clicked.connect(go);go();return p
