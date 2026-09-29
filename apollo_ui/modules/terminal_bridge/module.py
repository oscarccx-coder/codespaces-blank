import subprocess,os
from pathlib import Path
class Module:
    def __init__(self,context=None): self.base=Path((context or {}).get('base_dir','.')).resolve(); self.workspace=(self.base/'workspace').resolve(); self.workspace.mkdir(parents=True,exist_ok=True)
    def tools(self): return [
        {"name":"run_command","description":"Run a shell command inside Apollo workspace. High-risk and blocked by default.","parameters":{"type":"object","properties":{"command":{"type":"string"},"cwd":{"type":"string"},"timeout":{"type":"integer"}},"required":["command"]}},
        {"name":"get_working_directory","description":"Return Apollo terminal workspace root.","parameters":{"type":"object","properties":{}}},
    ]
    def _cwd(self,rel=''):
        p=(self.workspace/str(rel or '')).resolve()
        if p!=self.workspace and self.workspace not in p.parents: raise PermissionError('cwd escaped workspace')
        if not p.exists(): raise FileNotFoundError(p)
        return p
    def run(self,a,x):
        x=x or {}
        if a=='get_working_directory': return {'workspace':str(self.workspace)}
        if a=='run_command':
            cmd=str(x['command']);
            if '\n' in cmd or '\r' in cmd: raise ValueError('Only one command line per call')
            proc=subprocess.run(cmd,cwd=str(self._cwd(x.get('cwd',''))),shell=True,capture_output=True,text=True,timeout=max(1,min(int(x.get('timeout',30)),180)))
            return {'returncode':proc.returncode,'stdout':proc.stdout[-20000:],'stderr':proc.stderr[-20000:]}
        raise KeyError(a)
    def self_test(self): self._cwd(); return 'terminal workspace boundary passed'
