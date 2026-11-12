"""Apollo Learning Missions app, backed by the single shared mission service."""
from pathlib import Path
from apollo_learning_missions import shared_service
from apollo_learning_mission_ui import mission_view
from apollo_practice import study, memory_document


class Module:
    def __init__(self,context=None):
        self.context=context or {}
        self.root=Path(self.context.get("base_dir") or ".").resolve()
        self.validation=bool(self.context.get("validation"))
        self.service=shared_service(self.root,executor=self._research,validation=self.validation,
                                    practitioner=self._practice, memory_sink=self._save_lesson)

    def _manager(self):
        runtime=self.context.get("runtime")
        return getattr(runtime,"_manager",None)

    def _research(self,query,filename,limit):
        manager=self._manager()
        if manager is None:
            raise RuntimeError("Apollo module manager not ready; public research cannot start.")
        # Permission broker remains authoritative for each external request.
        return manager.execute(
            "training_module","explore_web_and_save",
            {"query":query,"filename":filename,"limit":limit},
        )

    def _practice(self, goal, result):
        from apollo_config import ApolloConfigStore
        from ollama_client import OllamaClient
        from urllib.parse import urlsplit
        import threading
        config = ApolloConfigStore(self.root).load()
        url = config.get("ollama_url", "http://127.0.0.1:11434")
        if urlsplit(url).hostname not in ("localhost", "127.0.0.1", "::1"):
            raise PermissionError("Practice uses a local Ollama endpoint only. Configure localhost in Settings.")
        if "cloud" in str(config.get("model", "")).casefold():
            raise PermissionError("Choose a locally installed model for practice, rather than an Ollama cloud model.")
        client = OllamaClient(url, config["model"], 0.2,
                              min(int(config.get("num_ctx", 8192)), 8192),
                              config.get("num_batch", 256), config.get("keep_alive", "5m"))
        client.strict_model = True
        # One shared deadline covers study, recall and application problems.
        timeout = threading.Timer(120, client.cancel_generation)
        timeout.daemon = True
        timeout.start()
        try:
            generate=lambda messages: client.chat_once(messages)["message"]["content"]
            lesson=study(goal, result, generate)
            from apollo_workflow_operations import application_questions, grade_application
            from apollo_practice import decode_object
            import json
            bundle=application_questions()
            try:
                response=generate([
                    {"role":"system","content":'Solve the workload/evidence problems. Return JSON only: {"answers":["answer", ...]} in order. No tools.'},
                    {"role":"user","content":json.dumps({"questions":bundle["questions"]})}])
                lesson['application']=grade_application(bundle,decode_object(response))
            except Exception as exc:
                lesson['application_error']=f'{type(exc).__name__}: {exc}'[:600]
            return lesson
        finally:
            timeout.cancel()

    def _save_lesson(self, mission, step_no, lesson):
        manager = self._manager()
        if manager is None:
            raise RuntimeError("Memory Bank is not ready.")
        def execute(action, **arguments):
            return manager.execute("memory_bank", action, arguments)
        # The caller selected this destination; models cannot supply node IDs.
        target = mission.get("target_node_id")
        if target is not None:
            execute("inspect_knowledge_node", node_id=target, limit=1)
        else:
            section = execute("create_knowledge_node", title="Research", kind="section")
            target = execute("create_knowledge_node", title=mission["title"][:160],
                             kind="topic", parent_id=section["id"])["id"]
        receipt = execute("store_memory",
            name=f"Practice mission {mission['id']} batch {step_no}: {mission['title'][:100]}",
            content=memory_document(mission, step_no, lesson), memory_type="research",
            summary=f"Unverified source-linked lesson about {mission['title']}; exact cloze recall {lesson['correct']}/{lesson['total']}.",
            source="Apollo Practice (unverified)",
            source_ref=f"apollo-practice:mission:{mission['id']}:batch:{step_no}",
            tags=["practice", "unverified", mission["title"][:160]], importance=1.0)
        if not receipt.get("stored"):
            raise RuntimeError("Memory Bank rejected the lesson.")
        execute("link_memory_node", memory_id=receipt["id"], node_id=target)
        return receipt

    def tools(self):
        # Tools intentionally read-only: no LLM may fabricate its own
        # owner_confirmed=True approval or spend ungranted web access.
        return [
            {"name":"list_learning_missions",
             "description":"List actual saved Apollo research goals and progress without changing any mission.",
             "parameters":{"type":"object","properties":{}}},
            {"name":"learning_mission_status",
             "description":"Retrieve actual persisted mission events and source research receipts.",
             "parameters":{"type":"object","properties":{"mission_id":{"type":"integer"}},"required":["mission_id"]}},
        ]

    def run(self,action,arguments):
        a=arguments or {}
        if action=="list_learning_missions":
            return {"missions":self.service.store.list()}
        if action=="learning_mission_status":
            return self.service.store.status(a["mission_id"])
        raise KeyError(action)

    def owner_action(self,action,**kwargs):
        """For deterministic explicit Chat commands and Qt owner controls only."""
        if action=="start":
            return self.service.begin(
                kwargs["title"],kwargs.get("goal") or kwargs["title"],
                mode=kwargs.get("mode","until_stop"),web_allowed=True,
                steps=kwargs.get("steps",8),interval_seconds=kwargs.get("interval_seconds",120),
                practice=kwargs.get("practice",False),target_node_id=kwargs.get("target_node_id"),
                owner_confirmed=True,
            )
        if action in ("pause","resume","stop"):
            return getattr(self.service,action)(int(kwargs["mission_id"]))
        if action=="status":
            return self.service.store.status(int(kwargs["mission_id"]))
        if action=="list":
            return self.service.store.list()
        if action=="stop_all":
            return self.service.stop_all()
        raise KeyError("Unknown owner command")

    def self_test(self):
        assert not any("start" in item["name"] or "stop" in item["name"]
                       for item in self.tools())
        return "Learning Missions stores real research, and requires explicit owner actions."

    def build_ui(self,parent=None,ui_context=None):
        return mission_view(self.service,kind="learning",parent=parent,
                            manager=self._manager())

    def close(self):
        # Disabling/unloading Learning Missions must stop scheduling new web
        # research even if Mission Control or Research Library remain loaded.
        # In-flight fetches may finish; saved RUNNING consent is re-evaluated
        # on the next explicitly enabled launch. Closing does NOT mark STOPPED.
        self.service.shutdown()
        if self.validation:
            self.service.store.close()
            if self.service._temp:
                self.service._temp.cleanup()
