@echo off
setlocal EnableExtensions
title Apollo - Finish XTTS Setup (No Reinstall)
cd /d "%~dp0.."
call "%~dp0..\install_xtts_v2.bat" --configure-only
exit /b %ERRORLEVEL%
