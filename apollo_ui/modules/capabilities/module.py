from pathlib import Path
from apollo_capabilities import service


class Module:
    def __init__(self, context=None):
        self.context=context or {};self.base=Path(self.context.get('base_dir') or '.').resolve()
        self.service=service(self.base,self.context.get('runtime'))

    def tools(self):
        def tool(name,description,properties=None,required=None):
            schema={'type':'object','properties':properties or {}}
            if required: schema['required']=required
            return {'name':name,'description':description,'parameters':schema}
        return [tool('status','Check installed upstream backends and their actual setup state.'),
            tool('runs','List saved capability execution receipts.'),
            tool('stop','Stop the currently running heavy backend task.'),
            tool('browser_task','Operate a fresh browser inside Docker for an explicitly requested task. Requires owner permission.',
                 {'query':{'type':'string'},'domains':{'type':'array','items':{'type':'string'}}},['query','domains']),
            tool('benchmark_inference','Run a bounded prompt against the configured local llama.cpp server and return measured timings.',
                 {'query':{'type':'string'}},['query'])]

    def run(self, action, arguments):
        x=arguments or {}
        if action=='status': return self.service.status()
        if action=='runs': return {'runs':self.service.runs()}
        if action=='stop': self.service.cancel();return {'stop_requested':True}
        if action=='browser_task': return self.service.run('browser_use','browser_task',x)
        if action=='benchmark_inference': return self.service.run('llama_cpp','inference',x)
        raise KeyError(action)

    def self_test(self):
        assert len(self.service.sources)==8
        return 'Eight pinned optional backends; no model or installer started during validation'

    def build_ui(self,parent=None,ui_context=None):
        from apollo_capability_ui import build_view
        return build_view(self,parent)

    def close(self):
        self.service.cancel()
