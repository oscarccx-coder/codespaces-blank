@echo off
setlocal EnableExtensions
title Apollo Foundry - Prerequisites
cd /d "%~dp0.."
echo.
echo APOLLO FOUNDRY - READ ONLY PREREQUISITES CHECK
echo No software will be installed, modified or downloaded.
echo.
set "PYTHON_EXE="
if exist ".venv\Scripts\python.exe" set "PYTHON_EXE=.venv\Scripts\python.exe"
if not defined PYTHON_EXE (
  where py >nul 2>&1
  if not errorlevel 1 (
    py -3 apollo_foundry_preflight.py
    goto :done
  )
  where python >nul 2>&1
  if not errorlevel 1 (
    python apollo_foundry_preflight.py
    goto :done
  )
  echo [ERROR] Python not found. Run Setup\01_INSTALL_APOLLO.bat.
  goto :done
)
"%PYTHON_EXE%" apollo_foundry_preflight.py
:done
echo.
echo To install Docker Desktop with explicit consent, run:
echo Setup\14_INSTALL_DOCKER_DESKTOP.bat
echo Then start Docker Desktop and run Setup\09_SETUP_FOUNDRY_SANDBOX.bat.
pause
