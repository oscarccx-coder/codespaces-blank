import json
import tempfile
from pathlib import Path

from apollo_shell import ApolloShell, ShellStateStore, pack_tiles


class FakeManager:
    def __init__(self):
        class UIInstance:
            def build_ui(self):
                return None
        self.records = {
            "file_manager": {
                "manifest": {
                    "id": "file_manager",
                    "name": "Files",
                    "version": "1.1",
                    "description": "File manager",
                    "ui": {"enabled": True, "title": "Files", "default_placement": "sidebar"},
                },
                "enabled": True,
                "instance": UIInstance(),
            },
            "duplicate_a": {
                "manifest": {
                    "id": "duplicate_a",
                    "name": "Same Name",
                    "version": "1",
                    "description": "A",
                    "ui": {"enabled": True, "title": "Same Name", "default_placement": "apps"},
                },
                "enabled": True,
                "instance": UIInstance(),
            },
            "duplicate_b": {
                "manifest": {
                    "id": "duplicate_b",
                    "name": "Same Name",
                    "version": "1",
                    "description": "B",
                    "ui": {"enabled": True, "title": "Same Name", "default_placement": "apps"},
                },
                "enabled": False,
                "instance": None,
            },
        }

    def list_modules(self):
        rows = []
        for module_id, record in self.records.items():
            rows.append({
                "id": module_id,
                "enabled": record["enabled"],
                "loaded": record["instance"] is not None,
            })
        return rows

    def get_module(self, module_id):
        return self.records.get(module_id)

    def get_ui_placement(self, module_id):
        return self.records[module_id]["manifest"]["ui"].get("default_placement", "apps")


def assert_no_overlap(packed, columns=4):
    used = set()
    for item, row, col, rs, cs in packed:
        assert 0 <= col < columns
        assert col + cs <= columns
        for rr in range(row, row + rs):
            for cc in range(col, col + cs):
                assert (rr, cc) not in used, (item, rr, cc)
                used.add((rr, cc))


def main():
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        manager = FakeManager()
        shell = ApolloShell(root, manager)

        catalog = shell.app_map()
        assert "core.chat" in catalog
        assert "module.file_manager" in catalog
        assert "module.duplicate_a" in catalog
        assert "module.duplicate_b" in catalog
        assert catalog["module.duplicate_a"]["title"] == catalog["module.duplicate_b"]["title"]
        assert catalog["module.duplicate_a"]["app_id"] != catalog["module.duplicate_b"]["app_id"]
        assert catalog["module.duplicate_b"]["available"] is False

        # User layout actions persist across a fresh shell instance.
        shell.pin("module.duplicate_a", "large", "Projects")
        assert shell.is_pinned("module.duplicate_a")
        shell.set_size("module.duplicate_a", "wide")
        shell.set_section("module.duplicate_a", "Physics")
        before = shell.store.get("module.duplicate_a")
        assert before["size"] == "wide"
        assert before["section"] == "Physics"

        shell2 = ApolloShell(root, manager)
        restored = shell2.store.get("module.duplicate_a")
        assert restored["size"] == "wide"
        assert restored["section"] == "Physics"

        # Missing apps never render on Home but remain recoverable in layout state.
        shell2.store.pin("module.removed_app", "small", "Main")
        assert shell2.store.get("module.removed_app") is not None
        assert all(row["app_id"] != "module.removed_app" for row in shell2.hub_items())
        assert any(row["app_id"] == "module.removed_app" for row in shell2.orphaned_items())

        # Tile packer obeys spans and never overlaps.
        sample = [
            {"app_id": "a", "size": "small"},
            {"app_id": "b", "size": "medium"},
            {"app_id": "c", "size": "wide"},
            {"app_id": "d", "size": "large"},
            {"app_id": "e", "size": "small"},
        ]
        packed = pack_tiles(sample, 4)
        assert len(packed) == len(sample)
        assert_no_overlap(packed, 4)

        # Direct manipulation: arbitrary grid spans persist, collisions reflow,
        # and exact drop coordinates survive a restart.
        shell2.pin("module.duplicate_a", "medium", "Physics") if not shell2.is_pinned("module.duplicate_a") else None
        placed = shell2.place_resize(
            "module.duplicate_a",
            0,
            0,
            row_span=3,
            col_span=4,
            section="Physics",
        )
        assert placed["row_span"] == 3
        assert placed["col_span"] == 4
        assert placed["size"] == "custom"
        assert placed["grid_row"] == 0
        assert placed["grid_col"] == 0

        shell3 = ApolloShell(root, manager)
        restored_direct = shell3.store.get("module.duplicate_a")
        assert restored_direct["row_span"] == 3
        assert restored_direct["col_span"] == 4
        assert restored_direct["grid_row"] == 0
        assert restored_direct["grid_col"] == 0

        # Cross-section drag is a layout operation only.
        moved = shell3.place_resize(
            "module.duplicate_a", 1, 0, row_span=2, col_span=2, section="Main"
        )
        assert moved["section"] == "Main"
        assert moved["row_span"] == 2 and moved["col_span"] == 2

        packed_direct = pack_tiles(shell3.hub_items(), 4)
        assert_no_overlap(packed_direct, 4)

        # Version-1 style records without explicit spans migrate safely.
        legacy = {
            "version": 1,
            "items": [
                {"app_id": "core.chat", "size": "wide", "section": "Main", "order": 0}
            ],
        }
        layout_path = root / "storage" / "state" / "shell" / "hub_layout.json"
        layout_path.write_text(json.dumps(legacy), encoding="utf-8")
        migrated = ShellStateStore(root)
        migrated_item = migrated.get("core.chat")
        assert migrated_item["row_span"] == 1
        assert migrated_item["col_span"] == 3

        # Corrupt layout is backed up and replaced with a safe default.
        path = root / "storage" / "state" / "shell" / "hub_layout.json"
        path.write_text("{ this is not json", encoding="utf-8")
        recovered = ShellStateStore(root)
        assert recovered.items()
        backups = list(path.parent.glob("hub_layout.corrupt-*.json"))
        assert backups, "corrupt layout should be preserved as a backup"

        # Unpin is layout-only and does not affect the app registry.
        assert shell2.unpin("module.duplicate_a") is True
        assert shell2.app("module.duplicate_a") is not None

    print("Apollo Shell tests passed")


if __name__ == "__main__":
    main()
