"""Apollo app consolidation catalog. Groups UIs; NEVER uninstalls module tools.

Backends remain available to the local model, permissions and other apps.
The main UI defaults to everyday surfaces, with developer/experimental tools
still available under the Advanced filter.
"""
GROUPS = ("Everyday", "Coding", "Memory & Learning", "System", "Advanced", "All")

MODULE_GROUPS = {
    "voice_center": "Everyday",
    "voice_imprint_trainer": "Advanced",
    "text_to_speech": "Advanced",
    "file_manager": "Everyday",
    "vehicle_diagnostics": "Everyday",
    "circuit_lab": "Everyday",
    "notification_center": "Everyday",
    "workspace_manager": "Coding",
    "model_runtime": "Coding",
    "self_improvement_lab": "Coding",
    "growth_lab": "Coding",
    "task_engine": "Coding",
    "roadmap": "Coding",
    "benchmark_suite": "Advanced",
    "verification_engine": "Advanced",
    "module_factory": "Advanced",
    "upgrade_history": "Advanced",
    "orchestrator": "Advanced",
    "context_manager": "Advanced",
    "conversation_flow": "Advanced",
    "todo_list": "Everyday",
    "memory_bank": "Memory & Learning",
    "chat_memory_module": "Advanced",
    "memory_intelligence": "Advanced",
    "memory_distillation": "Advanced",
    "knowledge_graph": "Advanced",
    "pile_knowledge": "Memory & Learning",
    "training_module": "Memory & Learning",
    "web_explorer": "Advanced",
    "neural_learning": "Advanced",
    "neural_visualizer": "Advanced",
    "capability_graph": "Advanced",
    "core_services": "System",
    "gpu_monitor": "System",
    "activity_trace": "Advanced",
    "dependency_manager": "System",
    "desktop_services": "Advanced",
    "fleet_manager": "Advanced",
    "cluster_manager": "Advanced",
    "device_agent": "Advanced",
    "device_bridge": "Advanced",
    "process_manager": "Advanced",
    "system_info": "Advanced",
    "background_intelligence": "Advanced",
    "self_awareness": "Advanced",
    "screen_vision": "Advanced",
    "automation_engine": "Advanced",
    "voice_agent": "Advanced",
    "file_builder": "Advanced",
    "calculator": "Advanced",
    "terminal_bridge": "Advanced",
}


def group_for(module_id):
    return MODULE_GROUPS.get(str(module_id), "Advanced")


def is_visible(module_id, filter_name="Everyday"):
    return filter_name == "All" or group_for(module_id) == filter_name


def main_app_for(module_id):
    """Canonical app for overlapping visible voice tools and other front ends."""
    aliases = {
        "voice_imprint_trainer": "voice_center",
        "text_to_speech": "voice_center",
        "memory_intelligence": "memory_bank",
        "memory_distillation": "memory_bank",
        "activity_trace": "core_services",
        "system_info": "core_services",
        "upgrade_history": "self_improvement_lab",
    }
    return aliases.get(str(module_id), str(module_id))
