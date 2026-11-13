"""Scheduling contracts for Apollo Initiative Director.

No real network, GPU, external applications or user schedule is started.
"""
from datetime import datetime, timedelta
import importlib.util
import os
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from apollo_initiative_scheduler import ScheduledMissionStore, _wall_ts, _next_occurrence


class ScheduleStoreTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.store = ScheduledMissionStore(self.temp.name)
        self.addCleanup(self.store.close)
        self.today = "2026-11-14"
        self.start = _wall_ts("2026-11-15", "08:00")
        self.before = _wall_ts("2026-11-14", "12:00")

    def create(self, **overrides):
        data = dict(name="Research memory reliability",kind="research",
                    task={"title":"Memory research","goal":"Research reliable retrieval benchmarks"},
                    start_day="2026-11-15",local_time="08:00",repeat="daily",
                    max_runs=5,web_allowed=True,owner_confirmed=True,now=self.before)
        data.update(overrides)
        return self.store.create(**data)

    def test_owner_consent_and_web_scope_required(self):
        with self.assertRaises(PermissionError):
            self.create(owner_confirmed=False)
        with self.assertRaises(PermissionError):
            self.create(web_allowed=False)
        with self.assertRaises(ValueError):
            self.create(kind="shell")
        with self.assertRaises(ValueError):
            self.create(repeat="minutely")
        with self.assertRaises(ValueError):
            self.create(max_runs=0)
        with self.assertRaises(ValueError):
            self.create(start_day="2026-11-13")
        self.assertEqual(self.store.list(),[])

    def test_daily_schedule_queues_one_occurrence(self):
        s = self.create()
        self.assertEqual(s["state"],"active")
        self.assertEqual(s["next_local"],"2026-11-15 08:00")
        run = self.store.reserve_due(now=self.start+1)
        self.assertIsNotNone(run)
        self.assertEqual(run["task_kind"],"research")
        self.assertEqual(run["slot_ts"],self.start)
        self.assertIsNone(self.store.reserve_due(now=self.start+1))
        self.store.finish(run["run_id"],state="queued",receipt={"mission_id":5})
        self.assertEqual(self.store.runs(s["id"])[0]["state"],"queued")
        self.assertEqual(self.store.get(s["id"])["run_count"],1)
        self.assertEqual(self.store.get(s["id"])["next_local"],"2026-11-16 08:00")

    def test_weekly_repeats_on_local_calendar_day(self):
        s = self.create(repeat="weekly")
        task = self.store.reserve_due(now=self.start+1)
        self.assertIsNotNone(task)
        self.store.finish(task["run_id"],state="completed",receipt={"ok":True})
        self.assertEqual(self.store.get(s["id"])["next_local"],"2026-11-22 08:00")

    def test_once_only_runs_once(self):
        s = self.create(repeat="once",max_runs=20)
        self.assertEqual(s["max_runs"],1)
        task=self.store.reserve_due(now=self.start+3)
        self.store.finish(task["run_id"],state="completed",receipt={"ok":True})
        self.assertEqual(self.store.get(s["id"])["state"],"completed")
        self.assertIsNone(self.store.get(s["id"])["next_due"])
        self.assertIsNone(self.store.reserve_due(now=self.start+86400))

    def test_skips_stale_recurrences_but_runs_latest_due_day(self):
        s = self.create(start_day="2026-11-15",local_time="08:00",
                        now=self.before)
        now = _wall_ts("2026-11-20", "11:00")
        task = self.store.reserve_due(now=now)
        self.assertEqual(task["slot_ts"],_wall_ts("2026-11-20","08:00"))
        self.store.finish(task["run_id"],state="queued",receipt={"mission_id":4})
        self.assertEqual(self.store.get(s["id"])["next_local"],"2026-11-21 08:00")
        self.assertEqual(len(self.store.runs(s["id"])),1)

    def test_stale_one_time_task_expires_without_running(self):
        s=self.create(repeat="once")
        self.assertIsNone(self.store.reserve_due(now=_wall_ts("2026-11-19","10:00")))
        self.assertEqual(self.store.get(s["id"])["state"],"expired")
        self.assertEqual(self.store.runs(s["id"]),[])

    def test_pause_resume_stop_must_be_owner_directed(self):
        s=self.create()
        with self.assertRaises(PermissionError):
            self.store.control(s["id"],"pause")
        self.store.control(s["id"],"pause",owner_confirmed=True,now=self.before)
        self.assertIsNone(self.store.reserve_due(now=self.start+1))
        restarted=self.store.control(s["id"],"resume",owner_confirmed=True,
                                     now=self.start+20)
        self.assertEqual(restarted["next_local"],"2026-11-16 08:00")
        self.store.control(s["id"],"stop",owner_confirmed=True)
        with self.assertRaises(ValueError):
            self.store.control(s["id"],"resume",owner_confirmed=True)
        self.assertEqual(self.store.get(s["id"])["state"],"stopped")

    def test_recovery_quarantines_unknown_dispatch(self):
        s=self.create()
        run=self.store.reserve_due(now=self.start+5)
        self.assertEqual(self.store.runs(s["id"])[0]["state"],"reserved")
        other=ScheduledMissionStore(self.temp.name)
        try:
            self.assertIn(s["id"],other.recover())
            self.assertEqual(other.get(s["id"])["state"],"blocked")
            self.assertEqual(other.runs(s["id"])[0]["state"],"uncertain")
            self.assertIsNone(other.reserve_due(now=self.start+86400+5))
        finally:
            other.close()

    def test_cross_connection_lease_never_duplicates(self):
        self.create()
        other=ScheduledMissionStore(self.temp.name)
        try:
            first=self.store.reserve_due(now=self.start+5)
            self.assertIsNotNone(first)
            self.assertIsNone(other.reserve_due(now=self.start+5))
            self.store.finish(first["run_id"],state="queued",receipt={"mission_id":10})
        finally:
            other.close()

    def test_three_failures_block_recurring_task(self):
        s=self.create(max_runs=6)
        for i in range(3):
            tick=_wall_ts(f"2026-11-{15+i:02d}","08:01")
            run=self.store.reserve_due(now=tick)
            self.assertIsNotNone(run)
            self.store.finish(run["run_id"],state="failed",error="Public research unavailable")
        self.assertEqual(self.store.get(s["id"])["state"],"blocked")
        self.assertEqual(self.store.get(s["id"])["consecutive_failures"],3)

    def test_scheduled_local_time_survives_dst_change(self):
        # Both dates are legal; next occurrence should be 08:00 OS-local, not
        # exactly 86400 seconds from the previous run on a DST transition.
        previous=_wall_ts("2027-03-27","08:00")
        nxt=_next_occurrence("2027-03-27","08:00","daily",previous)
        self.assertEqual(datetime.fromtimestamp(nxt).strftime("%Y-%m-%d %H:%M"),
                         "2027-03-28 08:00")

    def test_health_is_strictly_typed_and_offline(self):
        with self.assertRaises(ValueError):
            self.create(kind="health",task={"arbitrary":"tool"},web_allowed=False)
        s=self.create(name="Apollo health check",kind="health",task={},web_allowed=False)
        self.assertEqual(s["task"],{})
        self.assertFalse(s["web_allowed"])


class ScheduleModuleTests(unittest.TestCase):
    def setUp(self):
        from modules.suggestion_center.module import Module
        self.temp=tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.module=Module({"base_dir":self.temp.name,"validation":True})
        self.addCleanup(self.module.close)
        self.calls=[]
        self.missions=[]

        class Manager:
            def execute(_self,module,action,args):
                self.calls.append((module,action,args))
                return {"snapshot":"healthy","ok":True}

        class MissionStore:
            def list(_self):
                return list(self.missions)

        class Missions:
            store=MissionStore()
            def begin(_self,title,goal,**options):
                mission={"id":len(self.missions)+1,"title":title,
                         "goal":goal,"state":"RUNNING","options":options}
                self.missions.append(mission)
                return mission

        self.module._manager=lambda:Manager()
        self.module._missions=lambda:Missions()
        self.future=datetime.now().replace(second=0,microsecond=0)+timedelta(minutes=2)

    def schedule(self,kind):
        data=dict(kind=kind,name="Research Apollo memory" if kind=="research" else "Apollo health check",
                  goal="Research evidence for Apollo memory reliability" if kind=="research" else "",
                  start_day=self.future.strftime("%Y-%m-%d"),
                  local_time=self.future.strftime("%H:%M"),repeat="once",max_runs=1,
                  web_allowed=kind=="research")
        return self.module.owner_create_schedule(**data)

    def due_now(self,ident):
        with self.module.schedules.lock,self.module.schedules.db:
            self.module.schedules.db.execute(
                "UPDATE schedules SET next_due=? WHERE id=?", (time.time()-30,ident))

    def test_daily_research_dispatch_is_a_real_one_step_mission(self):
        s=self.schedule("research")
        self.due_now(s["id"])
        with patch("apollo_idle_learning.foreground_busy",return_value=False):
            tick=self.module.schedule_tick()
        self.assertEqual(tick["state"],"queued")
        self.assertEqual(len(self.missions),1)
        self.assertEqual(self.missions[0]["options"]["mode"],"fixed")
        self.assertEqual(self.missions[0]["options"]["steps"],1)
        self.assertTrue(self.missions[0]["options"]["web_allowed"])
        self.assertEqual(self.module.schedule_history(s["id"])[0]["state"],"queued")

    def test_health_dispatch_calls_only_allowlisted_capability(self):
        s=self.schedule("health")
        self.due_now(s["id"])
        with patch("apollo_idle_learning.foreground_busy",return_value=False):
            tick=self.module.schedule_tick()
        self.assertEqual(tick["state"],"completed")
        self.assertEqual(self.calls,[("background_intelligence","maintenance_pulse",{})])

    def test_foreground_chat_defers_scheduled_execution(self):
        s=self.schedule("research")
        self.due_now(s["id"])
        with patch("apollo_idle_learning.foreground_busy",return_value=True):
            self.assertIsNone(self.module.schedule_tick())
        self.assertEqual(self.module.schedules.get(s["id"])["run_count"],0)
        self.assertEqual(self.missions,[])


os.environ.setdefault("QT_QPA_PLATFORM","offscreen")

@unittest.skipIf(importlib.util.find_spec("PySide6") is None, "Qt GUI tested on Windows CI")
class ScheduledTaskQtTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from PySide6.QtWidgets import QApplication
        cls.app = QApplication.instance() or QApplication([])

    def test_schedule_dialog_can_create_offline_daily_task(self):
        from PySide6.QtCore import QTimer
        from PySide6.QtWidgets import QDialog, QPushButton, QComboBox
        from modules.suggestion_center.module import Module
        from apollo_suggestion_ui import suggestion_view
        import shiboken6

        with tempfile.TemporaryDirectory() as folder:
            module = Module({"base_dir":folder,"validation":True})
            page = suggestion_view(module)
            try:
                events = []
                def configure():
                    dialogs = [w for w in self.app.topLevelWidgets()
                               if isinstance(w,QDialog) and w.windowTitle()=="Apollo scheduled missions"]
                    self.assertEqual(len(dialogs),1)
                    dlg = dialogs[0]
                    task_kind = next(w for w in dlg.findChildren(QComboBox)
                                     if w.findData("health")>=0)
                    task_kind.setCurrentIndex(task_kind.findData("health"))
                    frequency = next(w for w in dlg.findChildren(QComboBox)
                                     if w.findData("daily")>=0)
                    frequency.setCurrentIndex(frequency.findData("daily"))
                    next(w for w in dlg.findChildren(QPushButton)
                         if w.text()=="Create approved schedule").click()
                    events.append(len(module.schedules_status()))
                    dlg.accept()
                QTimer.singleShot(0,configure)
                page.findChild(QPushButton,"initiative_schedules").click()
                self.assertEqual(events,[1])
                record = module.schedules_status()[0]
                self.assertEqual(record["task_kind"],"health")
                self.assertEqual(record["repeat_mode"],"daily")
                self.assertFalse(record["web_allowed"])
            finally:
                shiboken6.delete(page)
                module.close()


if __name__=="__main__":
    unittest.main()
