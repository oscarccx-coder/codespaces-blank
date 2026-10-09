@echo off
setlocal EnableExtensions
title Apollo - Start
cd /d "%~dp0.."
call "%~dp0..\start_apollo_ui.bat" %*
exit /b %ERRORLEVEL%
