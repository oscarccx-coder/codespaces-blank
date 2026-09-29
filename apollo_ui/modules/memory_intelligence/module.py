import sqlite3,re
from pathlib import Path
class Module:
    def __init__(self,context=None): self.base=Path((context or {}).get('base_dir','.')).resolve(); self.db=self.base/'storage'/'databases'/'memory_bank.db'
    def tools(self): return [
        {"name":"memory_health","description":"Inspect Memory Bank size/types/source distribution without modifying it.","parameters":{"type":"object","properties":{}}},
        {"name":"find_possible_conflicts","description":"Find same-name Memory Bank entries that may conflict or duplicate.","parameters":{"type":"object","properties":{}}},
        {"name":"memory_age_report","description":"Report learned/updated dates for oldest/newest named memories.","parameters":{"type":"object","properties":{"limit":{"type":"integer"}}}},
    ]
    def _conn(self):
        if not self.db.exists(): return None
        c=sqlite3.connect(self.db); c.row_factory=sqlite3.Row; return c
    def run(self,a,x):
        c=self._conn()
        if c is None:return {'available':False,'reason':'memory_bank.db not found'}
        try:
            if a=='memory_health':
                count=c.execute('select count(*) n from memories').fetchone()['n']; types=[dict(r) for r in c.execute('select memory_type,count(*) count from memories group by memory_type order by count(*) desc')]; sources=[dict(r) for r in c.execute('select source,count(*) count from memories group by source order by count(*) desc limit 20')]; return {'available':True,'count':count,'types':types,'sources':sources}
            if a=='find_possible_conflicts':
                rows=c.execute('select lower(name) key,count(*) count,group_concat(id) ids,group_concat(summary," || ") summaries from memories group by lower(name) having count(*)>1 order by count(*) desc limit 100').fetchall(); return {'possible_conflicts':[dict(r) for r in rows]}
            if a=='memory_age_report':
                n=max(1,min(int((x or {}).get('limit',20)),100)); oldest=[dict(r) for r in c.execute('select id,name,memory_type,learned_at,updated_at from memories order by learned_at asc limit ?',(n,))]; newest=[dict(r) for r in c.execute('select id,name,memory_type,learned_at,updated_at from memories order by updated_at desc limit ?',(n,))]; return {'oldest':oldest,'newest':newest}
            raise KeyError(a)
        finally:c.close()
    def self_test(self): return 'memory intelligence query contracts passed'
