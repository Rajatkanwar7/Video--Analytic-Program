"""Exercise the real batch-file discovery without installing application packages."""
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


@unittest.skipUnless(sys.platform == "win32", "Windows command interpreter required")
class WindowsInstallerTests(unittest.TestCase):
    def check_installer(self, directory, *, on_path):
        directory = Path(directory)
        shutil.copy2(Path(__file__).resolve().parents[1] / "INSTALL_WINDOWS.bat", directory)
        environment = os.environ.copy()
        environment["LOCALAPPDATA"] = str(directory / "user data")
        environment["ProgramFiles"] = str(directory / "program files")
        environment["JAILWATCH_PYTHON"] = "invalid inherited value"
        system32 = Path(environment["SystemRoot"]) / "System32"
        paths = [str(system32)]
        if on_path:
            paths.insert(0, str(Path(sys.executable).parent))
        environment["PATH"] = os.pathsep.join(paths)
        # Make accidental use of the launcher fail, including on hosted runners.
        (directory / "py.bat").write_text("@echo off\nexit /b 99\n")
        result = subprocess.run(
            [environment.get("COMSPEC", str(system32 / "cmd.exe")), "/d", "/c",
             "INSTALL_WINDOWS.bat --check-python"],
            cwd=directory, env=environment, input="", capture_output=True,
            text=True, timeout=30,
        )
        return result

    def test_python_on_path_without_launcher(self):
        with tempfile.TemporaryDirectory(prefix="JailWatch setup ") as directory:
            result = self.check_installer(directory, on_path=True)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn(str(Path(sys.executable)), result.stdout)
            self.assertFalse((Path(directory) / ".venv").exists())

    def test_standard_install_without_path_or_launcher(self):
        with tempfile.TemporaryDirectory(prefix="JailWatch setup ") as directory:
            target = (Path(directory) / "user data" / "Programs" / "Python"
                      / f"Python{sys.version_info.major}{sys.version_info.minor}")
            target.parent.mkdir(parents=True)
            # A directory junction models Python installed outside the current PATH.
            subprocess.run(
                [os.environ["COMSPEC"], "/d", "/c", "mklink", "/J", str(target),
                 str(Path(sys.executable).parent)],
                check=True, capture_output=True, text=True,
            )
            try:
                result = self.check_installer(directory, on_path=False)
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                self.assertIn("Detected Python", result.stdout)
                self.assertFalse((Path(directory) / ".venv").exists())
            finally:
                target.rmdir()

    def test_missing_python_returns_actionable_error(self):
        with tempfile.TemporaryDirectory(prefix="JailWatch setup ") as directory:
            result = self.check_installer(directory, on_path=False)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("64-bit was not found", result.stdout)
            self.assertIn("py launcher is optional", result.stdout)
            self.assertFalse((Path(directory) / ".venv").exists())
