"""Real Qt owner controls and exact chat routing."""
import importlib.util
import os
import unittest
from unittest.mock import patch
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
@unittest.skipIf(importlib.util.find_spec('PySide6') is None,'Qt runs on Windows CI')
class WorkflowQtTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from PySide6.QtWidgets import QApplication
        cls.app=QApplication.instance() or QApplication([])
    def setUp(self):
        from tests.test_workflow_intelligence import ModuleIntegrationTests
        from apollo_workflow_ui import workflow_view
        import shiboken6
        self.fixture=ModuleIntegrationTests(); self.fixture.setUp(); self.addCleanup(self.fixture.doCleanups)
        self.module=self.fixture.module; self.page=workflow_view(self.module); self.page.resize(1100,850)
        self.addCleanup(lambda:shiboken6.delete(self.page))
    def widget(self,kind,name): return self.page.findChild(kind,name)
    def click(self,label):
        from PySide6.QtWidgets import QPushButton
        next(b for b in self.page.findChildren(QPushButton) if b.text()==label).click()
    def start_audit(self):
        from PySide6.QtWidgets import QComboBox,QLineEdit
        self.widget(QComboBox,'workflow_kind').setCurrentIndex(4); self.widget(QLineEdit,'workflow_goal').setText('Audit local Apollo configuration'); self.click('Start workflow')
        return self.module.service.store.list()[0]['id']
    def complete(self):
        for _ in range(4):
            state=self.module.service.tick()
            if state and state['state']=='COMPLETED': return state
        self.fail('Workflow did not complete')
    def test_actual_run_receipts_handoff_and_output(self):
        from PySide6.QtWidgets import QPlainTextEdit
        ident=self.start_audit(); state=self.complete(); self.click('Refresh')
        self.assertEqual(state['id'],ident); self.assertIn('COMPLETED',self.widget(QPlainTextEdit,'workflow_detail').toPlainText())
        self.click('Show latest handoff'); self.assertIn('receipt_sha256',self.widget(QPlainTextEdit,'workflow_detail').toPlainText())
        self.click('Read output'); self.assertIn('configuration audit',self.widget(QPlainTextEdit,'workflow_detail').toPlainText())
    def test_pause_resume_stop_buttons_control_real_state(self):
        ident=self.start_audit(); self.click('Pause'); self.assertEqual(self.module.service.store.status(ident)['state'],'PAUSED')
        self.click('Resume / retry'); self.click('Stop'); self.assertEqual(self.module.service.store.status(ident)['state'],'STOPPED'); self.assertIsNone(self.module.service.tick())
    def test_procedure_owner_approval_and_revocation(self):
        from PySide6.QtWidgets import QTabWidget,QListWidget,QInputDialog
        self.start_audit(); self.complete(); self.start_audit(); self.complete(); self.page.findChild(QTabWidget).setCurrentIndex(1)
        self.widget(QListWidget,'workflow_procedures').setCurrentRow(0)
        with patch.object(QInputDialog,'getText',return_value=('My checked audit workflow',True)): self.click('Approve procedure')
        self.assertEqual(self.module.service.store.procedures()[0]['state'],'approved'); self.click('Revoke'); self.assertEqual(self.module.service.store.procedures()[0]['state'],'revoked')
    def test_selected_memory_node_reaches_run_scope(self):
        from PySide6.QtWidgets import QComboBox,QLineEdit,QCheckBox
        node=self.fixture.bank.create_knowledge_node('Engineering research',kind='project'); destination=self.widget(QComboBox,'workflow_destination')
        destination.addItem('Engineering',node['id']); destination.setCurrentIndex(destination.count()-1)
        self.widget(QLineEdit,'workflow_goal').setText('Retrieval research'); self.widget(QCheckBox,'workflow_web').setChecked(True); self.widget(QCheckBox,'workflow_index').setChecked(True)
        self.click('Start workflow'); run=self.module.service.store.list()[0]; self.assertEqual(run['target_node_id'],node['id']); self.assertTrue(run['index_memory'])
    def test_exact_chat_command_uses_service_before_model(self):
        from workers import ChatTask
        module=self.module
        class Manager:
            def get_module(self,name): return {'enabled':True,'instance':module} if name=='workflow_intelligence' else None
        task=ChatTask(object(),[{'role':'user','content':'Decorated model request'}],Manager(),owner_text='start workflow audit about Apollo settings',work_mode='Deep research')
        self.assertIn('Workflow',task._run_with_modules()); self.assertEqual(len(self.module.service.store.list()),1)
if __name__=='__main__': unittest.main()
