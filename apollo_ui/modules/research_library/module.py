"""Research Library: view the shared Apollo learning mission ledger."""
from pathlib import Path
from apollo_learning_missions import shared_service
from apollo_learning_mission_ui import mission_view


class Module:
    def __init__(self,context=None):
        self.context=context or {}
        self.validation=bool(self.context.get("validation"))
        self.root=Path(self.context.get("base_dir") or ".").resolve()
        self.service=shared_service(self.root,validation=self.validation)

    def tools(self):
        return []

    def run(self,action,arguments):
        raise KeyError(action)

    def self_test(self):
        return "Read persistent mission outcomes using the shared mission service."

    def build_ui(self,parent=None,ui_context=None):
        runtime=self.context.get("runtime")
        manager=getattr(runtime,"_manager",None)
        return mission_view(self.service,kind="library",parent=parent,manager=manager)

    def close(self):
        if self.validation:
            self.service.shutdown()
            self.service.store.close()
            if self.service._temp:
                self.service._temp.cleanup()
