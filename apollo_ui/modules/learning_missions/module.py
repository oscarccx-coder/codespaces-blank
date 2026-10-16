"""Apollo Learning Missions app, backed by the single shared mission service."""
from pathlib import Path
from apollo_learning_missions import shared_service
from apollo_learning_mission_ui import mission_view


class Module:
    def __init__(self,context=None):
        self.context=context or {}
        self.root=Path(self.context.get("base_dir") or ".").resolve()
        self.validation=bool(self.context.get("validation"))
        self.service=shared_service(self.root,executor=self._research,validation=self.validation)

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
        if self.validation:
            self.service.shutdown()
            self.service.store.close()
            if self.service._temp:
                self.service._temp.cleanup()
