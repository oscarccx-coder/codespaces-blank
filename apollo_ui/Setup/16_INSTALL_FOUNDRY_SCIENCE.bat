@echo off
setlocal EnableExtensions
title Apollo Foundry - Optional Local Science Libraries
cd /d "%~dp0.."
echo ======================================================
echo APOLLO FOUNDRY - OPTIONAL WINDOWS SCIENCE LIBRARIES
echo ======================================================
echo.
echo The Docker sandbox already contains NumPy, SymPy and Matplotlib.
echo This optional setup is ONLY for trusted apps launched directly on Windows.
echo It installs into Apollo's private .venv, never global Python.
echo Direct Windows preview is UNSANDBOXED. Review generated code first.
echo.
if not exist ".venv\Scripts\python.exe" (
  echo [ERROR] Apollo .venv is missing. Run Setup\01_INSTALL_APOLLO.bat.
  pause
  exit /b 1
)
".venv\Scripts\python.exe" -c "import sys; assert sys.prefix != sys.base_prefix"
if errorlevel 1 (
  echo [ERROR] Refusing to install outside a virtual environment.
  pause
  exit /b 1
)
choice /C YN /N /M "Install optional scientific libraries into Apollo .venv? [Y/N] "
if errorlevel 2 exit /b 0
".venv\Scripts\python.exe" -m pip install --only-binary=:all: "sympy>=1.13,<2" "matplotlib>=3.10,<4"
if errorlevel 1 (
  echo [ERROR] Package installation failed. Check internet, disk and Python version.
  pause
  exit /b 1
)
".venv\Scripts\python.exe" -m pip check
if errorlevel 1 (
  echo [WARNING] Dependency conflicts found. Inspect output before local preview.
  pause
  exit /b 1
)
echo [OK] Optional local scientific packages are installed.
pause
exit /b 0
