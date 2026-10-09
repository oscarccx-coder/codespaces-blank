@echo off
setlocal EnableExtensions
title Apollo - Uninstall Requirements
cd /d "%~dp0"

echo ============================================================
echo  APOLLO - UNINSTALL REQUIREMENTS
echo ============================================================
echo This removes ONLY Apollo's private .venv environment:
echo   %~dp0.venv
echo.
echo This does NOT remove:
echo   - Windows Python, system packages, Git or Ollama
echo   - Apollo code, models, XTTS downloads or voice profiles
echo   - Chats, research, memory, projects or settings in storage
echo   - Shared FFmpeg / WinGet packages
echo.
echo Close Apollo before continuing.
echo.

if not exist "%~dp0.venv\pyvenv.cfg" (
    echo [INFO] No Apollo-owned .venv installation was found.
    echo No other Python installation or folder will be touched.
    if not defined CI pause
    exit /b 0
)
choice /C YN /N /M "Remove Apollo's local Python requirements? [Y/N]: "
if errorlevel 2 (
    echo Cancelled: nothing removed.
    exit /b 0
)
if errorlevel 1 (
    rmdir /S /Q "%~dp0.venv"
    if exist "%~dp0.venv" (
        echo [ERROR] Could not fully remove .venv.
        echo Close Apollo, Python and any terminals using it, then retry.
        if not defined CI pause
        exit /b 1
    )
    echo.
    echo [OK] Apollo's local Python dependencies have been removed.
    echo Run INSTALL_REQUIREMENTS.bat to reinstall them.
    if not defined CI pause
    exit /b 0
)
echo [ERROR] Could not read your confirmation; nothing removed.
if not defined CI pause
exit /b 1
