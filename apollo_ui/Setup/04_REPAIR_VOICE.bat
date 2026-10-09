@echo off
setlocal EnableExtensions
title Apollo - Repair XTTS
cd /d "%~dp0.."
call "%~dp0..\install_xtts_v2.bat" %*
exit /b %ERRORLEVEL%
