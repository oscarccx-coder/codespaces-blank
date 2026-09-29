from pathlib import Path
from datetime import datetime, timezone
import json


ROADMAP_SCHEMA_VERSION = 2
DEFAULT_ROADMAP = [
    {"version": "7.5.12.4", "id": "fleet_cluster_foundation", "title": "Fleet + Cluster Foundation", "status": "active", "category": "Distributed Apollo", "summary": "Authenticated Device Agent, Fleet registry/UI and task-parallel Cluster scheduler across trusted Apollo nodes."},
    {"version": "7.5.12.5", "id": "fleet_rollout_controller", "title": "Fleet Rollout Controller", "status": "planned", "category": "Distributed Apollo", "summary": "Central staged/canary update rollout, compatibility filtering, offline queues and rollout journal."},
    {"version": "7.5.12.6", "id": "distributed_snapshots", "title": "Distributed Project Snapshots", "status": "planned", "category": "Distributed Apollo", "summary": "Content-addressed project snapshots and isolated worker workspaces instead of shared-folder editing."},
    {"version": "7.5.12.7", "id": "cluster_reassignment_verification", "title": "Cluster Reassignment + Verification", "status": "planned", "category": "Distributed Apollo", "summary": "Worker leases, automatic reassignment, peer review and Verification Engine integration."},
    {"version": "7.5.12.8", "id": "mission_cluster_integration", "title": "Development Missions + Cluster", "status": "planned", "category": "Distributed Apollo", "summary": "Timed Development Missions can decompose DAGs and distribute independent work across Apollo nodes."},
    {"version": "7.5.12.3", "id": "update_storage_foundation", "title": "Update Service + Storage Layout", "status": "active", "category": "Foundation", "summary": "Signed LAN update packages, external rollback updater, Update Manager app and categorized persistent storage."},{'version': '7.5.12.2', 'id': 'roadmap_blueprints_docs', 'title': 'Roadmap Blueprints + Docs Cleanup', 'status': 'active', 'category': 'Foundation', 'summary': 'Expanded internal roadmap, future-feature blueprints and cleaner documentation layout.'}, {'version': '7.5.13', 'id': 'hub_widgets_visualizer2', 'title': 'Hub Widgets + Neural Visualizer 2', 'status': 'planned', 'category': 'OS Shell', 'summary': 'Live Hub widgets plus event-driven neural/module/memory activity visualisation.'}, {'version': '7.5.14', 'id': 'operation_journal', 'title': 'Operation Journal', 'status': 'planned', 'category': 'Reliability', 'summary': 'Permanent record of real actions, file changes, tools, failures, retries and verification.'}, {'version': '7.5.15', 'id': 'snapshots_undo', 'title': 'Project Snapshots / Undo', 'status': 'planned', 'category': 'Reliability', 'summary': 'Atomic project/module checkpoints, rollback and real undo/redo.'}, {'version': '7.5.16', 'id': 'conversation_intelligence', 'title': 'Conversation Intelligence', 'status': 'planned', 'category': 'Intelligence', 'summary': 'Stronger referent resolution, project/topic threads and long-conversation continuity.'}, {'version': '7.5.17', 'id': 'universal_tool_repair', 'title': 'Universal Tool Repair', 'status': 'planned', 'category': 'Reliability', 'summary': 'Normalize malformed calls and repair arguments before controlled retries.'}, {'version': '7.6', 'id': 'verification2', 'title': 'Verification Engine 2', 'status': 'planned', 'category': 'Development', 'summary': 'Runtime, acceptance and project-specific tests beyond syntax.'}, {'version': '7.6.1', 'id': 'automatic_regression', 'title': 'Automatic Regression Tests', 'status': 'planned', 'category': 'Development', 'summary': 'Turn every fixed bug into a permanent regression test.'}, {'version': '7.6.2', 'id': 'automatic_repair', 'title': 'Automatic Repair Loop', 'status': 'planned', 'category': 'Development', 'summary': 'Bounded diagnose → patch → retest → rollback loop.'}, {'version': '7.6.3', 'id': 'development_missions', 'title': 'Development Missions', 'status': 'planned', 'category': 'Development', 'summary': 'Timed autonomous build/test/research/repair missions with deadlines.'}, {'version': '7.6.4', 'id': 'mission_manager', 'title': 'Mission Manager UI', 'status': 'planned', 'category': 'Development', 'summary': 'Pause, resume, inspect and extend long-running development missions.'}, {'version': '7.6.5', 'id': 'research_diagnosis', 'title': 'Research + Diagnosis Engine', 'status': 'planned', 'category': 'Development', 'summary': 'Error-led research that records what was learned and why a repair was attempted.'}, {'version': '7.6.6', 'id': 'deadline_budgeting', 'title': 'Deadline / Resource Budgeting', 'status': 'planned', 'category': 'Development', 'summary': 'Reserve time for verification and stop safely at mission deadlines.'}, {'version': '7.7', 'id': 'workspace_ide', 'title': 'Workspace IDE', 'status': 'planned', 'category': 'Development', 'summary': 'Project tree, editor, diffs, tests and output.'}, {'version': '7.7.3', 'id': 'app_sdk', 'title': 'Apollo App SDK', 'status': 'placeholder', 'category': 'Platform', 'summary': 'Stable app contracts, templates and validation rules for Apollo-created apps.'}, {'version': '7.7.4', 'id': 'project_templates', 'title': 'Project Templates', 'status': 'placeholder', 'category': 'Platform', 'summary': 'Verified starter foundations for common project types.'}, {'version': '7.8', 'id': 'memory3', 'title': 'Memory 3.0', 'status': 'planned', 'category': 'Memory', 'summary': 'Separate conversational, durable, project and learned-memory layers.'}, {'version': '7.8.3', 'id': 'data_provenance', 'title': 'Data Provenance', 'status': 'placeholder', 'category': 'Memory', 'summary': 'Track where learned facts, research, memories and assets came from.'}, {'version': '7.8.4', 'id': 'trust_layer', 'title': 'Trust / Confidence Layer', 'status': 'placeholder', 'category': 'Memory', 'summary': 'Keep verified facts, inference, generated ideas, stale data and conflicts distinct.'}, {'version': '7.8.5', 'id': 'knowledge_provenance_ui', 'title': 'Knowledge Provenance UI', 'status': 'placeholder', 'category': 'Memory', 'summary': 'Inspect why Apollo knows or trusts something.'}, {'version': '7.9', 'id': 'orchestrator_hardening', 'title': 'Agent / Orchestrator Hardening', 'status': 'planned', 'category': 'Agents', 'summary': 'Resumable tasks, permissions and robust orchestration.'}, {'version': '7.9.1', 'id': 'notification_center', 'title': 'Notification Centre', 'status': 'placeholder', 'category': 'OS Shell', 'summary': 'Mission, failure, hardware and update notifications in one place.'}, {'version': '7.10', 'id': 'compute_broker', 'title': 'VRAM / Compute Broker', 'status': 'placeholder', 'category': 'AI Platform', 'summary': 'Share GPU/CPU/RAM safely between LLM, image, vision, voice, video and training.'}, {'version': '7.10.1', 'id': 'model_benchmark_lab', 'title': 'Model Benchmark Lab', 'status': 'placeholder', 'category': 'AI Platform', 'summary': 'Compare local models on real Apollo tasks before changing defaults.'}, {'version': '7.10.2', 'id': 'experiment_lab', 'title': 'Experiment Lab', 'status': 'placeholder', 'category': 'AI Platform', 'summary': 'Compare candidate modules/models/configurations against current Apollo.'}, {'version': '7.11', 'id': 'vision_core', 'title': 'Vision Core', 'status': 'placeholder', 'category': 'Media', 'summary': 'Understand screenshots, photographs, diagrams and UI states.'}, {'version': '7.11.1', 'id': 'image_core', 'title': 'Image Core + Local Backends', 'status': 'placeholder', 'category': 'Media', 'summary': 'Unified image API with ComfyUI first and optional Diffusers backend.'}, {'version': '7.11.2', 'id': 'media_studio', 'title': 'Media Studio + Image Editing', 'status': 'placeholder', 'category': 'Media', 'summary': 'Generate, edit, inpaint, upscale and compare visual assets.'}, {'version': '7.11.3', 'id': 'asset_library', 'title': 'Asset Library', 'status': 'placeholder', 'category': 'Media', 'summary': 'Reusable project images, audio, documents, icons and generated assets.'}, {'version': '7.11.4', 'id': 'style_lora_manager', 'title': 'Style / LoRA Manager', 'status': 'placeholder', 'category': 'Media', 'summary': 'Manage optional local style adapters/reference presets.'}, {'version': '7.12', 'id': 'voice_system', 'title': 'Voice System Expansion', 'status': 'planned', 'category': 'Voice', 'summary': 'Continuous speech, interruption, wake phrase and Voice Imprint integration.'}, {'version': '7.13', 'id': 'hardware_layer', 'title': 'Computer / Hardware Layer', 'status': 'planned', 'category': 'Hardware', 'summary': 'Serial, Arduino, OBD, screen understanding and process/device control.'}, {'version': '7.14', 'id': 'secrets_vault', 'title': 'Secrets Vault', 'status': 'placeholder', 'category': 'Security', 'summary': 'Secure API keys/tokens with per-module access.'}, {'version': '7.14.1', 'id': 'dependency_snapshots', 'title': 'Dependency Snapshots', 'status': 'placeholder', 'category': 'Recovery', 'summary': 'Record exact project/module dependency environments.'}, {'version': '7.14.2', 'id': 'recovery_console', 'title': 'Recovery Console', 'status': 'placeholder', 'category': 'Recovery', 'summary': 'Safe-mode repair, disable broken modules and restore known-good state.'}, {'version': '7.14.3', 'id': 'backup_export', 'title': 'Backup / Export', 'status': 'placeholder', 'category': 'Recovery', 'summary': 'Verified backups and selective restore for Apollo data.'}, {'version': '7.15.1', 'id': 'global_search', 'title': 'Global Search', 'status': 'placeholder', 'category': 'OS Shell', 'summary': 'Search apps, files, projects, memories, conversations and capabilities.'}, {'version': '7.15.2', 'id': 'capability_discovery', 'title': 'Capability Discovery', 'status': 'placeholder', 'category': 'OS Shell', 'summary': 'Answer what Apollo can actually do from the live capability registry.'}, {'version': '7.15.3', 'id': 'local_usage_analytics', 'title': 'Local Usage Analytics', 'status': 'placeholder', 'category': 'Diagnostics', 'summary': 'Private metrics for failures, latency, usage and improvement targets.'}, {'version': '8.0', 'id': 'apollo_os_preview', 'title': 'Apollo OS Preview', 'status': 'planned', 'category': 'OS', 'summary': 'Unified launcher, workspace, apps, automation, memory, media, voice and development missions.'}]


class Module:
    def __init__(self, context=None):
        self.context = context or {}
        self.base = Path(
            self.context.get("base_dir")
            or self.context.get("apollo_base_dir")
            or "."
        ).resolve()
        self.storage = self.base / "storage" / "state" / "roadmap"
        self.storage.mkdir(parents=True, exist_ok=True)
        self.path = self.storage / "roadmap.json"
        self.blueprints_root = self.base / "blueprints" / "future_features"
        self._ensure_file()

    def _default_payload(self):
        return {
            "schema_version": ROADMAP_SCHEMA_VERSION,
            "updated_at": datetime.now(timezone.utc).isoformat(),
            "items": [dict(item) for item in DEFAULT_ROADMAP],
        }

    def _save(self, data):
        temp = self.path.with_suffix(".json.tmp")
        temp.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
        temp.replace(self.path)

    def _merge_defaults(self, data):
        if not isinstance(data, dict):
            data = {}
        existing = data.get("items")
        if not isinstance(existing, list):
            existing = []

        by_id = {}
        by_version = {}
        custom = []

        for item in existing:
            if not isinstance(item, dict):
                continue
            if str(item.get("id", "")).strip():
                by_id[str(item["id"])] = item
            if str(item.get("version", "")).strip():
                by_version.setdefault(str(item["version"]), item)

        merged = []
        used_objects = set()

        for default in DEFAULT_ROADMAP:
            old = by_id.get(default["id"])
            if old is None:
                old = by_version.get(default["version"])

            item = dict(default)
            if old is not None:
                # Preserve user/runtime progress while adding new schema fields.
                for field in ("status", "summary"):
                    if str(old.get(field, "")).strip():
                        item[field] = old[field]
                used_objects.add(id(old))
            merged.append(item)

        for old in existing:
            if isinstance(old, dict) and id(old) not in used_objects:
                custom.append(old)

        payload = {
            "schema_version": ROADMAP_SCHEMA_VERSION,
            "updated_at": data.get("updated_at") or datetime.now(timezone.utc).isoformat(),
            "items": merged + custom,
        }
        return payload

    def _ensure_file(self):
        if not self.path.exists():
            self._save(self._default_payload())
            return
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
        except Exception:
            raw = {}
        merged = self._merge_defaults(raw)
        if raw != merged:
            merged["updated_at"] = datetime.now(timezone.utc).isoformat()
            self._save(merged)

    def _load(self):
        self._ensure_file()
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except Exception:
            data = self._default_payload()
            self._save(data)
        return self._merge_defaults(data)

    def _placeholder_index(self):
        index_path = self.blueprints_root / "index.json"
        if not index_path.exists():
            return {"schema_version": 1, "features": []}
        try:
            data = json.loads(index_path.read_text(encoding="utf-8"))
            if isinstance(data, dict) and isinstance(data.get("features"), list):
                return data
        except Exception:
            pass
        return {"schema_version": 1, "features": []}

    def _placeholder(self, feature_id):
        feature_id = str(feature_id or "").strip()
        if not feature_id:
            raise ValueError("feature_id is required")
        path = self.blueprints_root / feature_id / "feature.json"
        if not path.exists():
            raise KeyError(f"Unknown future feature placeholder: {feature_id}")
        return json.loads(path.read_text(encoding="utf-8"))

    def tools(self):
        return [
            {
                "name": "roadmap_status",
                "description": "Return Apollo's internal development roadmap.",
                "parameters": {"type": "object", "properties": {}},
            },
            {
                "name": "update_roadmap_item",
                "description": "Update the status or summary of one roadmap milestone.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "id": {"type": "string"},
                        "version": {"type": "string"},
                        "status": {"type": "string"},
                        "summary": {"type": "string"},
                    }
                },
            },
            {
                "name": "feature_placeholders",
                "description": "List machine-readable placeholders for planned Apollo features.",
                "parameters": {"type": "object", "properties": {}},
            },
            {
                "name": "feature_placeholder",
                "description": "Read one planned feature blueprint.",
                "parameters": {
                    "type": "object",
                    "properties": {"feature_id": {"type": "string"}},
                    "required": ["feature_id"],
                },
            },
        ]

    def run(self, action, arguments):
        arguments = arguments or {}

        if action == "roadmap_status":
            data = self._load()
            data["placeholder_count"] = len(
                self._placeholder_index().get("features", [])
            )
            return data

        if action == "feature_placeholders":
            return self._placeholder_index()

        if action == "feature_placeholder":
            return self._placeholder(arguments.get("feature_id"))

        if action == "update_roadmap_item":
            item_id = str(arguments.get("id", "")).strip()
            version = str(arguments.get("version", "")).strip()
            if not item_id and not version:
                raise ValueError("id or version is required")

            data = self._load()
            for item in data["items"]:
                matches = (
                    (item_id and str(item.get("id")) == item_id)
                    or (version and str(item.get("version")) == version)
                )
                if not matches:
                    continue

                if str(arguments.get("status", "")).strip():
                    item["status"] = str(arguments["status"]).strip()
                if str(arguments.get("summary", "")).strip():
                    item["summary"] = str(arguments["summary"]).strip()

                data["updated_at"] = datetime.now(timezone.utc).isoformat()
                self._save(data)
                return {
                    "updated": True,
                    "id": item.get("id"),
                    "version": item.get("version"),
                }

            raise KeyError("Unknown roadmap milestone.")

        raise KeyError(action)

    def self_test(self):
        data = self._load()
        ids = {str(item.get("id")) for item in data.get("items", [])}
        return (
            "image_core" in ids
            and "compute_broker" in ids
            and "apollo_os_preview" in ids
            and len(self._placeholder_index().get("features", [])) >= 20
        )

    def build_ui(self, parent=None, ui_context=None):
        from PySide6.QtWidgets import (
            QWidget, QVBoxLayout, QHBoxLayout, QLabel, QScrollArea,
            QFrame, QPushButton
        )

        page = QWidget(parent)
        root = QVBoxLayout(page)
        root.setContentsMargins(18, 18, 18, 18)
        root.setSpacing(12)

        title = QLabel("Apollo Roadmap")
        title.setStyleSheet("font-size: 24px; font-weight: 700;")
        root.addWidget(title)

        subtitle = QLabel(
            "Internal build plan and future-feature blueprints. Pin this app "
            "to the Hub whenever you want the roadmap visible from Home."
        )
        subtitle.setWordWrap(True)
        root.addWidget(subtitle)

        controls = QHBoxLayout()
        refresh = QPushButton("Refresh Roadmap")
        placeholder_count = QLabel("")
        controls.addWidget(refresh)
        controls.addWidget(placeholder_count)
        controls.addStretch(1)
        root.addLayout(controls)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        host = QWidget()
        body = QVBoxLayout(host)
        body.setSpacing(8)

        def rebuild():
            while body.count():
                item = body.takeAt(0)
                widget = item.widget()
                if widget is not None:
                    widget.deleteLater()

            data = self._load()
            count = len(self._placeholder_index().get("features", []))
            placeholder_count.setText(f"{count} future blueprints ready")

            for entry in data["items"]:
                card = QFrame()
                card.setFrameShape(QFrame.Shape.StyledPanel)
                card_layout = QVBoxLayout(card)

                top = QHBoxLayout()
                version = QLabel(str(entry.get("version", "")))
                version.setStyleSheet("font-weight: 700;")
                name = QLabel(str(entry.get("title", "")))
                name.setStyleSheet("font-weight: 700;")
                category = QLabel(str(entry.get("category", "")))
                status = QLabel(str(entry.get("status", "")).upper())

                top.addWidget(version)
                top.addWidget(name, 1)
                top.addWidget(category)
                top.addWidget(status)
                card_layout.addLayout(top)

                summary = QLabel(str(entry.get("summary", "")))
                summary.setWordWrap(True)
                card_layout.addWidget(summary)
                body.addWidget(card)

            body.addStretch(1)

        refresh.clicked.connect(rebuild)
        scroll.setWidget(host)
        root.addWidget(scroll, 1)
        rebuild()
        return page
