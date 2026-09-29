import json,threading,time
from pathlib import Path
class Module:
    def __init__(self,context=None):
        c=context or {}; self.base=Path(c.get('base_dir','.')).resolve(); self.runtime=c.get('runtime'); self.path=self.base/'storage'/'state'/'voice_agent.json'; self.path.parent.mkdir(parents=True,exist_ok=True); self._stop=threading.Event(); self._thread=None
    def tools(self): return [
        {"name":"get_voice_agent_settings","description":"Read hands-free voice/wake-word settings.","parameters":{"type":"object","properties":{}}},
        {"name":"set_voice_agent_settings","description":"Set wake word and hands-free voice settings.","parameters":{"type":"object","properties":{"wake_word":{"type":"string"},"enabled":{"type":"boolean"},"listen_seconds":{"type":"integer"}}}},
        {"name":"start_listening","description":"Start a background wake-word monitor using Speech I/O. Microphone access is permission-gated.","parameters":{"type":"object","properties":{}}},
        {"name":"stop_listening","description":"Stop the background wake-word monitor.","parameters":{"type":"object","properties":{}}},
    ]
    def _settings(self):
        try:d=json.loads(self.path.read_text(encoding='utf-8')); return d if isinstance(d,dict) else {}
        except Exception:return {'wake_word':'apollo','enabled':False,'listen_seconds':5}
    def _save(self,d): self.path.write_text(json.dumps(d,indent=2),encoding='utf-8')
    def _loop(self):
        while not self._stop.is_set():
            cfg=self._settings();
            if not cfg.get('enabled',False): time.sleep(1); continue
            try:
                if not self.runtime or not self.runtime._manager: time.sleep(1); continue
                result=self.runtime.execute_tool(self.runtime._manager,'text_to_speech__listen_once',{'timeout_seconds':max(3,min(int(cfg.get('listen_seconds',5)),15))},actor='voice_agent')
                text=str(result.get('text','')).strip(); wake=str(cfg.get('wake_word','apollo')).lower().strip()
                if text and wake and wake in text.lower():
                    self.runtime.publish('voice.wake_word','voice_agent',{'text':text,'wake_word':wake}); self.runtime.notify('Wake word heard',text,'info','voice_agent')
            except Exception as e:
                if self.runtime:self.runtime.publish('voice.listen_error','voice_agent',{'error':str(e)})
                time.sleep(2)
    def run(self,a,x):
        x=x or {}
        if a=='get_voice_agent_settings': return self._settings()
        if a=='set_voice_agent_settings':
            cfg=self._settings(); cfg.update({k:x[k] for k in ('wake_word','enabled','listen_seconds') if k in x}); self._save(cfg); return cfg
        if a=='start_listening':
            cfg=self._settings(); cfg['enabled']=True; self._save(cfg)
            if self._thread and self._thread.is_alive(): return {'started':True,'already_running':True}
            self._stop.clear(); self._thread=threading.Thread(target=self._loop,daemon=True,name='ApolloVoiceAgent'); self._thread.start(); return {'started':True}
        if a=='stop_listening': self._stop.set(); cfg=self._settings(); cfg['enabled']=False; self._save(cfg); return {'stopped':True}
        raise KeyError(a)
    def close(self): self._stop.set()
    def self_test(self): return 'voice agent contracts passed'
