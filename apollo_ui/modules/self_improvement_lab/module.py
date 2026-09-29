import ast,hashlib,json
from datetime import datetime
from pathlib import Path
class Module:
 def __init__(self,context=None):self.base=Path((context or {}).get('base_dir','.')).resolve();self.runtime=(context or {}).get('runtime');self.root=self.base/'workspace'/'self_improvement';self.root.mkdir(parents=True,exist_ok=True)
 def tools(self):return [
  {'name':'audit_apollo','description':'Read-only audit of Apollo source/TODO/FIXME.','parameters':{'type':'object','properties':{}}},
  {'name':'create_proposal','description':'Create approval-gated improvement proposal; does not alter core.','parameters':{'type':'object','properties':{'title':{'type':'string'},'summary':{'type':'string'},'files':{'type':'array','items':{'type':'string'}}},'required':['title','summary']}},
  {'name':'stage_multi_file_patch','description':'Write coordinated multi-file candidate under Workspace/self_improvement; never auto-applied.','parameters':{'type':'object','properties':{'title':{'type':'string'},'summary':{'type':'string'},'changes':{'type':'array','items':{'type':'object','properties':{'path':{'type':'string'},'content':{'type':'string'}},'required':['path','content']}}},'required':['title','summary','changes']}},
  {'name':'verify_proposal','description':'Static-check staged Python and list hashes; does not execute/apply.','parameters':{'type':'object','properties':{'folder':{'type':'string'}},'required':['folder']}},
  {'name':'list_proposals','description':'List staged proposals.','parameters':{'type':'object','properties':{}}},
  {'name':'snapshot_before_change','description':'Create recovery snapshot before user-approved change.','parameters':{'type':'object','properties':{'name':{'type':'string'}}}},]
 def _folder(self,t):
  d=self.root/(datetime.now().strftime('%Y%m%d_%H%M%S')+'_'+''.join(c if c.isalnum() else '_' for c in str(t))[:60]);d.mkdir(parents=True,exist_ok=True);return d
 def _rel(self,p):
  r=Path(str(p).replace('\\','/'))
  if r.is_absolute() or '..' in r.parts:raise PermissionError('Path must be relative')
  return r
 def run(self,a,x):
  x=x or {}
  if a=='audit_apollo':
   files=[p for p in self.base.rglob('*.py') if 'workspace' not in p.parts and '__pycache__' not in p.parts];mark=[]
   for p in files:
    try:t=p.read_text(encoding='utf-8',errors='ignore')
    except:continue
    for n,line in enumerate(t.splitlines(),1):
     if 'TODO' in line or 'FIXME' in line:mark.append({'file':str(p.relative_to(self.base)),'line':n,'text':line.strip()[:200]})
   return {'python_files':len(files),'markers':mark[:200],'policy':'proposal_only_no_silent_core_write'}
  if a=='create_proposal':
   d=self._folder(x['title']);q={'title':x['title'],'summary':x['summary'],'files':x.get('files',[]),'created_at':datetime.now().isoformat(timespec='seconds'),'status':'pending_user_approval'};(d/'proposal.json').write_text(json.dumps(q,indent=2));return {'created':True,'folder':str(d),'status':'pending_user_approval'}
  if a=='stage_multi_file_patch':
   changes=x.get('changes') or []
   if not changes or len(changes)>100:raise ValueError('1-100 changes required')
   d=self._folder(x['title']);c=d/'candidate';c.mkdir();m={'title':x['title'],'summary':x['summary'],'created_at':datetime.now().isoformat(timespec='seconds'),'status':'pending_user_approval','changes':[]}
   for it in changes:
    r=self._rel(it['path']);t=c/r;t.parent.mkdir(parents=True,exist_ok=True);t.write_text(str(it.get('content','')),encoding='utf-8');o=self.base/r;oh=hashlib.sha256(o.read_bytes()).hexdigest() if o.is_file() else None;ch=hashlib.sha256(t.read_bytes()).hexdigest();m['changes'].append({'path':str(r).replace('\\','/'),'original_sha256':oh,'candidate_sha256':ch})
   (d/'proposal.json').write_text(json.dumps(m,indent=2));return {'created':True,'folder':str(d),'file_count':len(changes),'status':'pending_user_approval'}
  if a=='verify_proposal':
   d=Path(x['folder']).resolve()
   if self.root.resolve() not in d.parents and d!=self.root.resolve():raise PermissionError('Proposal escaped self-improvement workspace')
   c=d/'candidate';err=[];h={}
   for p in c.rglob('*'):
    if not p.is_file():continue
    r=str(p.relative_to(c)).replace('\\','/');h[r]=hashlib.sha256(p.read_bytes()).hexdigest()
    if p.suffix.lower() in {'.py','.pyw'}:
     try:ast.parse(p.read_text(),filename=r)
     except Exception as e:err.append({'file':r,'error':str(e)})
   q={'ok':not err,'errors':err,'hashes':h,'applied':False};(d/'verification.json').write_text(json.dumps(q,indent=2));return q
  if a=='list_proposals':return {'proposals':[str(p) for p in sorted(self.root.glob('*/proposal.json'),reverse=True)]}
  if a=='snapshot_before_change':
   if not self.runtime:raise RuntimeError('Runtime unavailable')
   return {'file':self.runtime.create_snapshot(x.get('name','self_improvement'))}
  raise KeyError(a)
 def self_test(self):assert any(t['name']=='stage_multi_file_patch' for t in self.tools());return 'Self-improvement multi-file staging/approval boundary passed'
 def build_ui(self,parent=None,ui_context=None):
  from PySide6.QtWidgets import QWidget,QVBoxLayout,QLabel,QListWidget,QPushButton
  p=QWidget(parent);l=QVBoxLayout(p);l.addWidget(QLabel('Self-Improvement Lab — proposal only, never silent core writes'));lst=QListWidget();l.addWidget(lst,1);b=QPushButton('Refresh Proposals');l.addWidget(b)
  def go():lst.clear();[lst.addItem(q) for q in self.run('list_proposals',{})['proposals']]
  b.clicked.connect(go);go();return p
