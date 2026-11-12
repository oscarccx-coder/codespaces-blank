import tempfile
import time
import unittest
from unittest.mock import patch
from apollo_learning_missions import MissionService,MissionStore
import apollo_idle_learning as idle

class IdleLearningTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.calls=[]
        def fetch(q,f,l):
            self.calls.append(q)
            return {'source_pages_fetched':1,'sources':[{'url':'https://example.org/paper'}],'saved':{'saved':True,'filename':f}}
        self.service=MissionService(self.temp.name,executor=fetch,auto_thread=False)
        self.addCleanup(self.service.store.close)
        self.addCleanup(idle.chat_busy,False)
    def begin(self,**kw):
        return self.service.begin('Idle learning topic','Research local memory improvements',owner_confirmed=True,web_allowed=True,**kw)['id']
    def test_idle_wait_spends_no_budget_then_runs(self):
        mid=self.begin(idle_only=True)
        with patch.object(idle,'idle_ready',return_value=False): self.assertIsNone(self.service.tick())
        state=self.service.store.status(mid)
        self.assertEqual(state['completed_steps'],0); self.assertEqual(state['failed_steps'],0); self.assertEqual(self.calls,[])
        with patch.object(idle,'idle_ready',return_value=True): self.assertEqual(self.service.tick()['completed_steps'],1)
    def test_foreground_chat_defers_normal_and_idle_work(self):
        self.begin(); idle.chat_busy(True)
        self.assertIsNone(self.service.tick()); self.assertEqual(self.calls,[])
        idle.chat_busy(False); self.assertEqual(self.service.tick()['completed_steps'],1)
    def test_pause_stop_not_undone_by_idle(self):
        mid=self.begin(idle_only=True); self.service.pause(mid)
        with patch.object(idle,'idle_ready',return_value=True): self.assertIsNone(self.service.tick())
        self.service.stop(mid); self.service.tick()
        self.assertEqual(self.service.store.status(mid)['state'],'STOPPED'); self.assertEqual(self.calls,[])
    def test_idle_setting_survives_restart(self):
        mid=self.begin(idle_only=True); other=MissionStore(self.temp.name)
        try: self.assertEqual(other.status(mid)['idle_only'],1)
        finally: other.close()
    def test_tracker_requires_attachment_timeout_and_no_busy_chat(self):
        with patch.object(idle,'_attached',False): self.assertFalse(idle.idle_ready(time.monotonic()+1000))
        with patch.object(idle,'_attached',True),patch.object(idle,'_last_activity',100),patch.object(idle,'_busy',False):
            self.assertFalse(idle.idle_ready(399)); self.assertTrue(idle.idle_ready(400))
        with patch.object(idle,'_attached',True),patch.object(idle,'_last_activity',100),patch.object(idle,'_busy',True): self.assertFalse(idle.idle_ready(1000))
    def test_existing_missions_default_to_normal_and_new_settings_validate(self):
        mid=self.begin(); self.assertEqual(self.service.store.status(mid)['idle_only'],0)
        with self.assertRaises(ValueError): self.begin(idle_only='yes')
if __name__=='__main__': unittest.main()
