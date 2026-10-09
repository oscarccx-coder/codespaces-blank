"""Offline structural contract for Apollo's simplified Windows setup commands.

The live Windows job runs the install/uninstall smoke test.
"""
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parent
SUPPORTED = {
    "INSTALL_REQUIREMENTS.bat",
    "UNINSTALL_REQUIREMENTS.bat",
    "start_apollo_ui.bat",
    "start_apollo_safe_mode.bat",
    "UPDATE_APOLLO_CODE.bat",
    "install_xtts_v2.bat",
    "build_apollo_exe_safer.bat",
}


def read(name):
    return (ROOT / name).read_text(encoding="utf-8").replace("\r\n", "\n")


class WindowsSetupTests(unittest.TestCase):
    def test_only_supported_entrypoints_exist(self):
        current = {p.name for p in ROOT.glob("*.bat")}
        self.assertEqual(current, SUPPORTED)

    def test_core_install_is_local_and_checked(self):
        script = read("INSTALL_REQUIREMENTS.bat")
        for marker in (
            ".venv\\Scripts\\python.exe",
            " -m venv ",
            '"%VENV_PY%" -m pip install -r',
            '"%VENV_PY%" -m pip check',
            'assert not (sys.prefix == sys.base_prefix)',
            'PIP_REQUIRE_VIRTUALENV=true',
        ):
            self.assertIn(marker, script)
        self.assertNotIn(' -m pip install --user', script)

    def test_uninstaller_targets_only_apollo_venv(self):
        script = read("UNINSTALL_REQUIREMENTS.bat")
        self.assertIn('if not exist "%~dp0.venv\\pyvenv.cfg"', script)
        self.assertIn('choice /C YN', script)
        self.assertIn('if /I "%~1"=="--yes"', script)
        self.assertIn('rmdir /S /Q "%~dp0.venv"', script)
        self.assertNotIn("pip uninstall", script)
        self.assertNotIn('rmdir /S /Q "%~dp0storage"', script)
        self.assertNotIn('rmdir /S /Q "%LOCALAPPDATA%"', script)

    def test_signed_updates_remove_only_obsolete_batch_files(self):
        from apollo_release import RETIRED_WINDOWS_LAUNCHERS
        from apollo_updater import safe_relative
        self.assertEqual(len(RETIRED_WINDOWS_LAUNCHERS), 11)
        self.assertTrue(all(name.endswith(".bat") for name in RETIRED_WINDOWS_LAUNCHERS))
        self.assertTrue(all("/" not in name and "\\\\" not in name for name in RETIRED_WINDOWS_LAUNCHERS))
        self.assertTrue(all(name not in SUPPORTED for name in RETIRED_WINDOWS_LAUNCHERS))
        self.assertTrue(all(not (ROOT / name).exists() for name in RETIRED_WINDOWS_LAUNCHERS))
        for name in RETIRED_WINDOWS_LAUNCHERS:
            self.assertEqual(str(safe_relative(name)), name)

    def test_launch_and_xtts_use_same_python(self):
        launcher = read("start_apollo_ui.bat")
        xtts = read("install_xtts_v2.bat")
        safe = read("start_apollo_safe_mode.bat")
        self.assertIn('set "PYTHON_EXE=%~dp0.venv\\Scripts\\python.exe"', launcher)
        self.assertIn('set "PYTHON_EXE=%APOLLO_DIR%\\.venv\\Scripts\\python.exe"', xtts)
        self.assertIn('assert not (sys.prefix == sys.base_prefix)', xtts)
        self.assertNotIn('rmdir /S /Q "%XTTS_TARGET%"', xtts)
        self.assertNotIn(" /MOVE ", xtts)
        self.assertIn('call "%~dp0start_apollo_ui.bat"', safe)


if __name__ == "__main__":
    unittest.main()
