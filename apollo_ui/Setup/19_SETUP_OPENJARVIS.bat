@echo off
setlocal
cd /d "%~dp0.."
if exist ".venv\Scripts\python.exe" (
  ".venv\Scripts\python.exe" "tools\setup_openjarvis.py" %*
) else (
  py -3.13 "tools\setup_openjarvis.py" %*
)
set "APOLLO_SETUP_EXIT=%ERRORLEVEL%"
if not "%APOLLO_SETUP_EXIT%"=="0" echo OpenJarvis setup failed. Read the error above before closing.
pause
exit /b %APOLLO_SETUP_EXIT%
