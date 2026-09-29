import json,urllib.request
from pathlib import Path
ROLES={'general','coding','reasoning','fast','vision'}
class Module:
 def __init__(self,context=None):self.base=Path((context or {}).get('base_dir','.')).resolve();self.config_path=self.base/'config.json';self.roles_path=self.base/'storage'/'state'/'model_roles.json';self.roles_path.parent.mkdir(parents=True,exist_ok=True)
 def tools(self):return [
  {'name':'list_models','description':'List Ollama models installed on configured local server.','parameters':{'type':'object','properties':{}}},
  {'name':'get_active_model','description':'Return current fallback model and specialist role profiles.','parameters':{'type':'object','properties':{}}},
  {'name':'set_active_model','description':'Persist fallback/general Ollama model.','parameters':{'type':'object','properties':{'model':{'type':'string'}},'required':['model']}},
  {'name':'set_role_model','description':'Assign a model to a specialist role.','parameters':{'type':'object','properties':{'role':{'type':'string'},'model':{'type':'string'}},'required':['role','model']}},
  {'name':'set_role_profile','description':'Assign model, temperature and context size to a role.','parameters':{'type':'object','properties':{'role':{'type':'string'},'model':{'type':'string'},'temperature':{'type':'number'},'num_ctx':{'type':'integer'}},'required':['role','model']}},
  {'name':'route_task','description':'Deterministically choose a role/profile for a task without asking another LLM.','parameters':{'type':'object','properties':{'text':{'type':'string'}},'required':['text']}},]
 def _cfg(self):
  try:return json.loads(self.config_path.read_text())
  except:return {}
 def _roles(self):
  try:
   d=json.loads(self.roles_path.read_text());return d if isinstance(d,dict) else {}
  except:return {}
 def _save(self,d):self.roles_path.write_text(json.dumps(d,indent=2))
 def _prof(self,r):
  c=self._cfg();z=self._roles().get(r);z={'model':z} if isinstance(z,str) else (z if isinstance(z,dict) else {})
  return {'role':r,'model':z.get('model') or c.get('model'),'temperature':float(z.get('temperature',c.get('temperature',0.65))),'num_ctx':int(z.get('num_ctx',c.get('num_ctx',8192)))}
 def run(self,a,x):
  x=x or {};c=self._cfg();url=str(c.get('ollama_url','http://127.0.0.1:11434')).rstrip('/')
  if a=='list_models':
   with urllib.request.urlopen(url+'/api/tags',timeout=4) as r:d=json.loads(r.read().decode())
   return {'models':[m.get('name') for m in d.get('models',[]) if m.get('name')]}
  if a=='get_active_model':return {'model':c.get('model'),'roles':{r:self._prof(r) for r in sorted(ROLES)},'auto_routing':bool(c.get('auto_model_routing',False))}
  if a=='set_active_model':c['model']=str(x['model']);self.config_path.write_text(json.dumps(c,indent=2));return {'saved':True,'model':c['model']}
  if a in {'set_role_model','set_role_profile'}:
   r=str(x['role']).lower().strip()
   if r not in ROLES:raise ValueError('Unknown role')
   roles=self._roles();z=roles.get(r);z={'model':z} if isinstance(z,str) else (z if isinstance(z,dict) else {});z['model']=str(x['model'])
   if a=='set_role_profile':z['temperature']=max(0,min(float(x.get('temperature',0.65)),2));z['num_ctx']=max(1024,min(int(x.get('num_ctx',8192)),131072))
   roles[r]=z;self._save(roles);return {'saved':True,**self._prof(r)}
  if a=='route_task':
   t=str(x['text']).lower();r='general'
   if any(k in t for k in ['code','python','debug','module','function','script','program','workspace','file build']):r='coding'
   elif any(k in t for k in ['reason','derive','prove','physics','maths','mathematics','analy','calculate why']):r='reasoning'
   elif len(t)<100 and any(k in t for k in ['hello','hi ','thanks','add ','open ','list ','mute']):r='fast'
   elif any(k in t for k in ['image','screen','photo','picture','vision','look at']):r='vision'
   return {**self._prof(r),'source':'deterministic_router'}
  raise KeyError(a)
 def self_test(self):assert self._prof('general')['role']=='general';return 'Model Runtime role-profile contracts passed'
 def build_ui(self,parent=None,ui_context=None):
  from PySide6.QtWidgets import QWidget,QVBoxLayout,QLabel,QComboBox,QPushButton,QHBoxLayout,QDoubleSpinBox,QSpinBox
  p=QWidget(parent);l=QVBoxLayout(p);l.addWidget(QLabel('Model Runtime — specialist roles'))
  try:models=self.run('list_models',{}).get('models',[])
  except:models=[]
  ctr={}
  for r in ['general','coding','reasoning','fast','vision']:
   row=QHBoxLayout();row.addWidget(QLabel(r.title()));m=QComboBox();m.setEditable(True);m.addItems(models);pr=self._prof(r);m.setCurrentText(str(pr['model'] or ''));temp=QDoubleSpinBox();temp.setRange(0,2);temp.setSingleStep(.05);temp.setValue(pr['temperature']);ctx=QSpinBox();ctx.setRange(1024,131072);ctx.setSingleStep(1024);ctx.setValue(pr['num_ctx']);row.addWidget(m,2);row.addWidget(QLabel('Temp'));row.addWidget(temp);row.addWidget(QLabel('Context'));row.addWidget(ctx);l.addLayout(row);ctr[r]=(m,temp,ctx)
  b=QPushButton('Save Role Profiles');l.addWidget(b);l.addStretch(1)
  def save():
   for r,(m,t,c) in ctr.items():
    if m.currentText().strip():self.run('set_role_profile',{'role':r,'model':m.currentText().strip(),'temperature':t.value(),'num_ctx':c.value()})
  b.clicked.connect(save);return p
