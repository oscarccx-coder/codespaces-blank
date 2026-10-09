@echo off
setlocal EnableExtensions EnableDelayedExpansion
title Apollo - Install Requirements
cd /d "%~dp0"
set "PYTHONHOME="
set "PYTHONPATH="
set "PIP_REQUIRE_VIRTUALENV=true"
set "VENV_PY=%~dp0.venv\Scripts\python.exe"

echo ============================================================
echo  APOLLO - INSTALL REQUIREMENTS
echo ============================================================
echo Installs packages into Apollo's private .venv only.
echo System Python, personal files and downloaded models are not modified.
echo.

if exist "%VENV_PY%" goto :INSTALL_PACKAGES

echo [1/3] Finding Python for a new Apollo environment...
set "BASE_VERSION="
where py.exe >nul 2>&1
if not errorlevel 1 (
    for %%V in (3.13 3.12 3.11 3.14) do (
        if not defined BASE_VERSION (
            py -%%V -c "import sys,encodings,venv; assert sys.version_info.major==3" >nul 2>&1
            if not errorlevel 1 set "BASE_VERSION=%%V"
        )
    )
)
if defined BASE_VERSION (
    echo Using Python !BASE_VERSION! via Windows Python Launcher.
    py -!BASE_VERSION! -m venv "%~dp0.venv"
    if errorlevel 1 goto :FAIL
    goto :CHECK_VENV
)

set "BASE_PY="
call :TRY_PY "%LOCALAPPDATA%\Programs\Python\Python313\python.exe"
call :TRY_PY "%LOCALAPPDATA%\Programs\Python\Python312\python.exe"
call :TRY_PY "%LOCALAPPDATA%\Programs\Python\Python311\python.exe"
call :TRY_PY "%LOCALAPPDATA%\Python\pythoncore-3.14-64\python.exe"
for /f "delims=" %%P in ('where python.exe 2^>nul') do (
    if not defined BASE_PY call :TRY_PY "%%P"
)
if not defined BASE_PY (
    echo [ERROR] A healthy Python 3.11 or later could not be found.
    echo Install Python from python.org, then run this file again.
    goto :FAIL
)
echo Using "%BASE_PY%"
"%BASE_PY%" -m venv "%~dp0.venv"
if errorlevel 1 goto :FAIL

:CHECK_VENV
if not exist "%VENV_PY%" (
    echo [ERROR] Python did not create Apollo's local environment.
    goto :FAIL
)

:INSTALL_PACKAGES
echo [2/3] Installing Apollo's core dependencies...
"%VENV_PY%" -c "import sys,encodings,venv; assert not (sys.prefix == sys.base_prefix); assert sys.version_info >= (3,11)" 
if errorlevel 1 (
    echo [ERROR] .venv is missing or is not an isolated Python environment.
    goto :FAIL
)
"%VENV_PY%" -m pip install -r "%~dp0requirements.txt"
if errorlevel 1 goto :FAIL
echo.
echo [3/3] Checking installed dependencies...
"%VENV_PY%" -m pip check
if errorlevel 1 goto :FAIL
"%VENV_PY%" -c "import PySide6,numpy,psutil,duckdb,sounddevice,serial,cryptography; print('Apollo dependencies OK')"
if errorlevel 1 goto :FAIL

if /I "%~1"=="--voice" (
    echo.
    echo Installing OPTIONAL XTTS speech dependencies into the same .venv.
    echo This may require several gigabytes of disk space.
    call "%~dp0install_xtts_v2.bat"
    if errorlevel 1 goto :FAIL
)

echo.
echo [OK] Apollo requirements installed in .venv.
echo Launch Apollo using start_apollo_ui.bat
echo Optional voice runtime: install_xtts_v2.bat
echo Optional full install: INSTALL_REQUIREMENTS.bat --voice
echo.
if not defined CI pause
exit /b 0

:TRY_PY
if defined BASE_PY exit /b 0
if not exist "%~1" exit /b 0
"%~1" -c "import sys,encodings,venv; assert sys.version_info >= (3,11)" >nul 2>&1
if not errorlevel 1 set "BASE_PY=%~1"
exit /b 0

:FAIL
echo.
echo [ERROR] Installation did not complete.
echo Apollo's model files, voice profiles and personal storage were not removed.
echo Check the message above and run this installer again.
if not defined CI pause
exit /b 1
