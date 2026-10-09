@echo off
setlocal EnableExtensions
title Apollo - Safe Mode
cd /d "%~dp0.."
call "%~dp0..\start_apollo_safe_mode.bat" %*
exit /b %ERRORLEVEL%
