@echo off
setlocal EnableExtensions
title Apollo - Restore Backup
cd /d "%~dp0.."
set "PYTHON_EXE=%~dp0..\.venv\Scripts\python.exe"
if not exist "%PYTHON_EXE%" (
  echo Install Apollo dependencies before restoring a backup.
  pause
  exit /b 1
)
echo Close Apollo completely before restoring data.
echo WARNING: Restore replaces matching saved memories and voice profiles.
set /p "BACKUP=Full path to Apollo ZIP backup: "
if not defined BACKUP exit /b 2
"%PYTHON_EXE%" "%~dp0..\apollo_setup.py" restore "%BACKUP%" --yes
set "RESULT=%ERRORLEVEL%"
if not defined CI pause
exit /b %RESULT%
