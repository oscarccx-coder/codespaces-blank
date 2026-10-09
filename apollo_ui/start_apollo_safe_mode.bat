@echo off
setlocal EnableExtensions
cd /d "%~dp0"
set "APOLLO_SAFE_MODE=1"
call "%~dp0start_apollo_ui.bat"
exit /b %ERRORLEVEL%
