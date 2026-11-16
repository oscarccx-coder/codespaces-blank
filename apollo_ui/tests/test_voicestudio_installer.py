"""VoiceStudio guided setup tests; no real installer/model/code execution."""
from __future__ import annotations
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

from apollo_voicestudio_installer import diagnose, guided_install, install_missing_prerequisites


class GuidedInstallerTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="Apollo VoiceStudio fixture ")
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.source = self.root / "VoiceStudio-main"
        (self.source / "scripts").mkdir(parents=True)
        (self.source / "backend").mkdir()
        (self.source / "backend" / "main.py").write_text("pass")
        (self.source / "scripts" / "dev-backend.mjs").write_text("")
        (self.source / "package.json").write_text(json.dumps({
            "name": "omnivoice-studio-monorepo",
            "scripts": {"dev:api": "bun scripts/dev-backend.mjs"},
        }))

    def test_diagnose_only_checks_existing_downloaded_checkout(self):
        with patch("apollo_voicestudio_installer.locate_tool",
                   side_effect=lambda name: "/fake/" + name):
            state = diagnose(self.source)
        self.assertEqual(state["checkout"], str(self.source.resolve()))
        self.assertFalse(state["backend_venv"])
        self.assertFalse(state["prepared"])
        self.assertEqual(state["missing"], [])
        with self.assertRaises(ValueError):
            diagnose(self.root)

    def test_install_needs_explicit_approval(self):
        with patch("apollo_voicestudio_installer.prepare_backend") as runner:
            with self.assertRaises(PermissionError):
                guided_install(self.source, self.root / "logs")
            with self.assertRaises(PermissionError):
                install_missing_prerequisites(self.source, self.root / "logs")
            runner.assert_not_called()

    def test_owner_approved_runtime_stays_in_selected_source(self):
        with patch("apollo_voicestudio_installer.locate_tool",
                   side_effect=lambda name: "/fake/" + name), \
             patch("apollo_voicestudio_installer.prepare_backend",
                   return_value={"ok": True, "prepared": True,
                                 "checkout": str(self.source),
                                 "log": str(self.root / "logs/setup.log")}) as runner:
            outcome = guided_install(self.source, self.root / "logs",
                                     approved=True, install_missing=False)
        self.assertTrue(outcome["prepared"])
        self.assertEqual(outcome["installed_tools"], [])
        runner.assert_called_once_with(self.source, self.root / "logs")

    def test_winget_uses_exact_ids_and_never_shell_execution(self):
        installed = set()
        def locate(name):
            return "/fake/" + name if name in installed else ""
        def run(command, **kwargs):
            installed.add({"Oven-sh.Bun": "bun", "astral-sh.uv": "uv"}[command[3]])
            self.assertNotIn("shell", kwargs)
            self.assertEqual(command[0], "winget")
            self.assertIn("--exact", command)
            return Mock(returncode=0)
        with patch("apollo_voicestudio_installer.sys.platform", "win32"), \
             patch("apollo_voicestudio_installer.shutil.which",
                   side_effect=lambda name: "winget" if name == "winget" else None), \
             patch("apollo_voicestudio_installer.locate_tool", side_effect=locate), \
             patch("apollo_voicestudio_installer.subprocess.run",
                   side_effect=run) as commands:
            result = install_missing_prerequisites(self.source, self.root / "logs",
                                                   approved=True)
        self.assertEqual(result["installed"], ["bun", "uv"])
        self.assertEqual(commands.call_count, 2)

    def test_missing_dependency_refuses_unapproved_downloads(self):
        with patch("apollo_voicestudio_installer.locate_tool", return_value=""), \
             patch("apollo_voicestudio_installer.prepare_backend") as runner:
            with self.assertRaises(RuntimeError):
                guided_install(self.source, self.root / "logs",
                               approved=True, install_missing=False)
            runner.assert_not_called()


if __name__ == "__main__":
    unittest.main()
