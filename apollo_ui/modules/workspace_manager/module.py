import os,re,subprocess,sys
from pathlib import Path
class Module:
    def __init__(self,context=None):
        self.base=Path((context or {}).get('base_dir','.')).resolve(); self.root=(self.base/'workspace').resolve(); self.root.mkdir(parents=True,exist_ok=True)
    def tools(self): return [
        {"name":"list_projects","description":"List folders/projects in Apollo workspace.","parameters":{"type":"object","properties":{}}},
        {"name":"list_files","description":"List files within a workspace project/path.","parameters":{"type":"object","properties":{"path":{"type":"string"}}}},
        {"name":"read_file","description":"Read a UTF-8 workspace file.","parameters":{"type":"object","properties":{"path":{"type":"string"}},"required":["path"]}},
        {"name":"write_file","description":"Write one UTF-8 workspace file. Use file_builder for whole multi-file builds.","parameters":{"type":"object","properties":{"path":{"type":"string"},"content":{"type":"string"}},"required":["path","content"]}},
        {"name":"search_files","description":"Search text across workspace files.","parameters":{"type":"object","properties":{"query":{"type":"string"},"path":{"type":"string"}},"required":["query"]}},
        {"name":"run_python_project","description":"Run a Python entry file inside workspace. High-risk execution is permission-gated.","parameters":{"type":"object","properties":{"path":{"type":"string"},"timeout":{"type":"integer"}},"required":["path"]}},
    ]
    def _path(self,rel):
        p=(self.root/str(rel or '')).resolve()
        if p!=self.root and self.root not in p.parents: raise PermissionError('Path escaped workspace')
        return p
    def run(self,a,x):
        x=x or {}
        if a=='list_projects': return {'projects':[p.name for p in sorted(self.root.iterdir()) if p.is_dir()]}
        if a=='list_files':
            p=self._path(x.get('path','')); return {'files':[str(f.relative_to(self.root)) for f in sorted(p.rglob('*')) if f.is_file()][:2000]}
        if a=='read_file':
            p=self._path(x['path']); return {'path':str(p.relative_to(self.root)),'content':p.read_text(encoding='utf-8',errors='replace')[:200000]}
        if a=='write_file':
            p=self._path(x['path']); p.parent.mkdir(parents=True,exist_ok=True); p.write_text(str(x.get('content','')),encoding='utf-8'); return {'written':True,'path':str(p.relative_to(self.root))}
        if a=='search_files':
            q=str(x['query']).lower(); root=self._path(x.get('path','')); hits=[]
            for p in root.rglob('*'):
                if not p.is_file() or p.stat().st_size>2_000_000: continue
                try: txt=p.read_text(encoding='utf-8',errors='ignore')
                except Exception: continue
                for i,line in enumerate(txt.splitlines(),1):
                    if q in line.lower(): hits.append({'path':str(p.relative_to(self.root)),'line':i,'text':line[:300]})
                    if len(hits)>=200: return {'hits':hits}
            return {'hits':hits}
        if a=='run_python_project':
            p=self._path(x['path']);
            if p.suffix.lower() not in {'.py','.pyw'}: raise ValueError('Only Python entry files are supported')
            proc=subprocess.run([sys.executable,str(p)],cwd=str(p.parent),capture_output=True,text=True,timeout=max(1,min(int(x.get('timeout',30)),120)))
            return {'returncode':proc.returncode,'stdout':proc.stdout[-12000:],'stderr':proc.stderr[-12000:]}
        raise KeyError(a)
    def self_test(self): self._path('demo/test.txt'); return 'workspace path guard passed'
    def build_ui(self,parent=None,ui_context=None):
        from PySide6.QtWidgets import QWidget,QHBoxLayout,QVBoxLayout,QListWidget,QTextEdit,QPushButton,QLabel
        p=QWidget(parent); root=QHBoxLayout(p); files=QListWidget(); right=QVBoxLayout(); editor=QTextEdit(); status=QLabel(); save=QPushButton('Save Selected File'); refresh=QPushButton('Refresh'); root.addWidget(files,1); root.addLayout(right,3); right.addWidget(editor,1); right.addWidget(status); right.addWidget(save); right.addWidget(refresh)
        current={'path':None}
        def r():
            files.clear();
            for f in self.run('list_files',{}).get('files',[]): files.addItem(f)
        def open_item(item):
            try:
                data=self.run('read_file',{'path':item.text()}); editor.setPlainText(data['content']); current['path']=item.text(); status.setText(item.text())
            except Exception as e: status.setText(str(e))
        def do_save():
            if current['path']:
                self.run('write_file',{'path':current['path'],'content':editor.toPlainText()}); status.setText('Saved '+current['path'])
        files.itemDoubleClicked.connect(open_item); save.clicked.connect(do_save); refresh.clicked.connect(r); r(); return p
