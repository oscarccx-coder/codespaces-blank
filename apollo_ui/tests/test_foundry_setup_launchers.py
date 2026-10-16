"""Regression checks for double-clickable Foundry Docker setup batches.

Windows integration tests use a fake Docker executable. No installers, pulls,
image builds or elevated commands are run on a test host.
"""
from __future__ import annotations

import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = (
    "14_INSTALL_DOCKER_DESKTOP.bat",
    "09_SETUP_FOUNDRY_SANDBOX.bat",
)

FAKE_DOCKER = r"""@echo off
if /I "%~1"=="info" (
  if /I "%FAKE_DOCKER_STATE%"=="up" (
    echo linux
    exit /b 0
  )
  if /I "%FAKE_DOCKER_STATE%"=="windows" (
    echo windows
    exit /b 0
  )
  echo Cannot connect to the Docker daemon 1>&2
  exit /b 1
)
if /I "%~1"=="image" (
  if /I "%FAKE_DOCKER_IMAGE%"=="yes" exit /b 0
  exit /b 1
)
echo Unexpected Docker command. 1>&2
exit /b 99
"""


class SetupStructuralTests(unittest.TestCase):
    def test_both_installers_end_with_visible_result_and_optional_pause(self):
        for name in SCRIPTS:
            with self.subTest(name=name):
                text = (ROOT / "Setup" / name).read_text(encoding="utf-8")
                self.assertIn("call :MAIN", text)
                self.assertIn('set "EXIT_CODE=%errorlevel%"', text)
                self.assertIn('if "%NO_PAUSE%"=="0"', text)
                self.assertIn("pause >nul", text)
                self.assertIn("echo [RESULT]", text)
                self.assertIn("SETUP_LOG", text)
                self.assertIn('"--check"', text)
                self.assertIn('"--no-pause"', text)
                self.assertIn('pushd "%APOLLO_ROOT%"', text)
                self.assertIn("if defined CI", text)
                self.assertNotIn("exit /b %ERRORLEVEL%", text)

    def test_build_still_requires_confirmation_and_uses_approved_image(self):
        text = (ROOT / "Setup" / "09_SETUP_FOUNDRY_SANDBOX.bat").read_text()
        self.assertIn("choice /C YN", text)
        self.assertLess(text.index("choice /C YN"), text.index('"build --progress=plain"') if '"build --progress=plain"' in text else text.index(" build --progress=plain"))
        self.assertIn("apollo-foundry-qt:phase1", text)
        self.assertIn("--pull", text)
        self.assertIn("foundry_sandbox\\Dockerfile", text)
        self.assertIn("if defined CI", text)

    def test_installer_cannot_use_winget_before_owner_choice(self):
        text = (ROOT / "Setup" / "14_INSTALL_DOCKER_DESKTOP.bat").read_text()
        self.assertIn("Docker.DockerDesktop", text)
        self.assertIn("wsl --install", text)
        self.assertLess(text.index("choice /C YN"), text.index("winget install"))
        self.assertIn("call :CHECK_ENGINE", text)
        self.assertIn("09_SETUP_FOUNDRY_SANDBOX.bat", text)


@unittest.skipUnless(os.name == "nt", "Windows CMD integration test")
class SetupCmdIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        base = Path(self.tmp.name)
        self.root = base / "Apollo Install (test space)" / "apollo_ui"
        setup = self.root / "Setup"
        setup.mkdir(parents=True)
        (self.root / "foundry_sandbox").mkdir()
        (self.root / "foundry_sandbox" / "Dockerfile").write_text("FROM scratch\n")
        for name in SCRIPTS:
            shutil.copyfile(ROOT / "Setup" / name, setup / name)
        mock_bin = base / "mock-bin"
        mock_bin.mkdir()
        (mock_bin / "docker.cmd").write_text(FAKE_DOCKER, encoding="ascii")
        self.env = dict(os.environ)
        self.env["CI"] = "1"
        self.env["PATH"] = str(mock_bin) + os.pathsep + self.env["PATH"]
        self.env["FAKE_DOCKER_STATE"] = "up"
        self.env["FAKE_DOCKER_IMAGE"] = "yes"
        self.workdir = base

    def run_installer(self, name, *options):
        path = self.root / "Setup" / name
        args = " ".join(options)
        command = f'call "{path}" {args}'
        return subprocess.run(
            ["cmd.exe", "/d", "/c", command],
            env=self.env, cwd=self.workdir, capture_output=True,
            text=True, timeout=20, check=False,
        )

    def test_both_check_modes_launch_from_different_directory_with_spaces(self):
        for name in SCRIPTS:
            with self.subTest(name=name):
                out = self.run_installer(name, "--check")
                self.assertEqual(out.returncode, 0, out.stdout + out.stderr)
                self.assertIn("[RESULT]", out.stdout)
                self.assertIn("Linux engine", out.stdout)

    def test_engine_not_running_prints_error_and_returns_failure(self):
        self.env["FAKE_DOCKER_STATE"] = "down"
        for name in SCRIPTS:
            with self.subTest(name=name):
                out = self.run_installer(name, "--check")
                self.assertNotEqual(out.returncode, 0, out.stdout)
                self.assertIn("engine", out.stdout.lower())
                self.assertIn("[LOG]", out.stdout)

    def test_wrong_container_mode_is_reported(self):
        self.env["FAKE_DOCKER_STATE"] = "windows"
        for name in SCRIPTS:
            with self.subTest(name=name):
                out = self.run_installer(name, "--check")
                self.assertNotEqual(out.returncode, 0)
                self.assertIn("Linux containers", out.stdout)

    def test_missing_image_is_not_reported_as_ready(self):
        self.env["FAKE_DOCKER_IMAGE"] = "no"
        out = self.run_installer("09_SETUP_FOUNDRY_SANDBOX.bat", "--check")
        self.assertEqual(out.returncode, 4, out.stdout + out.stderr)
        self.assertIn("not built", out.stdout)

    def test_missing_dockerfile_cannot_launch_a_build(self):
        (self.root / "foundry_sandbox" / "Dockerfile").unlink()
        out = self.run_installer("09_SETUP_FOUNDRY_SANDBOX.bat", "--check")
        self.assertEqual(out.returncode, 2, out.stdout + out.stderr)
        self.assertIn("Missing", out.stdout)


if __name__ == "__main__":
    unittest.main()
