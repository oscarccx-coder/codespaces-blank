import os
class Module:
    def __init__(self,context=None): pass
    def tools(self): return [
        {"name":"list_processes","description":"List running local processes with PID/CPU/memory.","parameters":{"type":"object","properties":{"limit":{"type":"integer"}}}},
        {"name":"process_info","description":"Read one process by PID.","parameters":{"type":"object","properties":{"pid":{"type":"integer"}},"required":["pid"]}},
        {"name":"terminate_process","description":"Terminate a process by PID. High-risk and blocked by default.","parameters":{"type":"object","properties":{"pid":{"type":"integer"}},"required":["pid"]}},
    ]
    def run(self,a,x):
        import psutil; x=x or {}
        if a=='list_processes':
            rows=[]
            for p in psutil.process_iter(['pid','name','cpu_percent','memory_info']):
                try: rows.append({'pid':p.info['pid'],'name':p.info['name'],'cpu_percent':p.info.get('cpu_percent',0),'memory_mb':round((p.info['memory_info'].rss if p.info.get('memory_info') else 0)/1048576,1)})
                except Exception:pass
            rows.sort(key=lambda r:r['memory_mb'],reverse=True); return {'processes':rows[:max(1,min(int(x.get('limit',100)),500))]}
        if a=='process_info':
            p=psutil.Process(int(x['pid'])); return {'pid':p.pid,'name':p.name(),'exe':p.exe() if p.exe() else '', 'status':p.status(),'memory_mb':round(p.memory_info().rss/1048576,1)}
        if a=='terminate_process':
            pid=int(x['pid']);
            if pid==os.getpid(): raise RuntimeError('Apollo refuses to terminate its own process through this tool')
            p=psutil.Process(pid); name=p.name(); p.terminate(); return {'terminated':True,'pid':pid,'name':name}
        raise KeyError(a)
    def self_test(self): return 'process manager contracts passed'
