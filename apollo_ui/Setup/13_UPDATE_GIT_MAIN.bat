@echo off
setlocal EnableExtensions DisableDelayedExpansion
title Apollo - Safe Git Main Update
set "NO_PAUSE=0"
if /I "%~1"=="--no-pause" set "NO_PAUSE=1"
if defined CI set "NO_PAUSE=1"
set "PYTHON_EXE=%~dp0..\.venv\Scripts\python.exe"
if exist "%PYTHON_EXE%" goto :RUN
where py.exe >nul 2>&1
if not errorlevel 1 (
  set "PYTHON_EXE=py -3"
  goto :RUN
)
where python.exe >nul 2>&1
if not errorlevel 1 (
  set "PYTHON_EXE=python"
  goto :RUN
)
echo [ERROR] Python is unavailable. Repair Apollo using Setup\01_INSTALL_APOLLO.bat.
set "EXIT_CODE=1"
goto :FINISH
:RUN
if not exist "%~dp0..\apollo_git_source_update.py" (
  echo [ERROR] Apollo source updater is missing.
  set "EXIT_CODE=1"
  goto :FINISH
)
rem The Python helper protects tracked memory, audio, and profile data.
rem It still refuses dirty code and any remote changes to protected data.
rem Never use git reset --hard or an automatic destructive clean here.
if "%PYTHON_EXE%"=="py -3" (
  py -3 "%~dp0..\apollo_git_source_update.py" %*
) else if "%PYTHON_EXE%"=="python" (
  python "%~dp0..\apollo_git_source_update.py" %*
) else (
  "%PYTHON_EXE%" "%~dp0..\apollo_git_source_update.py" %*
)
set "EXIT_CODE=%errorlevel%"
:FINISH
echo.
echo [RESULT] Apollo update result code %EXIT_CODE%.
if "%NO_PAUSE%"=="0" (
  echo Press any key to close this window.
  pause >nul
)
endlocal & exit /b %EXIT_CODE%
