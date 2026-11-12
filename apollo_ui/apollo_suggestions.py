"""Durable proposal inbox. Suggestions are data, never executable instructions."""
from datetime import datetime,timezone
import hashlib
import json
from pathlib import Path
import sqlite3
import threading
import time

def now(): return datetime.now(timezone.utc).isoformat(timespec='seconds')
def bounded(value,maximum,minimum=1):
    value=str(value or '').strip()
    if not minimum<=len(value)<=maximum: raise ValueError('Suggestion text is empty or too long.')
    return value

class SuggestionStore:
    def __init__(self,root,*,memory=False):
        self.lock=threading.RLock(); folder=Path(root)/'storage'/'databases'
        if not memory: folder.mkdir(parents=True,exist_ok=True)
        self.db=sqlite3.connect(':memory:' if memory else str(folder/'apollo_suggestions.db'),timeout=15,check_same_thread=False); self.db.row_factory=sqlite3.Row
        self.db.executescript('''CREATE TABLE IF NOT EXISTS suggestions(
            id INTEGER PRIMARY KEY,kind TEXT NOT NULL,title TEXT NOT NULL,prompt TEXT NOT NULL,reason TEXT NOT NULL,
            evidence_json TEXT NOT NULL,status TEXT NOT NULL DEFAULT 'open',mission_id INTEGER,
            fingerprint TEXT NOT NULL UNIQUE,created_at TEXT NOT NULL,updated_at TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS guidance(id INTEGER PRIMARY KEY,suggestion_id INTEGER NOT NULL,answer TEXT NOT NULL,created_at TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS reflection_state(key TEXT PRIMARY KEY,value TEXT NOT NULL);''')
    def close(self):
        with self.lock: self.db.close()
    def add(self,kind,title,prompt,reason,evidence=()):
        if kind not in ('question','proposal'): raise ValueError('Unknown suggestion kind.')
        title=bounded(title,180); prompt=bounded(prompt,1000); reason=bounded(reason,1200)
        digest=hashlib.sha256((kind+'\n'+title.casefold()).encode()).hexdigest()
        with self.lock,self.db:
            prior=self.db.execute('SELECT id FROM suggestions WHERE fingerprint=?',(digest,)).fetchone()
            if prior: return self.get(prior[0])
            if self.db.execute("SELECT count(*) FROM suggestions WHERE status='open'").fetchone()[0]>=50: raise ValueError('Review the existing suggestion inbox first.')
            cursor=self.db.execute('INSERT INTO suggestions(kind,title,prompt,reason,evidence_json,fingerprint,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?)',
                (kind,title,prompt,reason,json.dumps(list(evidence)),digest,now(),now()))
            return self.get(cursor.lastrowid)
    def get(self,ident):
        with self.lock:
            row=self.db.execute('SELECT * FROM suggestions WHERE id=?',(int(ident),)).fetchone()
            if row is None: raise KeyError('Suggestion not found.')
            item=dict(row); item['evidence']=json.loads(item.pop('evidence_json'))
            item['answers']=[dict(r) for r in self.db.execute('SELECT answer,created_at FROM guidance WHERE suggestion_id=? ORDER BY id',(ident,))]
            return item
    def list(self):
        with self.lock: return [self.get(r[0]) for r in self.db.execute('SELECT id FROM suggestions ORDER BY id DESC LIMIT 200')]
    def review(self,ident,status):
        if status not in ('accepted','dismissed'): raise ValueError('Unknown review state.')
        with self.lock,self.db:
            self.get(ident); self.db.execute('UPDATE suggestions SET status=?,updated_at=? WHERE id=?',(status,now(),ident))
        return self.get(ident)
    def answer(self,ident,answer):
        answer=bounded(answer,4000)
        with self.lock,self.db:
            item=self.get(ident)
            if item['kind']!='question': raise ValueError('Select a question to answer.')
            self.db.execute('INSERT INTO guidance(suggestion_id,answer,created_at) VALUES(?,?,?)',(ident,answer,now()))
            self.db.execute("UPDATE suggestions SET status='answered',updated_at=? WHERE id=?",(now(),ident))
        return self.get(ident)
    def state(self,key,default=''):
        with self.lock:
            row=self.db.execute('SELECT value FROM reflection_state WHERE key=?',(key,)).fetchone()
            return row[0] if row else default
    def set_state(self,key,value):
        with self.lock,self.db: self.db.execute('INSERT INTO reflection_state VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value',(key,str(value)))
    def reserve(self):
        """Cross-process daily budget and lease; disabled remains durable."""
        with self.lock,self.db:
            self.db.execute('BEGIN IMMEDIATE')
            if self.state('enabled','1')!='1' or float(self.state('next_due','0'))>time.time(): return False
            day=now()[:10]; used=int(self.state('calls:'+day,'0'))
            if used>=4: return False
            self.db.execute('INSERT INTO reflection_state VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value',('calls:'+day,str(used+1)))
            self.db.execute("INSERT INTO reflection_state VALUES('next_due',?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",(str(time.time()+3600),))
            return True
    def guidance_context(self):
        with self.lock: return [dict(r) for r in self.db.execute('SELECT s.title,g.answer FROM guidance g JOIN suggestions s ON s.id=g.suggestion_id ORDER BY g.id DESC LIMIT 8')]


def validate_proposals(response,allowed_ids):
    if isinstance(response,str):
        from apollo_practice import decode_object
        response=decode_object(response)
    if not isinstance(response,dict) or not isinstance(response.get('suggestions'),list): raise ValueError('Reflection must return a suggestions array.')
    proposals=[]
    for item in response['suggestions'][:3]:
        if not isinstance(item,dict): continue
        ids=item.get('mission_ids',[])
        if not isinstance(ids,list) or any(type(i) is not int or i not in allowed_ids for i in ids): continue
        kind=item.get('kind')
        if kind not in ('question','proposal'): continue
        proposals.append({'kind':kind,'title':bounded(item.get('title'),180),'prompt':bounded(item.get('prompt'),1000),
                          'reason':bounded(item.get('reason'),1200),'evidence':ids})
    return proposals
