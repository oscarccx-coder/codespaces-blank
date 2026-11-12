import importlib.util
import json
import os
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch
from apollo_suggestions import SuggestionStore,validate_proposals
from modules.suggestion_center.module import Module

class SuggestionTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup); self.store=SuggestionStore(self.tmp.name); self.addCleanup(self.store.close)
    def test_deduplicate_and_preserve_dismissal_after_restart(self):
        item=self.store.add('proposal','Study retrieval','Research retrieval failure cases','A concrete knowledge gap',[3]); self.store.review(item['id'],'dismissed')
        second=SuggestionStore(self.tmp.name)
        try:
            same=second.add('proposal','STUDY RETRIEVAL','Different prompt','Still not approved',[3])
            self.assertEqual(same['id'],item['id']); self.assertEqual(same['status'],'dismissed')
        finally: second.close()
    def test_owner_answers_keep_revision_history_and_context(self):
        item=self.store.add('question','Which goal?','What should Apollo prioritise?','Owner guidance needed')
        self.store.answer(item['id'],'Apollo memory first'); self.store.answer(item['id'],'Actually focus on Foundry')
        item=self.store.get(item['id']); self.assertEqual(item['status'],'answered'); self.assertEqual(len(item['answers']),2)
        self.assertEqual(self.store.guidance_context()[0]['answer'],'Actually focus on Foundry')
    def test_proposal_cannot_be_answered_and_text_is_bounded(self):
        item=self.store.add('proposal','A useful task','Research local AI evidence','No work started')
        with self.assertRaises(ValueError): self.store.answer(item['id'],'Hello')
        with self.assertRaises(ValueError): self.store.add('question','x'*181,'prompt','reason')
    def test_cross_process_reservation_and_disable(self):
        self.assertTrue(self.store.reserve()); other=SuggestionStore(self.tmp.name)
        try: self.assertFalse(other.reserve())
        finally: other.close()
        self.store.set_state('next_due','0'); self.store.set_state('enabled','0'); self.assertFalse(self.store.reserve())
    def test_daily_budget(self):
        for _ in range(4):
            self.store.set_state('next_due','0'); self.assertTrue(self.store.reserve())
        self.store.set_state('next_due','0'); self.assertFalse(self.store.reserve())
    def test_model_cannot_invent_evidence_or_turn_prompt_into_action(self):
        item={'kind':'proposal','title':'A task','prompt':'start anything','reason':'Only a proposal','mission_ids':[99]}
        self.assertEqual(validate_proposals({'suggestions':[item]},{1}),[])
        item['mission_ids']=[1]; result=validate_proposals({'suggestions':[item]},{1})
        self.assertEqual(result[0]['prompt'],'start anything'); self.assertNotIn('execute',result[0])
    def test_inbox_is_bounded(self):
        for i in range(50): self.store.add('proposal',f'Topic {i}','Research an explicit public topic','Not started')
        with self.assertRaises(ValueError): self.store.add('proposal','A new one','Another public topic','No work started')

class ModuleTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.module=Module({'base_dir':self.tmp.name,'validation':True}); self.addCleanup(self.module.close)
    def test_seed_question_is_real_and_tools_are_read_only(self):
        items=self.module.run('list_suggestions',{})['items']; self.assertEqual(items[0]['kind'],'question')
        self.assertEqual([t['name'] for t in self.module.tools()],['list_suggestions'])
        with self.assertRaises(KeyError): self.module.run('start_research',{})
    def test_private_answer_stays_local_without_memory_option(self):
        result=self.module.owner_answer(self.module.store.list()[0]['id'],'Prioritise reliable memory')
        self.assertTrue(result['saved_locally']); self.assertNotIn('memory',result)
    def test_memory_failure_does_not_lose_owner_guidance(self):
        result=self.module.owner_answer(self.module.store.list()[0]['id'],'Focus on useful research',True)
        self.assertTrue(result['saved_locally']); self.assertIn('memory_error',result)
        self.assertEqual(self.module.store.guidance_context()[0]['answer'],'Focus on useful research')
    def test_research_needs_explicit_public_consent_and_owner_channel(self):
        item=self.module.store.add('proposal','Research memory','Research retrieval evidence','A suggested task')
        with self.assertRaises(PermissionError): self.module.start_research(item['id'],item['prompt'])
        self.assertIsNone(self.module.store.get(item['id'])['mission_id'])
    def test_research_acknowledgement_deduplicates_repeated_clicks(self):
        rows=[]
        class Missions:
            store=SimpleNamespace(list=lambda:rows)
            def begin(self,title,prompt,**options):
                rows.append({'id':17,'title':title,'goal':prompt,**options}); return rows[-1]
        self.module._missions=lambda:Missions()
        item=self.module.store.add('proposal','Research local memory','Research memory evidence','A new hypothesis')
        first=self.module.start_research(item['id'],item['prompt'],True); second=self.module.start_research(item['id'],item['prompt'],True)
        self.assertEqual(first['id'],second['id']); self.assertEqual(len(rows),1)
        self.assertTrue(rows[0]['idle_only']); self.assertTrue(rows[0]['practice'])
    def test_idle_reflection_uses_guidance_and_observed_gaps(self):
        self.module._manager=lambda:object()
        self.module.snapshot=lambda:{'missions':[{'id':2,'title':'Memory','goal':'Research memory','state':'RUNNING','next_gap':'What fails?'}],'owner_guidance':[{'title':'Priority','answer':'Memory first'}]}
        contexts=[]
        def generate(context):
            contexts.append(context); return {'suggestions':[{'kind':'question','title':'Which benchmark matters?','prompt':'Which benchmark would you like me to improve?','reason':'Need a measurable goal','mission_ids':[2]}]}
        self.module._generate=generate
        with patch('apollo_idle_learning.idle_ready',return_value=False): self.assertTrue(self.module.pulse()['waiting'])
        with patch('apollo_idle_learning.idle_ready',return_value=True): self.module.pulse(); self.module.pulse()
        self.assertEqual(len(contexts),1); self.assertIn('Memory first',json.dumps(contexts))
        self.assertTrue(any(i['kind']=='proposal' for i in self.module.store.list()))
    @unittest.skipIf(importlib.util.find_spec('apollo_config') is None,'Full repository dependency check runs in CI')
    def test_external_reflection_endpoint_is_refused(self):
        (Path(self.tmp.name)/'config.json').write_text(json.dumps({'ollama_url':'https://external.example.org','model':'local-name'}))
        with self.assertRaises(PermissionError): self.module._generate({'missions':[],'owner_guidance':[]})

    def test_failed_local_reflection_is_visible(self):
        self.module._manager=lambda:object(); self.module.snapshot=lambda:{'missions':[],'owner_guidance':[]}; self.module._generate=lambda c:(_ for _ in ()).throw(RuntimeError('Ollama unavailable'))
        with patch('apollo_idle_learning.idle_ready',return_value=True): self.assertIn('error',self.module.pulse())
        self.assertIn('Ollama unavailable',self.module.store.state('last_error'))

os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
@unittest.skipIf(importlib.util.find_spec('PySide6') is None,'Qt runs on Windows CI')
class SuggestionQtTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from PySide6.QtWidgets import QApplication
        cls.app=QApplication.instance() or QApplication([])
    def test_save_answer_and_disable_reflection_through_real_widgets(self):
        from apollo_suggestion_ui import suggestion_view
        from PySide6.QtWidgets import QPlainTextEdit,QPushButton,QCheckBox
        import shiboken6
        with tempfile.TemporaryDirectory() as root:
            module=Module({'base_dir':root,'validation':True}); page=suggestion_view(module)
            try:
                page.findChild(QPlainTextEdit,'guidance_answer').setPlainText('Improve Foundry reliability first')
                next(b for b in page.findChildren(QPushButton) if b.text()=='Save answer').click()
                self.assertEqual(module.store.list()[0]['status'],'answered')
                next(w for w in page.findChildren(QCheckBox) if 'Allow occasional' in w.text()).setChecked(False)
                self.assertEqual(module.store.state('enabled'),'0')
            finally: shiboken6.delete(page); module.close()
    @unittest.skipIf(importlib.util.find_spec('apollo_chat_files') is None,'Full chat dependency check runs in Windows CI')
    def test_chat_question_banner_hides_during_work_and_in_temporary_chat(self):
        from tests.test_chat_workspace import WorkspaceQtTests
        WorkspaceQtTests.setUpClass(); fixture=WorkspaceQtTests(); fixture.setUp()
        with tempfile.TemporaryDirectory() as root:
            module=Module({'base_dir':root,'validation':True})
            try:
                fixture.owner.module_manager.get_module=lambda key:{'enabled':True,'instance':module} if key=='suggestion_center' else None
                view=fixture.view; view._guidance_tick(); self.assertFalse(view.guidance_button.isHidden())
                view._set_busy(True); self.assertTrue(view.guidance_button.isHidden())
                view._set_busy(False); view.new_chat(temporary=True); self.assertTrue(view.guidance_button.isHidden())
            finally: fixture.doCleanups(); module.close()

if __name__=='__main__': unittest.main()
