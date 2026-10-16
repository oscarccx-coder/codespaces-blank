"""End-to-end Windows BAT Git updater tests with a local throwaway bare remote.

No real GitHub access, no user's Apollo files, and no live application update.
"""
from __future__ import annotations

import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
MAIN_BAT = ROOT / "Setup" / "13_UPDATE_GIT_MAIN.bat"
SETUP_BAT = ROOT / "Setup" / "03_UPDATE_APOLLO.bat"
LEGACY_BAT = ROOT / "UPDATE_APOLLO_CODE.bat"


class EntryPointTests(unittest.TestCase):
    def test_all_git_entrypoints_have_a_safe_implementation(self):
        setup = SETUP_BAT.read_text(encoding="utf-8")
        legacy = LEGACY_BAT.read_text(encoding="utf-8")
        main = MAIN_BAT.read_text(encoding="utf-8")
        self.assertIn("UPDATE_APOLLO_CODE.bat", setup)
        self.assertIn("13_UPDATE_GIT_MAIN.bat", legacy)
        self.assertIn('if /I "%~1"=="--check"', main)
        self.assertIn('if /I "%~1"=="--no-pause"', main)
        self.assertIn("git status --porcelain", main)
        self.assertIn("git merge --ff-only FETCH_HEAD", main)
        self.assertIn("git branch --show-current", main)
        self.assertIn("pause >nul", main)
        self.assertIn("[LOG]", main)


@unittest.skipUnless(os.name == "nt" and shutil.which("git"), "Windows + Git required")
class WindowsMainGitUpdateTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="Apollo updater test (spaces) ")
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.bare = self.root / "local-origin.git"
        self.author = self.root / "source author"
        self.install = self.root / "Apollo clone (test)"
        self._git("init", "--bare", "--initial-branch=main", str(self.bare))
        self._git("clone", str(self.bare), str(self.author))
        (self.author / "apollo_ui" / "Setup").mkdir(parents=True)
        shutil.copyfile(MAIN_BAT, self.author / "apollo_ui" / "Setup" / MAIN_BAT.name)
        shutil.copyfile(SETUP_BAT, self.author / "apollo_ui" / "Setup" / SETUP_BAT.name)
        shutil.copyfile(LEGACY_BAT, self.author / "apollo_ui" / LEGACY_BAT.name)
        (self.author / "README.md").write_text("version one\n", encoding="utf-8")
        self._git("-C", str(self.author), "add", ".")
        self._git("-C", str(self.author), "-c", "user.name=Apollo CI",
                  "-c", "user.email=apollo-ci@example.invalid",
                  "commit", "-m", "initial version")
        self._git("-C", str(self.author), "push", "-u", "origin", "main")
        self._git("clone", str(self.bare), str(self.install))
        self.env = os.environ.copy()
        self.env["CI"] = "1"
        self.wrapper = self.root / "invoke.bat"

    def _git(self, *args):
        return subprocess.run(
            ["git", *args], capture_output=True, text=True,
            cwd=self.root, timeout=25, check=True,
        )

    def invoke(self, relative_path="apollo_ui/Setup/13_UPDATE_GIT_MAIN.bat", arg="--no-pause"):
        # Actual CALL from a simple wrapper avoids CMD /c nested quoting
        # bugs when paths contain both whitespace and parentheses.
        actual = self.install / Path(relative_path)
        self.wrapper.write_text(
            '@echo off\n' +
            f'call "{actual}" {arg}\n' +
            "exit /b %errorlevel%\n", encoding="utf-8",
        )
        return subprocess.run(
            ["cmd.exe", "/d", "/c", "invoke.bat"],
            cwd=self.root, env=self.env, capture_output=True,
            text=True, timeout=35, check=False,
        )

    def _make_remote_update(self):
        (self.author / "README.md").write_text("version two\n", encoding="utf-8")
        self._git("-C", str(self.author), "add", "README.md")
        self._git("-C", str(self.author), "-c", "user.name=Apollo CI",
                  "-c", "user.email=apollo-ci@example.invalid",
                  "commit", "-m", "new source")
        self._git("-C", str(self.author), "push", "origin", "main")

    def test_real_local_origin_fast_forward_from_numbered_setup(self):
        self._make_remote_update()
        result = self.invoke("apollo_ui/Setup/03_UPDATE_APOLLO.bat")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("[OK] Git main update completed.", result.stdout)
        self.assertEqual((self.install / "README.md").read_text(), "version two\n")
        again = self.invoke()
        self.assertEqual(again.returncode, 0, again.stdout + again.stderr)
        self.assertIn("[OK]", again.stdout)

    def test_read_only_check_does_not_fetch_remote_changes(self):
        self._make_remote_update()
        before = self._git("-C", str(self.install), "rev-parse", "HEAD").stdout.strip()
        test = self.invoke(arg="--check")
        after = self._git("-C", str(self.install), "rev-parse", "HEAD").stdout.strip()
        self.assertEqual(test.returncode, 0, test.stdout + test.stderr)
        self.assertIn("Read-only preflight", test.stdout)
        self.assertEqual(before, after)
        self.assertEqual((self.install / "README.md").read_text(), "version one\n")

    def test_uncommitted_change_refuses_update_and_preserves_content(self):
        self._make_remote_update()
        (self.install / "README.md").write_text("local edit\n", encoding="utf-8")
        result = self.invoke()
        self.assertEqual(result.returncode, 2, result.stdout + result.stderr)
        self.assertIn("[STOPPED]", result.stdout)
        self.assertEqual((self.install / "README.md").read_text(), "local edit\n")

    def test_untracked_file_refuses_update(self):
        self._make_remote_update()
        (self.install / "new private note.txt").write_text("private")
        result = self.invoke()
        self.assertEqual(result.returncode, 2, result.stdout + result.stderr)
        self.assertEqual((self.install / "new private note.txt").read_text(), "private")
        self.assertEqual((self.install / "README.md").read_text(), "version one\n")

    def test_feature_branch_refused_instead_of_cross_merging_main(self):
        self._make_remote_update()
        self._git("-C", str(self.install), "checkout", "-b", "feature/testing")
        result = self.invoke()
        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assertIn("not main", result.stdout)
        self.assertEqual((self.install / "README.md").read_text(), "version one\n")

    def test_legacy_launcher_runs_the_same_implementation(self):
        self._make_remote_update()
        result = self.invoke("apollo_ui/UPDATE_APOLLO_CODE.bat")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual((self.install / "README.md").read_text(), "version two\n")


if __name__ == "__main__":
    unittest.main()
