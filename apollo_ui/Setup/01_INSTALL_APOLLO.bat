@echo off
setlocal EnableExtensions
title Apollo - Install and Setup
cd /d "%~dp0.."
call "%~dp0..\INSTALL_REQUIREMENTS.bat"
if errorlevel 1 exit /b 1
if defined CI exit /b 0
choice /C YN /N /M "Create Apollo and Apollo Setup shortcuts on your Desktop? [Y/N]: "
if errorlevel 2 goto :WIZARD
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0create_shortcuts.ps1"
if errorlevel 1 echo [WARNING] Shortcuts could not be created. You can launch Apollo from Setup.
:WIZARD
call "%~dp0\10_SETUP_WIZARD.bat"
exit /b %ERRORLEVEL%
