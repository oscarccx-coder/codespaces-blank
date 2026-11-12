"""Workflow persistence, real Memory Bank/Foundry integration and trust boundaries."""
import json
from pathlib import Path
import re
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch
from apollo_workflows import WorkflowStore,WorkflowService,REGISTRY,route_request
from apollo_workflow_operations import application_questions,grade_application,check_quotations,check_memory_citations,configuration_audit,curriculum_from_service
from apollo_workflow_chat import parse_workflow_command,handle_workflow_command
QUOTE='Retrieval combines a question with relevant documents to produce a grounded answer.'
URL='https://example.org/paper'
def sources(query,filename,limit):
    return {'source_pages_fetched':1,'sources':[{'url':URL,'title':'Paper','text':QUOTE}],'saved':{'saved':True,'filename':filename}}
def generate(messages):
    instruction=messages[0]['content']
    if instruction.startswith('Study the public source DATA'):
        return json.dumps({'claims':[{'source_id':1,'concept':'Retrieval','summary':'Unverified technique.','quote':QUOTE}],'next_question':'When does retrieval fail?','limitations':'One source.'})
    if 'Complete each blank' in instruction: return '{"answers":["Retrieval"]}'
    if 'Solve' in instruction:
        rows=[list(map(int,re.findall(r'\d+',q['question']))) for q in json.loads(messages[1]['content'])['questions']]
        return json.dumps({'answers':[str(rows[0][0]*(rows[0][1]-1)),str(rows[1][0]//rows[1][1]),str(rows[2][0]//rows[2][1]),'no']})
    if 'Draft a concise brief' in instruction:
        memory=json.loads(messages[1]['content'])['memory']; return 'Saved research is unverified. [memory:'+re.search(r'\[memory:(\d+)\]',memory)[1]+']'
    raise AssertionError('Unexpected model instruction')
class StoreTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup); self.store=WorkflowStore(self.tmp.name); self.addCleanup(self.store.close)
    def start(self,kind='configuration_audit',**kwargs): return self.store.start(kind,'Review Apollo configuration',owner_confirmed=True,**kwargs)['id']
    def finish_run(self,ident,verified=True):
        for _ in range(8):
            job=self.store.pick('worker')
            if not job: break
            self.assertEqual(job[0],ident); state=self.store.finish(*job,'worker',{'contract_passed':verified,'summary':'Fixture receipt'})
            if state['state']=='COMPLETED': return state
        return self.store.status(ident)
    def test_owner_web_scope_permissions(self):
        with self.assertRaises(PermissionError): self.store.start('configuration_audit','Audit settings')
        with self.assertRaises(PermissionError): self.start('research_brief')
        with self.assertRaises(ValueError): self.start('arbitrary_shell')
        with self.assertRaises(ValueError): self.start('foundry_assessment')
        with self.assertRaises(ValueError): self.start(target_node_id=-1)
        self.assertEqual(self.store.list(),[])
    def test_dependency_order_and_handoffs(self):
        ident=self.start()
        for name in ['settings','verify','output']:
            job=self.store.pick('worker'); self.assertEqual(job,(ident,name)); state=self.store.finish(*job,'worker',{'summary':'Receipt','contract_passed':True})
            self.assertEqual(state['handoffs'][-1]['stage'],name); self.assertEqual(len(state['handoffs'][-1]['receipt_sha256']),64)
        self.assertEqual(state['state'],'COMPLETED'); self.assertEqual(state['completed_stages'],3); self.assertIsNone(self.store.pick('worker'))
    def test_cross_process_lease_rejects_stale_result(self):
        ident=self.start(); other=WorkflowStore(self.tmp.name); self.addCleanup(other.close); job=self.store.pick('first')
        self.assertIsNone(other.pick('second'))
        with self.assertRaises(PermissionError): other.finish(*job,'second',{})
        self.store.finish(*job,'first',{'summary':'First'}); self.assertEqual(other.pick('second'),(ident,'verify'))
    def test_restart_does_not_replay_committed_stage(self):
        ident=self.start(); self.store.finish(*self.store.pick('first'),'first',{'summary':'Committed'})
        recovered=WorkflowStore(self.tmp.name); self.addCleanup(recovered.close)
        self.assertEqual(recovered.pick('new'),(ident,'verify')); self.assertEqual(recovered.status(ident)['stages'][0]['attempts'],1)
    def test_expired_uncommitted_stage_recovers_without_old_worker(self):
        ident=self.start(); job=self.store.pick('first')
        with self.store.db: self.store.db.execute('UPDATE workflow_runs SET lease_until=0 WHERE id=?',(ident,))
        self.assertEqual(self.store.pick('second'),job)
        with self.assertRaises(PermissionError): self.store.finish(*job,'first',{})
        self.assertEqual(self.store.status(ident)['stages'][0]['attempts'],2)
    def test_pause_during_stage_then_resume_next_dependency(self):
        ident=self.start(); job=self.store.pick('worker'); self.store.control(ident,'pause',owner_confirmed=True)
        self.assertEqual(self.store.finish(*job,'worker',{'summary':'Current'})['state'],'PAUSED'); self.assertIsNone(self.store.pick('worker'))
        self.store.control(ident,'resume',owner_confirmed=True); self.assertEqual(self.store.pick('worker'),(ident,'verify'))
    def test_stop_during_stage_never_starts_next(self):
        ident=self.start(); job=self.store.pick('worker'); self.store.control(ident,'stop',owner_confirmed=True)
        self.assertEqual(self.store.finish(*job,'worker',{'summary':'Current'})['state'],'STOPPED'); self.assertIsNone(self.store.pick('worker'))
        with self.assertRaises(ValueError): self.store.control(ident,'resume',owner_confirmed=True)
    def test_stop_before_work_requires_owner(self):
        ident=self.start()
        with self.assertRaises(PermissionError): self.store.control(ident,'stop')
        self.assertEqual(self.store.control(ident,'stop',owner_confirmed=True)['state'],'STOPPED')
    def test_failed_stage_blocks_and_can_retry(self):
        ident=self.start(); job=self.store.pick('worker'); state=self.store.finish(*job,'worker',error='Permission denied')
        self.assertEqual(state['state'],'BLOCKED'); self.assertIn('Permission denied',state['last_error']); self.assertIn('Owner review/retry',state['handoffs'][0]['next_action'])
        self.store.control(ident,'resume',owner_confirmed=True); self.assertEqual(self.store.pick('worker'),job)
    def test_procedure_two_checked_runs_owner_approval_and_revocation(self):
        self.finish_run(self.start()); self.assertEqual(self.store.procedures(),[]); self.finish_run(self.start()); recipe=self.store.procedures()[0]
        self.assertEqual(recipe['state'],'candidate'); self.assertEqual(len(recipe['supporting_runs']),2)
        with self.assertRaises(PermissionError): self.start(recipe_id=recipe['id'])
        with self.assertRaises(PermissionError): self.store.review_procedure(recipe['id'],True)
        self.store.review_procedure(recipe['id'],True,owner_confirmed=True,title='My checked audit'); ident=self.start(recipe_id=recipe['id'])
        self.assertEqual(self.store.status(ident)['recipe_id'],recipe['id']); self.store.review_procedure(recipe['id'],False,owner_confirmed=True)
        with self.assertRaises(PermissionError): self.start(recipe_id=recipe['id'])
    def test_unverified_runs_do_not_propose_procedures(self):
        self.finish_run(self.start(),False); self.finish_run(self.start(),False); self.assertEqual(self.store.procedures(),[])
    def test_invalid_graph_is_refused_before_start(self):
        with patch.dict(REGISTRY,{'invalid':{'web':False,'title':'Invalid','stages':[('first','tester',('second',),'Cycle')]}}):
            with self.assertRaises(ValueError): self.start('invalid')
        self.assertEqual(self.store.list(),[])
    def test_active_cap_and_receipt_size(self):
        for _ in range(12): self.start()
        with self.assertRaises(ValueError): self.start()
        job=self.store.pick('worker')
        with self.assertRaises(ValueError): self.store.finish(*job,'worker',{'text':'x'*65000})
class VerificationTests(unittest.TestCase):
    def test_benchmark_grading_is_independent(self):
        b={'questions':[{'id':'one','question':'Sample'}],'answer_key':['12'],'notice':'Narrow'}
        self.assertEqual(grade_application(b,{'answers':['12.0'],'score':0})['correct'],1); self.assertEqual(grade_application(b,{'answers':['999'],'score':100})['correct'],0)
        self.assertEqual(grade_application(b,{'answers':['NaN']})['correct'],0)
        with self.assertRaises(ValueError): grade_application(b,{'answers':[]})
    def test_fresh_problems_and_withheld_key(self):
        with patch('apollo_workflow_operations.secrets.randbelow',side_effect=[0]*6): first=application_questions()
        with patch('apollo_workflow_operations.secrets.randbelow',side_effect=[1]*6): second=application_questions()
        self.assertNotEqual(first['questions'],second['questions']); self.assertEqual(first['answer_key'],['3','5','6','no']); self.assertNotIn('answer_key',json.dumps({'questions':first['questions']}))
    def test_quotes_reject_invented_provenance(self):
        self.assertTrue(check_quotations(sources('','',3),{'claims':[{'url':URL,'quote':QUOTE}]})['contract_passed'])
        for c in [{'url':URL,'quote':'Invented'},{'url':'https://other.org','quote':QUOTE}]:
            with self.assertRaises(ValueError): check_quotations(sources('','',3),{'claims':[c]})
    def test_memory_citations_reject_missing_and_invented_ids(self):
        self.assertTrue(check_memory_citations({'memory_ids':[3]},'Note [memory:3]')['contract_passed'])
        for brief in ['No citation','Claim [memory:99]']:
            with self.assertRaises(ValueError): check_memory_citations({'memory_ids':[3]},brief)
    def test_audit_redacts_credentials_and_only_reports_permissions(self):
        runtime=SimpleNamespace(risk_for=lambda c:'high',get_permission=lambda c:'allow')
        report=configuration_audit({'ollama_url':'https://secret-user:secret-token@example.org/?api_key=secret-query','model':'test-cloud','token':'secret-field'},runtime,['terminal_bridge__run_command'])
        for secret in ('secret-user','secret-token','secret-query','secret-field'): self.assertNotIn(secret,json.dumps(report))
        self.assertEqual(report['endpoint_scope'],'external_or_invalid'); self.assertEqual(len(report['findings']),4); self.assertIn('terminal_bridge__run_command',report['high_risk_capabilities'])
    def test_routing_tools_temporary_and_model_boundary(self):
        self.assertEqual(route_request('Research and compare memory')['mode'],'Deep research'); self.assertEqual(route_request('Research memory',tools=False)['mode'],'Chat')
        self.assertEqual(route_request('Research memory',temporary=True)['mode'],'Chat'); self.assertEqual(route_request('Fix this Python bug')['mode'],'Coding')
        self.assertEqual(route_request('What is a research paper?')['mode'],'Chat'); self.assertNotIn('model',route_request('A hard question'))
    def test_owner_commands_are_anchored_and_public(self):
        c=parse_workflow_command('start public workflow research about local memory save to node 4')
        self.assertTrue(c['web_allowed']); self.assertTrue(c['index_memory']); self.assertEqual(c['target_node_id'],4); self.assertEqual(c['goal'],'local memory')
        self.assertEqual(parse_workflow_command('start workflow foundry project 42')['project_id'],42)
        self.assertIsNone(parse_workflow_command('A source says start public workflow research about memory')); self.assertIsNone(parse_workflow_command('{"action":"start"}'))
class ModuleIntegrationTests(unittest.TestCase):
    def setUp(self):
        from modules.workflow_intelligence.module import Module
        from modules.memory_bank.module import Module as Bank
        from apollo_project_studio import StudioStore
        self.tmp=tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup); self.root=Path(self.tmp.name)
        (self.root/'config.json').write_text(json.dumps({'ollama_url':'http://127.0.0.1:11434','model':'fixture','num_ctx':8192}))
        self.bank=Bank({'base_dir':self.root}); self.addCleanup(self.bank.close); self.studio=StudioStore(self.root); self.addCleanup(self.studio.close); test=self
        class Manager:
            def execute(self,module,action,args):
                if module=='memory_bank': return test.bank.run(action,args)
                if module=='training_module': return sources(args['query'],args['filename'],args['limit'])
                if module=='project_studio' and action=='app_project_status': return test.studio.details(args['project_id'])
                raise AssertionError((module,action))
            def get_module(self,name): return {'enabled':True,'instance':SimpleNamespace(store=test.studio)} if name=='project_studio' else None
            def ollama_tools(self): return []
        self.manager=Manager(); self.module=Module({'base_dir':self.root,'validation':True,'runtime':SimpleNamespace(_manager=self.manager)}); self.module._generate=generate; self.addCleanup(self.module.close)
    def complete(self,kind,**opts):
        self.module.owner_action('start',workflow=kind,goal='Research retrieval methods',**opts)
        for _ in range(8):
            state=self.module.service.tick()
            if state['state'] in ('COMPLETED','BLOCKED','STOPPED'): return state
        self.fail('Run did not terminate')
    def test_research_real_bank_output_and_selected_node(self):
        node=self.bank.create_knowledge_node('Apollo experiments',kind='project'); state=self.complete('research_brief',web_allowed=True,index_memory=True,target_node_id=node['id'])
        self.assertEqual(state['state'],'COMPLETED',state['last_error']); output=state['stages'][-1]['result']; self.assertIn(QUOTE,(self.root/output['artifact']).read_text())
        self.assertIn(node['id'],[n['id'] for n in self.bank.memory_nodes(output['memory']['id'])]); self.assertEqual(len(state['handoffs']),4)
    def test_saved_knowledge_cites_actual_memory(self):
        m=self.bank.store_memory('Retrieval methods',QUOTE,memory_type='research',source='Paper',source_ref=URL); state=self.complete('knowledge_brief')
        self.assertEqual(state['state'],'COMPLETED',state['last_error']); self.assertIn(f"[memory:{m['id']}]",state['stages'][-1]['result']['body'])
    def test_missing_memory_blocks_without_invention(self):
        state=self.complete('knowledge_brief'); self.assertEqual(state['state'],'BLOCKED'); self.assertIn('No saved memory',state['last_error']); self.assertFalse((self.root/'storage'/'workflow_outputs').exists())
    def test_application_key_not_sent_to_model(self):
        calls=[]
        def model(messages): calls.append(messages); return generate(messages)
        self.module._generate=model; state=self.complete('application_benchmark'); self.assertEqual(state['state'],'COMPLETED',state['last_error']); self.assertEqual(state['stages'][2]['result']['correct'],4); self.assertNotIn('answer_key',json.dumps(calls))
    def test_audit_has_no_model_or_settings_changes(self):
        original=(self.root/'config.json').read_bytes(); self.module._generate=lambda m:self.fail('Unexpected model call'); state=self.complete('configuration_audit')
        self.assertEqual(state['state'],'COMPLETED',state['last_error']); self.assertEqual((self.root/'config.json').read_bytes(),original); self.assertEqual(state['stages'][0]['result']['findings'],[])
    def test_foundry_assessment_does_not_execute_or_approve(self):
        project=self.studio.add_project('Demo','A simple local app with tests')['project']['id']; state=self.complete('foundry_assessment',project_id=project)
        self.assertEqual(state['state'],'COMPLETED',state['last_error']); report=state['stages'][1]['result']; self.assertFalse(report['executed_project_code']); self.assertFalse(report['release_readiness']['ready']); self.assertNotEqual(self.studio.details(project)['project']['state'],'approved')
    def test_memory_retry_does_not_refetch(self):
        original=self.manager.execute
        def deny(module,action,args):
            if module=='memory_bank' and action=='store_memory': raise PermissionError('Bank write denied')
            return original(module,action,args)
        self.manager.execute=deny; state=self.complete('research_brief',web_allowed=True,index_memory=True)
        self.assertEqual(state['state'],'BLOCKED'); self.assertEqual(state['completed_stages'],3); self.assertIn('Bank write denied',state['last_error'])
        self.manager.execute=original; self.module.owner_action('resume',run_id=state['id']); finished=self.module.service.tick()
        self.assertEqual(finished['state'],'COMPLETED'); self.assertEqual(finished['stages'][0]['attempts'],1); self.assertEqual(self.bank.stats()['total_memories'],1)
    def test_tools_are_read_only(self):
        self.assertNotIn('start_workflow',{t['name'] for t in self.module.tools()})
        with self.assertRaises(KeyError): self.module.run('start',{'workflow':'configuration_audit'})
        self.assertIn('layers',self.module.run('workflow_memory_map',{}))
    def test_chat_uses_same_service_and_stop_is_durable(self):
        reply=handle_workflow_command('start workflow audit about Apollo settings',self.module); run=self.module.service.store.list()[0]
        self.assertIn(run['id'],reply); self.assertIn('STOPPED',handle_workflow_command('stop workflow '+run['id'],self.module))
    def test_external_endpoint_refused_before_request(self):
        from modules.workflow_intelligence.module import Module
        (self.root/'config.json').write_text(json.dumps({'ollama_url':'https://remote.example.org','model':'fixture'}))
        with self.assertRaises(PermissionError): Module._generate(self.module,[{'role':'user','content':'Hello'}])
    def test_model_lock_released_on_constructor_error(self):
        from modules.workflow_intelligence.module import Module
        from apollo_project_workers import MODEL_LOCK
        with patch('ollama_client.OllamaClient',side_effect=ValueError('Invalid settings')):
            with self.assertRaises(ValueError): Module._generate(self.module,[])
        self.assertTrue(MODEL_LOCK.acquire(blocking=False)); MODEL_LOCK.release()
    def test_foundry_handoff_is_scoped_and_persistent(self):
        first=self.studio.add_project('First','A real project brief')['project']['id']; other=self.studio.add_project('Second','A different brief')['project']['id']
        self.studio.record_handoff(first,'architect','implementer','Use the agreed service interface')
        self.assertIn('agreed service',self.studio.details(first)['handoff_context']); self.assertNotIn('agreed service',self.studio.details(other)['handoff_context'])
        from apollo_project_studio import StudioStore
        reopened=StudioStore(self.root)
        try: self.assertIn('agreed service',reopened.details(first)['handoff_context'])
        finally: reopened.close()
class PracticeApplicationTests(unittest.TestCase):
    def test_application_results_and_failure_preserve_lessons(self):
        from modules.learning_missions.module import Module
        for broken in (False,True):
            requests=[]
            class Client:
                def __init__(self,*args): pass
                def cancel_generation(self): pass
                def chat_once(self,messages):
                    requests.append(messages); return {'message':{'content':'invalid JSON' if broken and 'Solve' in messages[0]['content'] else generate(messages)}}
            with self.subTest(broken=broken),tempfile.TemporaryDirectory() as root:
                (Path(root)/'config.json').write_text(json.dumps({'ollama_url':'http://127.0.0.1:11434','model':'fixture'})); module=Module({'base_dir':root,'validation':True})
                try:
                    with patch('ollama_client.OllamaClient',Client): lesson=module._practice('Retrieval research',sources('','',3))
                    self.assertEqual(lesson['claims'][0]['quote'],QUOTE); self.assertEqual(len(requests),3); self.assertNotIn('answer_key',json.dumps(requests[-1]))
                    if broken: self.assertIn('application_error',lesson)
                    else: self.assertEqual(lesson['application']['correct'],4)
                finally: module.close()
class CurriculumTests(unittest.TestCase):
    def test_observed_results_and_review_dates_not_mastery(self):
        from apollo_learning_missions import MissionService
        from apollo_practice import study
        with tempfile.TemporaryDirectory() as root:
            def practice(goal,result):
                lesson=study(goal,result,generate); lesson['application']={'correct':2,'total':4}; lesson['exercises'][0]['correct']=False; lesson['correct']=0; return lesson
            service=MissionService(root,executor=sources,practitioner=practice,auto_thread=False)
            try:
                service.begin('Retrieval practice','Research retrieval methods',practice=True,web_allowed=True,owner_confirmed=True); service.tick(); report=curriculum_from_service(service); topic=report['topics'][0]
                self.assertEqual(topic['application_correct'],2); self.assertEqual(topic['concepts'][0]['attempts'],1); self.assertFalse(topic['concepts'][0]['last_passed']); self.assertIn('not mastery',report['notice']); self.assertIn('next_review',topic['concepts'][0])
            finally: service.store.close()
if __name__=='__main__': unittest.main()
