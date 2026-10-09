@echo off
setlocal EnableExtensions
title Apollo - Backup
cd /d "%~dp0.."
set "PYTHON_EXE=%~dp0..\.venv\Scripts\python.exe"
if not exist "%PYTHON_EXE%" (
  echo [ERROR] Install Apollo first using Setup\01_INSTALL_APOLLO.bat
  pause
  exit /b 1
)
"%PYTHON_EXE%" "%~dp0..\apollo_setup.py" backup "%~dp0..\storage\backups\exports\Apollo-backup-%RANDOM%-%RANDOM%.zip"
set "RESULT=%ERRORLEVEL%"
if not defined CI pause
exit /b %RESULT%
