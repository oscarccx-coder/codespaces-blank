@echo off
setlocal
cd /d "%~dp0.."
if "%~1"=="" (
  echo Choose backend names: kokoro faster_whisper docling crawl4ai browser_use graphiti gpt_researcher llama_cpp
  echo Example: 20_SETUP_CAPABILITIES.bat kokoro docling crawl4ai
  pause
  exit /b 1
)
py -3.12 --version >nul 2>&1
if errorlevel 1 (
  py -3.13 "tools\setup_capabilities.py" %*
) else (
  py -3.12 "tools\setup_capabilities.py" %*
)
set "APOLLO_CAPABILITY_EXIT=%ERRORLEVEL%"
if not "%APOLLO_CAPABILITY_EXIT%"=="0" echo Setup failed. Read the error above.
pause
exit /b %APOLLO_CAPABILITY_EXIT%
