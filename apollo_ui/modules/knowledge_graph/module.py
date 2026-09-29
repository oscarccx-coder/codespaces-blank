import sqlite3,threading,json
from datetime import datetime
from pathlib import Path
class Module:
 def __init__(self,context=None):
  self.base=Path((context or {}).get('base_dir','.')).resolve();self.db=self.base/'storage'/'databases'/'knowledge_graph.db';self.db.parent.mkdir(parents=True,exist_ok=True);self.lock=threading.RLock();self.conn=sqlite3.connect(self.db,check_same_thread=False);self.conn.row_factory=sqlite3.Row;self.conn.execute("CREATE TABLE IF NOT EXISTS edges(id INTEGER PRIMARY KEY AUTOINCREMENT,subject TEXT NOT NULL,relation TEXT NOT NULL,object TEXT NOT NULL,source TEXT NOT NULL DEFAULT '',confidence REAL NOT NULL DEFAULT 1.0,created_at TEXT NOT NULL,UNIQUE(subject,relation,object,source))");self.conn.commit()
 def tools(self):return [
  {'name':'add_relation','description':'Add/update a source-linked relation in Apollo Knowledge Graph.','parameters':{'type':'object','properties':{'subject':{'type':'string'},'relation':{'type':'string'},'object':{'type':'string'},'source':{'type':'string'},'confidence':{'type':'number'}},'required':['subject','relation','object']}},
  {'name':'neighbors','description':'Return graph edges touching a concept.','parameters':{'type':'object','properties':{'concept':{'type':'string'},'limit':{'type':'integer'}},'required':['concept']}},
  {'name':'search_graph','description':'Search graph subjects, relations and objects.','parameters':{'type':'object','properties':{'query':{'type':'string'},'limit':{'type':'integer'}},'required':['query']}},
  {'name':'graph_stats','description':'Return graph size.','parameters':{'type':'object','properties':{}}},]
 def run(self,a,x):
  x=x or {}
  with self.lock:
   if a=='add_relation':
    s=str(x['subject']).strip();r=str(x['relation']).strip();o=str(x['object']).strip();src=str(x.get('source','')).strip();c=max(0,min(float(x.get('confidence',1)),1));t=datetime.now().isoformat(timespec='seconds');self.conn.execute('INSERT INTO edges(subject,relation,object,source,confidence,created_at) VALUES(?,?,?,?,?,?) ON CONFLICT(subject,relation,object,source) DO UPDATE SET confidence=excluded.confidence,created_at=excluded.created_at',(s,r,o,src,c,t));self.conn.commit();return {'stored':True,'subject':s,'relation':r,'object':o}
   if a=='neighbors':
    q=str(x['concept']);lim=max(1,min(int(x.get('limit',50)),200));rows=self.conn.execute('SELECT * FROM edges WHERE lower(subject)=lower(?) OR lower(object)=lower(?) ORDER BY confidence DESC,id DESC LIMIT ?',(q,q,lim)).fetchall();return {'concept':q,'edges':[dict(z) for z in rows]}
   if a=='search_graph':
    q='%'+str(x['query']).lower()+'%';lim=max(1,min(int(x.get('limit',50)),200));rows=self.conn.execute('SELECT * FROM edges WHERE lower(subject) LIKE ? OR lower(relation) LIKE ? OR lower(object) LIKE ? ORDER BY confidence DESC,id DESC LIMIT ?',(q,q,q,lim)).fetchall();return {'edges':[dict(z) for z in rows]}
   if a=='graph_stats':
    e=self.conn.execute('SELECT count(*) n FROM edges').fetchone()['n'];n=self.conn.execute('SELECT count(*) n FROM (SELECT subject x FROM edges UNION SELECT object x FROM edges)').fetchone()['n'];return {'edges':e,'nodes':n}
  raise KeyError(a)
 def self_test(self):return 'Knowledge Graph schema/contracts passed'
 def build_ui(self,parent=None,ui_context=None):
  from PySide6.QtWidgets import QWidget,QVBoxLayout,QLabel,QLineEdit,QPushButton,QTextEdit
  p=QWidget(parent);l=QVBoxLayout(p);l.addWidget(QLabel('Knowledge Graph'));q=QLineEdit();q.setPlaceholderText('Concept or relation');b=QPushButton('Search');o=QTextEdit();o.setReadOnly(True);l.addWidget(q);l.addWidget(b);l.addWidget(o,1)
  def go():o.setPlainText(json.dumps(self.run('search_graph',{'query':q.text()}),indent=2))
  b.clicked.connect(go);return p
 def close(self):
  try:self.conn.commit();self.conn.close()
  except:pass
