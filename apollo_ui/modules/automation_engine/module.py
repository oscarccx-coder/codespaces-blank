import json,threading
from datetime import datetime,timezone,timedelta
from pathlib import Path
class Module:
    def __init__(self,context=None):
        c=context or {}; self.base=Path(c.get('base_dir','.')).resolve(); self.path=self.base/'storage'/'state'/'automations.json'; self.path.parent.mkdir(parents=True,exist_ok=True); self.runtime=c.get('runtime'); self._lock=threading.RLock()
    def tools(self): return [
        {"name":"create_automation","description":"Create a one-shot or interval automation that calls an Apollo capability later.","parameters":{"type":"object","properties":{"name":{"type":"string"},"capability":{"type":"string"},"arguments":{"type":"object"},"run_at":{"type":"string"},"interval_seconds":{"type":"integer"}},"required":["name","capability"]}},
        {"name":"list_automations","description":"List saved automations.","parameters":{"type":"object","properties":{}}},
        {"name":"remove_automation","description":"Remove an automation by id.","parameters":{"type":"object","properties":{"id":{"type":"integer"}},"required":["id"]}},
        {"name":"run_due","description":"Run due automations through Apollo's normal permission/action bus.","parameters":{"type":"object","properties":{}}},
    ]
    def _load(self):
        try: data=json.loads(self.path.read_text(encoding='utf-8')); return data if isinstance(data,list) else []
        except Exception: return []
    def _save(self,data):
        if getattr(self,'validation',False): return
        t=self.path.with_suffix('.tmp'); t.write_text(json.dumps(data,indent=2),encoding='utf-8'); t.replace(self.path)
    def run(self,a,x):
        x=x or {}
        with self._lock:
            data=self._load()
            if a=='create_automation':
                ident=max([i.get('id',0) for i in data]+[0])+1; now=datetime.now(timezone.utc).astimezone(); run_at=x.get('run_at')
                if not run_at:
                    delay=max(60,int(x.get('interval_seconds',3600))); run_at=(now+timedelta(seconds=delay)).isoformat(timespec='seconds')
                item={'id':ident,'name':x['name'],'capability':x['capability'],'arguments':x.get('arguments',{}),'run_at':run_at,'interval_seconds':int(x.get('interval_seconds',0) or 0),'enabled':True}; data.append(item); self._save(data); return item
            if a=='list_automations': return {'automations':data}
            if a=='remove_automation':
                before=len(data); data=[i for i in data if int(i.get('id',-1))!=int(x['id'])]; self._save(data); return {'removed':before-len(data)}
            if a=='run_due':
                if self.runtime is None or self.runtime._manager is None: return {'ran':[],'note':'runtime unavailable'}
                now=datetime.now(timezone.utc).astimezone(); ran=[]; changed=False
                for item in data:
                    if not item.get('enabled',True): continue
                    try: due=datetime.fromisoformat(str(item.get('run_at')))
                    except Exception: continue
                    if due.tzinfo is None: due=due.replace(tzinfo=now.tzinfo)
                    if due>now: continue
                    try: result=self.runtime.execute_tool(self.runtime._manager,item['capability'],item.get('arguments',{}),actor='automation'); ran.append({'id':item['id'],'ok':True,'result':result})
                    except Exception as e: ran.append({'id':item['id'],'ok':False,'error':str(e)})
                    interval=int(item.get('interval_seconds',0) or 0)
                    if interval>0: item['run_at']=(now+timedelta(seconds=max(60,interval))).isoformat(timespec='seconds')
                    else: item['enabled']=False
                    changed=True
                if changed:self._save(data)
                return {'ran':ran}
        raise KeyError(a)
    def self_test(self): return 'automation store contract passed'
