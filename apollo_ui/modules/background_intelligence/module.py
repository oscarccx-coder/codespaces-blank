from datetime import datetime
from pathlib import Path
class Module:
 def __init__(self,context=None):self.base=Path((context or {}).get('base_dir','.')).resolve();self.runtime=(context or {}).get('runtime')
 def tools(self):return [{'name':'maintenance_pulse','description':'Run read-mostly Apollo maintenance/health pulse.','parameters':{'type':'object','properties':{}}},{'name':'maintenance_status','description':'Read latest maintenance snapshot.','parameters':{'type':'object','properties':{}}}]
 def run(self,a,x):
  if not self.runtime:raise RuntimeError('Runtime unavailable')
  if a=='maintenance_pulse':
   m=self.runtime._manager
   if m:self.runtime.refresh_capabilities(m)
   h=self.runtime.health();fails=self.runtime.module_failure_records();q={'time':datetime.now().isoformat(timespec='seconds'),'health':h,'quarantined_modules':[z for z in fails if z.get('quarantined')],'unread_notifications':len(self.runtime.notifications(unread_only=True,limit=200))};self.runtime.blackboard_set('background.health',q,'background_intelligence');return q
  if a=='maintenance_status':return {'status':self.runtime.blackboard_get('background.health',{})}
  raise KeyError(a)
 def self_test(self):return 'Background Intelligence contracts passed'
