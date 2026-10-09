"""Voice Imprint profile rename/order/archive regressions, including active routing."""
import json
import tempfile
import unittest
from pathlib import Path

from apollo_voice_profiles import VoiceProfileLibrary
from modules.voice_imprint_trainer.module import Module


def profile(root, name, pid):
    folder = Path(root) / "profiles" / pid
    folder.mkdir(parents=True)
    (folder / "profile.json").write_text(json.dumps({
        "id": pid, "name": name, "created_at": "2026-10-01",
        "signature_trained": False,
    }), encoding="utf-8")
    (folder / "original_recording.wav").write_bytes(b"private, recoverable recording")
    return folder


class VoiceManagementTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.base = Path(self.temporary.name)
        self.module = Module({"base_dir": self.base, "validation": True})
        self.first = profile(self.module.storage, "First Voice", "first")
        self.second = profile(self.module.storage, "Second Voice", "second")

    def test_names_change_without_moving_or_overwriting_voice_assets(self):
        result = self.module.rename_profile_from_ui("first", " New Favourite ")
        self.assertEqual(result["name"], "New Favourite")
        saved = json.loads((self.first / "profile.json").read_text(encoding="utf-8"))
        self.assertEqual(saved["id"], "first")
        self.assertEqual(saved["name"], "New Favourite")
        self.assertEqual((self.first / "original_recording.wav").read_bytes(),
                         b"private, recoverable recording")
        self.assertEqual([p["id"] for p in self.module.run("list_profiles", {})["profiles"]],
                         ["first", "second"])

    def test_renaming_active_voice_updates_apollo_default_metadata(self):
        self.module._save_json(self.module.active_path, {
            "enabled": True, "profile_id": "first", "profile_name": "First Voice",
        })
        self.module.rename_profile_from_ui("first", "Apollo Professor")
        self.assertEqual(self.module._active()["profile_name"], "Apollo Professor")
        self.assertTrue(self.module._active()["enabled"])

    def test_move_order_persists_and_lists_in_requested_sequence(self):
        self.module.reorder_profiles_from_ui(["second", "first"])
        self.assertEqual([p["id"] for p in self.module.run("list_profiles", {})["profiles"]],
                         ["second", "first"])
        new_library = VoiceProfileLibrary(self.module.storage)
        self.assertEqual(new_library.ordered_ids(), ["second", "first"])

    def test_order_validation_rejects_loss_or_duplicates(self):
        for items in (["first"], ["first", "first"], ["second", "missing"]):
            with self.subTest(items=items), self.assertRaises(ValueError):
                self.module.reorder_profiles_from_ui(items)

    def test_deletion_archives_audio_instead_of_erasing_it(self):
        result = self.module.archive_profile_from_ui("first")
        self.assertTrue(result["archived"])
        self.assertFalse(self.first.exists())
        archived = Path(result["archive"])
        self.assertTrue(archived.is_relative_to(self.module.storage / "deleted_profiles"))
        self.assertEqual((archived / "original_recording.wav").read_bytes(),
                         b"private, recoverable recording")
        self.assertEqual(self.module.library.ids(), ["second"])

    def test_archiving_default_deactivates_voice(self):
        self.module._save_json(self.module.active_path, {
            "enabled": True, "profile_id": "first", "profile_name": "First Voice",
        })
        result = self.module.archive_profile_from_ui("first")
        self.assertTrue(result["deactivated"])
        self.assertFalse(self.module._active().get("enabled"))
        self.assertFalse(self.module._active().get("profile_id"))

    def test_refuse_delete_during_training(self):
        self.module._training_state["running"] = True
        with self.assertRaises(RuntimeError):
            self.module.archive_profile_from_ui("first")
        self.assertTrue(self.first.exists())

    def test_reject_traversal_and_names_with_control_characters(self):
        with self.assertRaises(ValueError):
            self.module.archive_profile_from_ui("../first")
        with self.assertRaises(ValueError):
            self.module.rename_profile_from_ui("first", "Bad\nName")
        self.assertTrue(self.first.exists())


if __name__ == "__main__":
    unittest.main()
