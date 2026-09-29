import os,subprocess,sys
from pathlib import Path
class Module:
 def __init__(self,context=None):self.base=Path((context or {}).get('base_dir','.')).resolve()
 def tools(self):return [
  {'name':'get_clipboard','description':'Read current OS text clipboard.','parameters':{'type':'object','properties':{}}},
  {'name':'set_clipboard','description':'Set OS text clipboard.','parameters':{'type':'object','properties':{'text':{'type':'string'}},'required':['text']}},
  {'name':'open_with_default','description':'Open an Apollo-managed path with the operating-system default application.','parameters':{'type':'object','properties':{'path':{'type':'string'}},'required':['path']}},
  {'name':'file_association','description':'Inspect the Windows file association for an extension such as .py or .txt.','parameters':{'type':'object','properties':{'extension':{'type':'string'}},'required':['extension']}},]
 def _path(self,v):
  p=(self.base/str(v or '')).resolve() if not Path(str(v or '')).is_absolute() else Path(str(v)).resolve()
  if p!=self.base and self.base not in p.parents:raise PermissionError('Desktop Services only opens paths inside Apollo')
  return p
 def run(self,a,x):
  x=x or {}
  if a=='get_clipboard':
   if os.name=='nt':
    p=subprocess.run(['powershell.exe','-NoProfile','-NonInteractive','-Command','Get-Clipboard -Raw'],capture_output=True,text=True,timeout=10);return {'text':p.stdout,'returncode':p.returncode}
   cmd=['pbpaste'] if sys.platform=='darwin' else ['sh','-lc','command -v xclip >/dev/null && xclip -selection clipboard -o || true'];p=subprocess.run(cmd,capture_output=True,text=True,timeout=10);return {'text':p.stdout,'returncode':p.returncode}
  if a=='set_clipboard':
   text=str(x.get('text',''))
   if os.name=='nt':
    env=dict(os.environ);env['APOLLO_CLIPBOARD']=text;p=subprocess.run(['powershell.exe','-NoProfile','-NonInteractive','-Command','Set-Clipboard -Value $env:APOLLO_CLIPBOARD'],capture_output=True,text=True,timeout=10,env=env);return {'saved':p.returncode==0,'returncode':p.returncode}
   raise RuntimeError('Clipboard write currently targets Windows Apollo builds')
  if a=='open_with_default':
   p=self._path(x['path'])
   if not p.exists():raise FileNotFoundError(str(p))
   if os.name=='nt':os.startfile(str(p))
   else:subprocess.Popen(['open' if sys.platform=='darwin' else 'xdg-open',str(p)])
   return {'opened':True,'path':str(p)}
  if a=='file_association':
   ext=str(x['extension']).strip()
   if not ext.startswith('.'):ext='.'+ext
   if os.name!='nt':return {'extension':ext,'association':None,'note':'assoc is Windows-specific'}
   p=subprocess.run(['cmd.exe','/c','assoc',ext],capture_output=True,text=True,timeout=10);return {'extension':ext,'association':p.stdout.strip(),'returncode':p.returncode}
  raise KeyError(a)
 def self_test(self):assert self._path('workspace').name=='workspace';return 'Desktop Services path guard/contracts passed'
 def build_ui(self,parent=None,ui_context=None):
  from PySide6.QtWidgets import QWidget,QVBoxLayout,QLabel,QTextEdit,QPushButton
  p=QWidget(parent);l=QVBoxLayout(p);l.addWidget(QLabel('Desktop Services'));o=QTextEdit();b=QPushButton('Read Clipboard');l.addWidget(b);l.addWidget(o,1)
  def go():
   try:o.setPlainText(self.run('get_clipboard',{}).get('text',''))
   except Exception as e:o.setPlainText(str(e))
  b.clicked.connect(go);return p
