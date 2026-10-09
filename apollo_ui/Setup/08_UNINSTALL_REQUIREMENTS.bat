@echo off
setlocal EnableExtensions
title Apollo - Uninstall Private Dependencies
cd /d "%~dp0.."
call "%~dp0..\UNINSTALL_REQUIREMENTS.bat" %*
exit /b %ERRORLEVEL%
