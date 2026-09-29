import hashlib,re
from pathlib import Path
STOP={'the','a','an','and','or','of','to','in','on','for','with','from','this','that','is','are','be','as','it','we','you','i','about','learn','study','research','pile'}
class Module:
 def __init__(self,context=None):self.base=Path((context or {}).get('base_dir','.')).resolve()
 def tools(self):return [
  {'name':'normalize_topic','description':'Remove command-wrapper junk and create a canonical display topic/fingerprint.','parameters':{'type':'object','properties':{'topic':{'type':'string'}},'required':['topic']}},
  {'name':'distill_pile_result','description':'Turn accepted Pile passages into compact memory key points plus provenance.','parameters':{'type':'object','properties':{'query':{'type':'string'},'passages':{'type':'array'}},'required':['query','passages']}},
 ]
 @staticmethod
 def _strip(v):
  v=' '.join(str(v or '').split()).strip(); pats=[r'(?i)^\s*(?:says?\s+this|sent\s+this|request|coding\s+workspace\s+request)\s*[:,-]?\s*',r'(?i)^\s*(?:please\s+)?(?:learn|study|research|remember|absorb)\s+(?:about\s+)?(?:from\s+)?(?:the\s+)?pile(?:\s+(?:about|on|for))?\s*[:,-]?\s*',r'(?i)^\s*(?:please\s+)?(?:search|query|access|use|look\s+in|look\s+through)\s+(?:the\s+)?pile(?:\s+(?:about|on|for))?\s*[:,-]?\s*']
  changed=True
  while changed:
   changed=False
   for p in pats:
    n=re.sub(p,'',v,count=1).strip(' :,-')
    if n!=v:v=n;changed=True
  return v or 'Learned Knowledge'
 @staticmethod
 def _display(v):
  v=v.title(); repl={'Ai':'AI','Api':'API','Apis':'APIs','Llm':'LLM','Llms':'LLMs','Gpu':'GPU','Cpu':'CPU','Json':'JSON','Html':'HTML','Css':'CSS','Sql':'SQL','Usb':'USB','Obd':'OBD'}
  for a,b in repl.items():v=re.sub(r'\b'+re.escape(a)+r'\b',b,v)
  return v[:120]
 @classmethod
 def normalize(cls,v):
  raw=cls._strip(v); words=re.findall(r'[a-zA-Z0-9+#.-]+',raw.lower()); sig=sorted({x for x in words if x not in STOP and len(x)>1}); fp=hashlib.sha256('|'.join(sig).encode()).hexdigest()[:16]
  return {'topic':raw,'display_name':cls._display(raw),'fingerprint':fp,'keywords':sig[:32]}
 @staticmethod
 def _sentences(text):
  text=re.sub(r'https?://\S+','',str(text or '')); lines=[]
  for raw in text.splitlines():
   line=' '.join(raw.split()).strip(); lo=line.lower()
   if not line or lo.startswith(('from ','import ','#','//','copyright','license')):continue
   if line.count('=')>=3 or line.count('(')+line.count(')')>=10 or len(line)<35:continue
   lines.append(line)
  return [s.strip() for s in re.split(r'(?<=[.!?])\s+',' '.join(lines)) if 35<=len(s.strip())<=360]
 def run(self,a,x):
  x=x or {}
  if a=='normalize_topic':return self.normalize(x['topic'])
  if a=='distill_pile_result':
   n=self.normalize(x['query']); qt=set(n['keywords']); cand=[]; prov=[]
   for item in (x.get('passages') or [])[:12]:
    if not isinstance(item,dict):continue
    rel=float(item.get('relevance',0) or 0); prov.append({'subset':str(item.get('subset','The Pile')),'source_ref':str(item.get('source_ref','')),'relevance':rel})
    for s in self._sentences(item.get('text','')):
     words=set(re.findall(r'[a-zA-Z0-9+#.-]+',s.lower())); overlap=len(qt&words); tech=sum(1 for t in ('model','training','loss','optimizer','inference','network','python','keras','tensorflow','pytorch','batch','weights','gradient','attention','transformer','evaluation') if t in words); cand.append((overlap*2+tech+rel,s))
   cand.sort(key=lambda z:z[0],reverse=True); points=[]; seen=set()
   for _,s in cand:
    k=re.sub(r'\W+',' ',s.lower()).strip()
    if k in seen:continue
    seen.add(k); points.append(s)
    if len(points)>=6:break
   summary=points[0][:500] if points else f"Source-backed material learned about {n['display_name']}."; content=('Key knowledge:\n'+'\n'.join('- '+q for q in points)) if points else summary
   if prov:content+='\n\nProvenance:\n'+'\n'.join(f"- {q['subset']} • relevance {q['relevance']:.4f} • {q['source_ref']}" for q in prov[:8])
   return {**n,'summary':summary,'content':content[:12000],'provenance':prov[:12],'point_count':len(points)}
  raise KeyError(a)
 def self_test(self):
  n=self.normalize('says this learn from pile advanced ai coding in python'); assert n['display_name']=='Advanced AI Coding In Python'; return 'Memory distillation passed'
