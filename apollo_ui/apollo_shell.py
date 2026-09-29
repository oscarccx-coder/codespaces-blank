import json
import os
from datetime import datetime, timezone
from pathlib import Path


VALID_TILE_SIZES = {"small", "medium", "wide", "large", "custom"}
TILE_SPANS = {
    "small": (1, 1),
    "medium": (1, 2),
    "wide": (1, 3),
    "large": (2, 2),
}
HUB_COLUMNS = 4
MAX_TILE_ROW_SPAN = 4
MAX_TILE_COLUMN_SPAN = HUB_COLUMNS


def _clamp_int(value, minimum, maximum, default):
    try:
        value = int(value)
    except (TypeError, ValueError):
        value = default
    return max(minimum, min(maximum, value))


def _size_from_span(row_span, col_span):
    for name, spans in TILE_SPANS.items():
        if (row_span, col_span) == spans:
            return name
    return "custom"


CORE_APPS = [
    {
        "app_id": "core.chat",
        "title": "Chat",
        "description": "Talk to Apollo and continue your work.",
        "glyph": "▣",
        "kind": "core",
        "target": "Chat",
    },
    {
        "app_id": "core.medical",
        "title": "Medical",
        "description": "Medical information and health tools with Apollo guardrails.",
        "glyph": "✚",
        "kind": "core",
        "target": "Medical",
    },
    {
        "app_id": "core.train",
        "title": "Train / Learn",
        "description": "Teach Apollo facts, corrections and preferred answers.",
        "glyph": "◈",
        "kind": "core",
        "target": "Train",
    },
    {
        "app_id": "core.web",
        "title": "Web",
        "description": "Research and inspect web sources.",
        "glyph": "◎",
        "kind": "core",
        "target": "Web",
    },
    {
        "app_id": "core.workshop",
        "title": "Workshop",
        "description": "Build, inspect and improve local software projects.",
        "glyph": "</>",
        "kind": "core",
        "target": "Coding",
    },
    {
        "app_id": "core.modules",
        "title": "Modules",
        "description": "Install, validate and manage Apollo capabilities.",
        "glyph": "◇",
        "kind": "core",
        "target": "Modules",
    },
    {
        "app_id": "core.system",
        "title": "System",
        "description": "Runtime, GPU and system health information.",
        "glyph": "▤",
        "kind": "core",
        "target": "System",
    },
    {
        "app_id": "core.memory",
        "title": "Memory",
        "description": "Review Apollo's persistent memory and recall.",
        "glyph": "◉",
        "kind": "core",
        "target": "Memory",
    },
    {
        "app_id": "core.settings",
        "title": "Settings",
        "description": "Configure Apollo, apps and patch information.",
        "glyph": "⚙",
        "kind": "core",
        "target": "Settings",
    },
]


DEFAULT_LAYOUT = [
    {"app_id": "core.chat", "size": "small", "section": "Main"},
    {"app_id": "core.workshop", "size": "medium", "section": "Main"},
    {"app_id": "module.file_manager", "size": "medium", "section": "Main"},
    {"app_id": "core.medical", "size": "small", "section": "Main"},
    {"app_id": "core.memory", "size": "small", "section": "System"},
    {"app_id": "core.system", "size": "small", "section": "System"},
    {"app_id": "core.modules", "size": "small", "section": "System"},
    {"app_id": "module.neural_visualizer", "size": "medium", "section": "System"},
]


def utc_now():
    return datetime.now(timezone.utc).isoformat()


def _normalise_section(value):
    value = " ".join(str(value or "Main").split()).strip()
    return value[:48] or "Main"


def _normalise_item(item, order):
    if not isinstance(item, dict):
        return None
    app_id = str(item.get("app_id", "")).strip()
    if not app_id:
        return None

    requested_size = str(item.get("size", "medium")).lower().strip()
    fallback_span = TILE_SPANS.get(requested_size, TILE_SPANS["medium"])
    row_span = _clamp_int(
        item.get("row_span", fallback_span[0]),
        1,
        MAX_TILE_ROW_SPAN,
        fallback_span[0],
    )
    col_span = _clamp_int(
        item.get("col_span", fallback_span[1]),
        1,
        MAX_TILE_COLUMN_SPAN,
        fallback_span[1],
    )

    grid_row = item.get("grid_row")
    grid_col = item.get("grid_col")
    try:
        grid_row = int(grid_row) if grid_row is not None else None
    except (TypeError, ValueError):
        grid_row = None
    try:
        grid_col = int(grid_col) if grid_col is not None else None
    except (TypeError, ValueError):
        grid_col = None

    if grid_row is not None:
        grid_row = max(0, min(100, grid_row))
    if grid_col is not None:
        grid_col = max(0, min(HUB_COLUMNS - 1, grid_col))
        grid_col = min(grid_col, HUB_COLUMNS - col_span)

    return {
        "app_id": app_id,
        "size": _size_from_span(row_span, col_span),
        "section": _normalise_section(item.get("section", "Main")),
        "order": int(order),
        "grid_row": grid_row,
        "grid_col": grid_col,
        "row_span": row_span,
        "col_span": col_span,
    }


class ShellStateStore:
    """Crash-resistant persistent state for Apollo's OS-style shell.

    The shell stores logical app order/size/section rather than pixel positions,
    so layout can reflow across resolutions without destroying the user's setup.
    """

    def __init__(self, base_dir):
        self.base_dir = Path(base_dir).resolve()
        self.shell_dir = self.base_dir / "storage" / "state" / "shell"
        self.layout_path = self.shell_dir / "hub_layout.json"
        self.shell_dir.mkdir(parents=True, exist_ok=True)
        self._state = self._load()

    @staticmethod
    def default_state():
        items = []
        for index, item in enumerate(DEFAULT_LAYOUT):
            normal = _normalise_item(item, index)
            if normal:
                items.append(normal)
        return {
            "version": 2,
            "updated_at": utc_now(),
            "items": items,
        }

    def _load(self):
        if not self.layout_path.exists():
            state = self.default_state()
            self._write(state)
            return state

        try:
            raw = json.loads(self.layout_path.read_text(encoding="utf-8"))
            if not isinstance(raw, dict):
                raise ValueError("hub_layout root must be an object")
            raw_items = raw.get("items", [])
            if not isinstance(raw_items, list):
                raise ValueError("hub_layout items must be a list")
            items = []
            seen = set()
            for item in sorted(
                raw_items,
                key=lambda row: int(row.get("order", 0)) if isinstance(row, dict) else 0,
            ):
                normal = _normalise_item(item, len(items))
                if not normal or normal["app_id"] in seen:
                    continue
                seen.add(normal["app_id"])
                items.append(normal)
            return {
                "version": 2,
                "updated_at": str(raw.get("updated_at") or utc_now()),
                "items": items,
            }
        except Exception:
            # Preserve the damaged state for diagnosis instead of deleting evidence.
            stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
            backup = self.layout_path.with_name(f"hub_layout.corrupt-{stamp}.json")
            try:
                self.layout_path.replace(backup)
            except Exception:
                pass
            state = self.default_state()
            self._write(state)
            return state

    def _write(self, state):
        self.shell_dir.mkdir(parents=True, exist_ok=True)
        state = dict(state)
        state["version"] = 2
        state["updated_at"] = utc_now()
        temp = self.layout_path.with_suffix(".json.tmp")
        temp.write_text(json.dumps(state, indent=2), encoding="utf-8")
        os.replace(temp, self.layout_path)
        state["updated_at"] = json.loads(self.layout_path.read_text(encoding="utf-8"))["updated_at"]
        self._state = state

    def state(self):
        return json.loads(json.dumps(self._state))

    def items(self):
        return [dict(item) for item in self._state.get("items", [])]

    def _commit_items(self, items):
        clean = []
        seen = set()
        for item in items:
            normal = _normalise_item(item, len(clean))
            if not normal or normal["app_id"] in seen:
                continue
            seen.add(normal["app_id"])
            clean.append(normal)
        self._write({"version": 2, "items": clean})
        return self.items()

    def get(self, app_id):
        app_id = str(app_id or "").strip()
        for item in self._state.get("items", []):
            if item.get("app_id") == app_id:
                return dict(item)
        return None

    def pin(self, app_id, size="medium", section="Main"):
        app_id = str(app_id or "").strip()
        if not app_id:
            raise ValueError("app_id is required")
        existing = self.get(app_id)
        if existing:
            return existing
        items = self.items()
        preset = size if size in TILE_SPANS else "medium"
        row_span, col_span = TILE_SPANS[preset]
        items.append({
            "app_id": app_id,
            "size": preset,
            "section": _normalise_section(section),
            "order": len(items),
            "grid_row": None,
            "grid_col": None,
            "row_span": row_span,
            "col_span": col_span,
        })
        self._commit_items(items)
        return self.get(app_id)

    def unpin(self, app_id):
        app_id = str(app_id or "").strip()
        before = self.items()
        after = [item for item in before if item.get("app_id") != app_id]
        changed = len(before) != len(after)
        if changed:
            self._commit_items(after)
        return changed

    def set_size(self, app_id, size):
        size = str(size or "").lower().strip()
        if size not in TILE_SPANS:
            raise ValueError("size must be small, medium, wide, or large")
        row_span, col_span = TILE_SPANS[size]
        items = self.items()
        changed = False
        for item in items:
            if item.get("app_id") == app_id:
                item["size"] = size
                item["row_span"] = row_span
                item["col_span"] = col_span
                if item.get("grid_col") is not None:
                    item["grid_col"] = min(int(item["grid_col"]), HUB_COLUMNS - col_span)
                changed = True
                break
        if not changed:
            raise KeyError(app_id)
        self._commit_items(items)
        return self.get(app_id)

    def set_section(self, app_id, section):
        section = _normalise_section(section)
        items = self.items()
        changed = False
        for item in items:
            if item.get("app_id") == app_id:
                item["section"] = section
                item["grid_row"] = None
                item["grid_col"] = None
                changed = True
                break
        if not changed:
            raise KeyError(app_id)
        self._commit_items(items)
        return self.get(app_id)

    def move(self, app_id, delta):
        delta = -1 if int(delta) < 0 else 1
        items = self.items()
        target = next((item for item in items if item.get("app_id") == app_id), None)
        if target is None:
            raise KeyError(app_id)
        section = target.get("section", "Main")
        section_indexes = [i for i, item in enumerate(items) if item.get("section") == section]
        position = section_indexes.index(items.index(target))
        new_position = position + delta
        if new_position < 0 or new_position >= len(section_indexes):
            return self.get(app_id)
        a = section_indexes[position]
        b = section_indexes[new_position]
        items[a], items[b] = items[b], items[a]
        for item in items:
            if item.get("section") == section:
                item["grid_row"] = None
                item["grid_col"] = None
        self._commit_items(items)
        return self.get(app_id)

    def place_resize(
        self,
        app_id,
        row,
        col,
        row_span=None,
        col_span=None,
        section=None,
        columns=HUB_COLUMNS,
    ):
        """Move/resize one Hub tile and repack collisions around it.

        The directly manipulated tile wins its requested rectangle. Other tiles in
        affected sections retain their preferred positions when possible and are
        otherwise moved to the next free grid cells. This makes drag/drop stable
        while guaranteeing that persisted layouts never overlap.
        """
        columns = max(1, min(HUB_COLUMNS, int(columns)))
        items = self.items()
        target = next((item for item in items if item.get("app_id") == app_id), None)
        if target is None:
            raise KeyError(app_id)

        source_section = target.get("section", "Main")
        destination_section = _normalise_section(section or source_section)
        row_span = _clamp_int(
            row_span if row_span is not None else target.get("row_span", 1),
            1,
            MAX_TILE_ROW_SPAN,
            1,
        )
        col_span = _clamp_int(
            col_span if col_span is not None else target.get("col_span", 1),
            1,
            min(MAX_TILE_COLUMN_SPAN, columns),
            1,
        )
        row = max(0, min(100, int(row)))
        col = max(0, min(columns - col_span, int(col)))

        target.update({
            "section": destination_section,
            "grid_row": row,
            "grid_col": col,
            "row_span": row_span,
            "col_span": col_span,
            "size": _size_from_span(row_span, col_span),
        })

        affected = {source_section, destination_section}
        for current_section in affected:
            section_items = [
                item for item in items
                if item.get("section", "Main") == current_section
            ]
            if not section_items:
                continue
            section_items.sort(key=lambda item: int(item.get("order", 0)))
            if current_section == destination_section:
                section_items = [target] + [
                    item for item in section_items
                    if item.get("app_id") != app_id
                ]

            packed = pack_tiles(section_items, columns)
            positions = {
                item["app_id"]: (grid_row, grid_col, rs, cs)
                for item, grid_row, grid_col, rs, cs in packed
            }
            for item in section_items:
                pos = positions[item["app_id"]]
                item["grid_row"], item["grid_col"], item["row_span"], item["col_span"] = pos
                item["size"] = _size_from_span(pos[2], pos[3])

        # Logical order now follows the visible grid within each section.
        section_order = []
        for item in items:
            sec = item.get("section", "Main")
            if sec not in section_order:
                section_order.append(sec)
        rebuilt = []
        for sec in section_order:
            rows = [item for item in items if item.get("section", "Main") == sec]
            rows.sort(key=lambda item: (
                int(item.get("grid_row") or 0),
                int(item.get("grid_col") or 0),
                int(item.get("order", 0)),
            ))
            rebuilt.extend(rows)

        self._commit_items(rebuilt)
        return self.get(app_id)

    def reset(self):
        state = self.default_state()
        self._write(state)
        return self.items()


class ApolloShell:
    """Runtime app registry + persistent custom Hub state.

    Core pages and module UIs are represented by the same app record. The shell
    does not own Qt widgets; MainWindow is the router/renderer.
    """

    def __init__(self, base_dir, module_manager):
        self.base_dir = Path(base_dir).resolve()
        self.module_manager = module_manager
        self.store = ShellStateStore(self.base_dir)

    def catalog(self):
        apps = []
        for row in CORE_APPS:
            item = dict(row)
            item.update({
                "available": True,
                "enabled": True,
                "installed": True,
                "module_id": None,
                "source": "core",
            })
            apps.append(item)

        # Use installed records, including disabled modules. That means Hub Manager
        # can display an app that is installed but currently disabled instead of
        # silently forgetting it.
        for summary in self.module_manager.list_modules():
            module_id = str(summary.get("id", "")).strip()
            if not module_id or summary.get("error"):
                continue
            record = self.module_manager.get_module(module_id)
            manifest = record.get("manifest", {}) if record else {}
            ui = manifest.get("ui", {}) if isinstance(manifest, dict) else {}
            if not isinstance(ui, dict) or not bool(ui.get("enabled")):
                continue
            enabled = bool(summary.get("enabled"))
            loaded = bool(summary.get("loaded"))
            instance = record.get("instance") if record else None
            renderer_ready = bool(instance is not None and hasattr(instance, "build_ui"))
            apps.append({
                "app_id": f"module.{module_id}",
                "title": str(ui.get("title") or manifest.get("name") or module_id),
                "description": str(manifest.get("description", "")),
                "glyph": "◫",
                "kind": "module",
                "target": module_id,
                "module_id": module_id,
                "source": "module",
                "installed": True,
                "enabled": enabled,
                "available": bool(enabled and loaded and renderer_ready),
                "placement": self.module_manager.get_ui_placement(module_id),
                "version": str(manifest.get("version", "?")),
            })

        return apps

    def app_map(self):
        return {app["app_id"]: app for app in self.catalog()}

    def app(self, app_id):
        return self.app_map().get(str(app_id or "").strip())

    def layout_items(self):
        return self.store.items()

    def is_pinned(self, app_id):
        return self.store.get(app_id) is not None

    def hub_items(self):
        catalog = self.app_map()
        output = []
        for layout in self.store.items():
            app = catalog.get(layout.get("app_id"))
            # Missing/uninstalled app records remain in storage for recovery but
            # are hidden from Home so the Hub never contains a dead launcher.
            if not app:
                continue
            row = dict(app)
            row.update(layout)
            output.append(row)
        return output

    def orphaned_items(self):
        catalog = self.app_map()
        return [
            dict(item)
            for item in self.store.items()
            if item.get("app_id") not in catalog
        ]

    def pin(self, app_id, size="medium", section="Main"):
        if self.app(app_id) is None:
            raise KeyError(f"Unknown app: {app_id}")
        return self.store.pin(app_id, size=size, section=section)

    def unpin(self, app_id):
        return self.store.unpin(app_id)

    def set_size(self, app_id, size):
        return self.store.set_size(app_id, size)

    def set_section(self, app_id, section):
        return self.store.set_section(app_id, section)

    def move(self, app_id, delta):
        return self.store.move(app_id, delta)

    def place_resize(self, app_id, row, col, row_span=None, col_span=None, section=None):
        return self.store.place_resize(
            app_id,
            row,
            col,
            row_span=row_span,
            col_span=col_span,
            section=section,
            columns=HUB_COLUMNS,
        )

    def reset_layout(self):
        return self.store.reset()

    def manager_rows(self):
        catalog = self.app_map()
        layout = {item["app_id"]: item for item in self.store.items()}
        rows = []
        for app_id, app in catalog.items():
            row = dict(app)
            pinned = layout.get(app_id)
            row["pinned"] = pinned is not None
            row["size"] = pinned.get("size") if pinned else "medium"
            row["section"] = pinned.get("section") if pinned else "Main"
            row["order"] = pinned.get("order") if pinned else 10**6
            row["grid_row"] = pinned.get("grid_row") if pinned else None
            row["grid_col"] = pinned.get("grid_col") if pinned else None
            row["row_span"] = pinned.get("row_span", 1) if pinned else 1
            row["col_span"] = pinned.get("col_span", 2) if pinned else 2
            rows.append(row)
        for missing in self.orphaned_items():
            rows.append({
                "app_id": missing["app_id"],
                "title": missing["app_id"],
                "description": "The app is no longer installed or could not be discovered.",
                "glyph": "?",
                "kind": "missing",
                "source": "missing",
                "installed": False,
                "enabled": False,
                "available": False,
                "pinned": True,
                "size": missing.get("size", "medium"),
                "section": missing.get("section", "Main"),
                "order": missing.get("order", 10**6),
                "grid_row": missing.get("grid_row"),
                "grid_col": missing.get("grid_col"),
                "row_span": missing.get("row_span", 1),
                "col_span": missing.get("col_span", 2),
            })
        return sorted(
            rows,
            key=lambda row: (
                0 if row.get("pinned") else 1,
                int(row.get("order", 10**6)),
                str(row.get("title", "")).lower(),
                str(row.get("app_id", "")),
            ),
        )


def pack_tiles(items, columns=HUB_COLUMNS):
    """Pack logical Hub tiles without overlap, respecting preferred coordinates.

    Items with grid_row/grid_col attempt that exact persisted location first.
    Collisions or legacy items without coordinates fall back to first-fit packing.
    """
    columns = max(1, int(columns))
    occupied = set()
    output = []

    def fits(row, col, row_span, col_span):
        if row < 0 or col < 0 or col + col_span > columns:
            return False
        for rr in range(row, row + row_span):
            for cc in range(col, col + col_span):
                if (rr, cc) in occupied:
                    return False
        return True

    def reserve(row, col, row_span, col_span):
        for rr in range(row, row + row_span):
            for cc in range(col, col + col_span):
                occupied.add((rr, cc))

    for item in items:
        size = str(item.get("size", "medium")).lower()
        fallback_row, fallback_col = TILE_SPANS.get(size, TILE_SPANS["medium"])
        row_span = _clamp_int(item.get("row_span", fallback_row), 1, MAX_TILE_ROW_SPAN, fallback_row)
        col_span = _clamp_int(item.get("col_span", fallback_col), 1, min(columns, MAX_TILE_COLUMN_SPAN), fallback_col)

        preferred_row = item.get("grid_row")
        preferred_col = item.get("grid_col")
        try:
            preferred_row = int(preferred_row) if preferred_row is not None else None
            preferred_col = int(preferred_col) if preferred_col is not None else None
        except (TypeError, ValueError):
            preferred_row = preferred_col = None

        if (
            preferred_row is not None
            and preferred_col is not None
            and fits(preferred_row, preferred_col, row_span, col_span)
        ):
            reserve(preferred_row, preferred_col, row_span, col_span)
            output.append((item, preferred_row, preferred_col, row_span, col_span))
            continue

        row = 0
        placed = False
        while not placed:
            for col in range(columns):
                if fits(row, col, row_span, col_span):
                    reserve(row, col, row_span, col_span)
                    output.append((item, row, col, row_span, col_span))
                    placed = True
                    break
            if not placed:
                row += 1
    return output
