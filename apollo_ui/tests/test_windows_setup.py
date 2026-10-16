"""Offline structural contract for Apollo's simplified Windows setup commands.

The live Windows job runs the install/uninstall smoke test.
"""
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
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

    def test_optional_foundry_science_installs_only_in_venv_after_consent(self):
        script = read("Setup/16_INSTALL_FOUNDRY_SCIENCE.bat")
        self.assertIn("choice /C YN", script)
        self.assertIn(".venv", script)
        self.assertIn("sys.prefix != sys.base_prefix", script)
        self.assertLess(script.index("choice /C YN"), script.index("-m pip install"))
        self.assertIn("--only-binary=:all:", script)
        self.assertNotIn("pip install --user", script)

    def test_foundry_preflight_is_read_only_and_uses_venv(self):
        script = read("Setup/15_CHECK_FOUNDRY_PREREQUISITES.bat")
        self.assertIn(".venv\\Scripts\\python.exe", script)
        self.assertIn("apollo_foundry_preflight.py", script)
        self.assertNotIn("winget install", script)
        self.assertNotIn("docker build", script)

    def test_docker_desktop_setup_requires_explicit_consent(self):
        installer = read("Setup/14_INSTALL_DOCKER_DESKTOP.bat")
        sandbox = read("Setup/09_SETUP_FOUNDRY_SANDBOX.bat")
        helper = read("Setup/Docker_Foundry_Setup.ps1")
        for script in (installer, sandbox):
            self.assertIn("Docker_Foundry_Setup.ps1", script)
            self.assertIn("pause >nul", script)
            self.assertIn("set \"RESULT=%ERRORLEVEL%\"", script)
            self.assertIn("if not exist \"%HELPER%\"", script)
            self.assertNotIn("rmdir /S /Q", script)
        self.assertIn("-Action InstallDocker", installer)
        self.assertIn("-Action BuildImage", sandbox)
        self.assertIn("Start-Transcript", helper)
        self.assertIn("Docker.DockerDesktop", helper)
        self.assertIn("Confirm-Action", helper)
        self.assertLess(helper.index("Confirm-Action 'Install Docker Desktop"),
                        helper.index(" install --id Docker.DockerDesktop"))
        self.assertLess(helper.index("Confirm-Action 'Build the trusted"),
                        helper.index("& $docker build "))
        self.assertIn("wsl --install --no-distribution", helper)
        self.assertNotIn("& wsl.exe --install", helper)
        self.assertIn("Get-WinEvent", helper)
        self.assertIn("Show-FailureLogs", helper)
        self.assertIn("--network=none", helper)
        self.assertIn("--read-only", helper)
        self.assertIn("APOLLO_SANDBOX_READY", helper)
        self.assertNotIn("docker system prune", helper)
        self.assertNotIn("wsl --unregister", helper)

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
