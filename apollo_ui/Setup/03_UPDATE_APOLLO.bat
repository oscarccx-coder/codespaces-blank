@echo off
setlocal EnableExtensions
title Apollo - Update Code
cd /d "%~dp0.."
call "%~dp0..\UPDATE_APOLLO_CODE.bat" %*
exit /b %ERRORLEVEL%
