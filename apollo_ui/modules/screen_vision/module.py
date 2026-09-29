from datetime import datetime
from pathlib import Path
class Module:
    def __init__(self,context=None): self.base=Path((context or {}).get('base_dir','.')).resolve(); self.folder=self.base/'storage'/'media'/'screenshots'; self.folder.mkdir(parents=True,exist_ok=True)
    def tools(self): return [
        {"name":"screen_info","description":"Report available Qt screens without capturing pixels.","parameters":{"type":"object","properties":{}}},
        {"name":"capture_screen","description":"Capture the primary screen to Apollo storage. Privacy-sensitive and permission-gated.","parameters":{"type":"object","properties":{"filename":{"type":"string"}}}},
    ]
    def run(self,a,x):
        from PySide6.QtGui import QGuiApplication
        app=QGuiApplication.instance();
        if app is None: raise RuntimeError('Qt GUI application is not running')
        if a=='screen_info': return {'screens':[{'name':s.name(),'geometry':[s.geometry().x(),s.geometry().y(),s.geometry().width(),s.geometry().height()]} for s in app.screens()]}
        if a=='capture_screen':
            screen=app.primaryScreen();
            if screen is None: raise RuntimeError('No primary screen')
            name=str((x or {}).get('filename') or ('screen_'+datetime.now().strftime('%Y%m%d_%H%M%S')+'.png'))
            if not name.lower().endswith('.png'):name+='.png'
            name=''.join(c if c.isalnum() or c in '._-' else '_' for c in name); target=(self.folder/name).resolve(); pix=screen.grabWindow(0); ok=pix.save(str(target),'PNG'); return {'saved':bool(ok),'file':str(target)}
        raise KeyError(a)
    def self_test(self): assert self.folder.name=='screenshots'; return 'screen capture path contract passed'
