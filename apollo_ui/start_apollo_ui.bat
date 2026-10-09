@echo off
setlocal EnableExtensions
title Apollo - Start
cd /d "%~dp0"
set "PYTHONHOME="
set "PYTHONPATH="
set "PYTHON_EXE=%~dp0.venv\Scripts\python.exe"
set "PYTHONW_EXE=%~dp0.venv\Scripts\pythonw.exe"

if not exist "%PYTHON_EXE%" (
    echo [ERROR] Apollo's private Python environment is not installed.
    echo Run INSTALL_REQUIREMENTS.bat once, then start Apollo again.
    pause
    exit /b 1
)
"%PYTHON_EXE%" -c "import encodings,PySide6,psutil,numpy" >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Apollo's dependencies are incomplete or damaged.
    echo Run INSTALL_REQUIREMENTS.bat to repair the private environment.
    pause
    exit /b 1
)
if not exist "%PYTHONW_EXE%" set "PYTHONW_EXE=%PYTHON_EXE%"
start "" /b "%PYTHONW_EXE%" "%~dp0launch_apollo.pyw"
exit /b 0
