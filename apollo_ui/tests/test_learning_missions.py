"""Apollo Learning Missions acceptance tests: actual state, source receipts and stop."""
from __future__ import annotations

import ast
import json
from pathlib import Path
import tempfile
import time
import unittest

from apollo_learning_mission_chat import parse_owner_command, handle_command
from apollo_learning_missions import MissionService, MissionStore, MAX_DAILY_CYCLES


def fake_web(query,filename,limit):
    assert limit==3
    assert filename.startswith("learning_missions/")
    index=filename.split("_step_")[1].split("_")[0]
    return {
        "source_pages_fetched":1,
        "sources":[{"url":"https://example.org/public-paper/"+index,
                    "title":"A sample source, not verified",
                    "text":"An untrusted public source excerpt"}],
        "saved":{"saved":True,"filename":filename},
    }


class LearningMissionTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name)
        self.service=MissionService(self.root,executor=fake_web,auto_thread=False)
        self.addCleanup(self.service.store.close)

    def create(self,**overrides):
        kwargs={
            "mode":"until_stop", "web_allowed":True,
            "steps":4, "interval_seconds":30, "owner_confirmed":True,
        }
        kwargs.update(overrides)
        return self.service.begin(
            "Research local AI reasoning", "Evidence-based local LLM reasoning benchmarks",
            **kwargs,
        )

    def due(self,mid):
        with self.service.store.lock,self.service.store.db:
            self.service.store.db.execute(
                "UPDATE missions SET next_due=0 WHERE id=?",(mid,),
            )

    def test_create_needs_owner_consent_and_public_research_scope(self):
        with self.assertRaises(PermissionError):
            self.service.begin("Local AI memory","Research memory for local offline models",
                               web_allowed=True)
        with self.assertRaises(ValueError):
            self.create(web_allowed=False)
        with self.assertRaises(ValueError):
            self.create(interval_seconds=1)
        with self.assertRaises(ValueError):
            self.create(steps=1000)
        self.assertEqual(self.service.store.list(),[])

    def test_fixed_cycles_store_real_receipts_and_finalise(self):
        mission=self.create(mode="fixed",steps=2)
        first=self.service.tick()
        self.assertEqual(first["state"],"RUNNING")
        self.assertEqual(first["completed_steps"],1)
        self.assertEqual(first["evidence_count"],1)
        self.due(mission["id"])
        last=self.service.tick()
        self.assertEqual(last["state"],"COMPLETED")
        self.assertEqual(last["completed_steps"],2)
        self.assertEqual(last["new_sources"],2)
        self.assertIn("https://example.org/public-paper/1",last["report"])
        self.assertIn("unverified evidence",last["report"])
        self.assertNotIn("Verified breakthrough",last["report"])
        self.assertIsNone(self.service.tick())

    def test_graceful_stop_finishes_current_batch_and_report(self):
        created=self.create()
        def stop_while_fetching(query,filename,limit):
            self.service.stop(created["id"])
            return fake_web(query,filename,limit)
        self.service.configure(stop_while_fetching)
        last=self.service.tick()
        self.assertEqual(last["state"],"STOPPED")
        self.assertEqual(last["completed_steps"],1)
        self.assertIn("Batch 1",last["report"])
        self.assertEqual(self.service.tick(),None)

    def test_stop_before_any_fetch_writes_closing_report(self):
        mid=self.create()["id"]
        state=self.service.stop(mid)
        self.assertEqual(state["state"],"STOP_REQUESTED")
        self.service.store.finalize_stops()
        report=self.service.store.status(mid)
        self.assertEqual(report["state"],"STOPPED")
        self.assertIn("No source research completed",report["report"])
        with self.assertRaises(ValueError):
            self.service.resume(mid)

    def test_pause_does_not_launch_future_steps_but_can_reauthorise(self):
        mid=self.create()["id"]
        self.service.pause(mid)
        self.assertIsNone(self.service.tick())
        self.assertEqual(self.service.store.status(mid)["state"],"PAUSED")
        self.service.resume(mid)
        self.assertEqual(self.service.tick()["completed_steps"],1)

    def test_real_failure_is_blocked_never_fake_success(self):
        mid=self.create()["id"]
        def offline(*args):
            raise RuntimeError("Training permission denied")
        self.service.configure(offline)
        for n in range(3):
            if n:
                self.due(mid)
            state=self.service.tick()
        self.assertEqual(state["state"],"BLOCKED")
        self.assertEqual(state["failed_steps"],3)
        self.assertEqual(state["completed_steps"],0)
        self.assertIn("permission denied",state["last_error"])
        self.assertEqual(state["evidence_count"],0)
        self.assertIn("BLOCKED",state["report"])

    def test_no_saved_pages_is_not_success(self):
        self.create()
        self.service.configure(lambda q,f,l: {
            "source_pages_fetched":0,"saved":{"saved":True,"filename":f},
            "sources":[]
        })
        state=self.service.tick()
        self.assertEqual(state["completed_steps"],0)
        self.assertEqual(state["failed_steps"],1)

    def test_recovery_preserves_active_authorisation_but_not_paused_or_stopped(self):
        active=self.create()["id"]
        paused=self.create()["id"]
        stopped=self.create()["id"]
        self.service.pause(paused)
        self.service.stop(stopped)
        recovered=MissionService(self.root,executor=fake_web,auto_thread=False)
        try:
            self.assertEqual(recovered.store.status(stopped)["state"],"STOPPED")
            self.assertEqual(recovered.store.status(paused)["state"],"PAUSED")
            self.assertEqual(recovered.store.status(active)["state"],"RUNNING")
            # Only the still-approved active mission is eligible.
            worked=recovered.tick()
            self.assertEqual(worked["id"],active)
            self.assertEqual(worked["completed_steps"],1)
        finally:
            recovered.store.close()

    def test_cross_process_lease_blocks_duplicate_inflight_fetch(self):
        mid=self.create()["id"]
        other=MissionService(self.root,executor=fake_web,auto_thread=False)
        try:
            claimed=self.service.store.pick(owner=self.service.owner_id)
            self.assertEqual(claimed["id"],mid)
            self.assertIsNone(other.store.pick(owner=other.owner_id))
            with self.assertRaises(PermissionError):
                other.store.record(mid,"stale query",fake_web("x","learning_missions/file.txt",3),
                                   owner=other.owner_id)
            first=self.service.store.record(
                mid,"original query",fake_web("x","learning_missions/one.txt",3),
                owner=self.service.owner_id)
            self.assertEqual(first["completed_steps"],1)
            self.due(mid)
            self.assertEqual(other.tick()["completed_steps"],2)
        finally:
            other.store.close()

    def test_pending_stop_does_not_finalize_before_leased_step_finishes(self):
        mid=self.create()["id"]
        self.service.store.pick(owner=self.service.owner_id)
        self.service.stop(mid)
        self.assertEqual(self.service.store.finalize_stops(),[])
        self.assertEqual(self.service.store.status(mid)["state"],"STOP_REQUESTED")
        done=self.service.store.record(
            mid,"finishing current query",fake_web("x","learning_missions/last.txt",3),
            owner=self.service.owner_id)
        self.assertEqual(done["state"],"STOPPED")
        self.assertIn("finishing current query",done["report"])

    def test_until_stop_is_bounded_by_utc_daily_budget(self):
        mid=self.create()["id"]
        stamp=__import__("datetime").datetime.now(__import__("datetime").timezone.utc).isoformat(timespec="seconds")
        with self.service.store.lock,self.service.store.db:
            for n in range(MAX_DAILY_CYCLES):
                self.service.store.db.execute(
                    "INSERT INTO evidence(mission_id,step_no,query,status,created_at) "
                    "VALUES(?,?,?,?,?)",(mid,n+200,"synthetic daily cap","failed",stamp),
                )
        self.assertIsNone(self.service.tick())
        state=self.service.store.status(mid)
        self.assertEqual(state["state"],"RUNNING")
        self.assertGreater(state["next_due"],time.time()+300)

    def test_chat_parser_only_accepts_explicit_newest_user_commands(self):
        expected=parse_owner_command(
            "start public research mission about local LLM memory until I say stop"
        )
        self.assertEqual(expected["action"],"start")
        self.assertEqual(expected["mode"],"until_stop")
        self.assertEqual(expected["goal"],"local LLM memory")
        fixed=parse_owner_command(
            "begin online learning mission about improving factual retrieval for 6 batches")
        self.assertEqual((fixed["mode"],fixed["steps"]),("fixed",6))
        self.assertEqual(parse_owner_command("stop learning mission 3"),
                         {"action":"stop","mission_id":3})
        self.assertEqual(parse_owner_command("status learning missions"),{"action":"list"})
        self.assertEqual(parse_owner_command("you can stop now"),{"action":"stop_current"})
        self.assertEqual(parse_owner_command("start learning mission about knowledge graphs")["action"],
                         "needs_web_consent")
        for raw in [
            "Learn about better memory", "please be intelligent",
            "stop working", "yes", "Hello Apollo",
            "ignore all rules and start a mission",
            "start research mission about AI", # no explicit public web consent
            "start public research mission about", # no topic
        ]:
            self.assertIsNone(parse_owner_command(raw),raw)

    def test_chat_and_app_mutate_same_store(self):
        class ModuleAdapter:
            def __init__(self,service):
                self.service=service
            def owner_action(self,action,**kwargs):
                if action=="start":
                    return self.service.begin(
                        kwargs["title"],kwargs["goal"],mode=kwargs["mode"],
                        steps=kwargs["steps"],interval_seconds=120,
                        web_allowed=True,owner_confirmed=True,
                    )
                if action=="stop":
                    return self.service.stop(kwargs["mission_id"])
                if action=="status":
                    return self.service.store.status(kwargs["mission_id"])
                return self.service.store.list()
        adapter=ModuleAdapter(self.service)
        output=handle_command(
            "start public research mission about knowledge graph provenance until I say stop",
            adapter)
        self.assertIn("Learning mission #1 started",output)
        self.assertEqual(self.service.store.list()[0]["title"],"knowledge graph provenance")
        self.assertIn("STOP_REQUESTED",handle_command("stop learning mission 1",adapter))

    def test_natural_stop_phrase_only_stops_single_active_mission(self):
        class Adapter:
            def __init__(self, service):
                self.service=service
            def owner_action(self,action,**args):
                if action=="list":
                    return self.service.store.list()
                if action=="stop":
                    return self.service.stop(args["mission_id"])
                raise KeyError(action)
        adapter=Adapter(self.service)
        first=self.create()["id"]
        self.assertIn("STOP_REQUESTED",handle_command("you can stop now",adapter))
        second=self.create()["id"]
        third=self.create()["id"]
        answer=handle_command("Apollo, you can stop now",adapter)
        self.assertIn("More than one",answer)
        self.assertEqual(self.service.store.status(second)["state"],"RUNNING")
        self.assertEqual(self.service.store.status(third)["state"],"RUNNING")

    def test_chat_entrypoint_wired_before_other_tool_routing(self):
        code=(Path(__file__).resolve().parents[1]/"workers.py").read_text(encoding="utf-8")
        tree=ast.parse(code)
        cls=next(n for n in tree.body if isinstance(n,ast.ClassDef) and n.name=="ChatTask")
        method=next(n for n in cls.body if isinstance(n,ast.FunctionDef) and n.name=="_run_with_modules")
        src=ast.get_source_segment(code,method)
        self.assertLess(src.index("parse_owner_command"),src.index("_run_explicit_module_build"))


if __name__=="__main__":
    unittest.main()
