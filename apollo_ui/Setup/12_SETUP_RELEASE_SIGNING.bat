@echo off
setlocal EnableExtensions
title Apollo - One-time Release Signing Setup
rem Works as Setup/ launcher in Apollo or extracted alongside tools/ in a ZIP.
set "APOLLO_DIR=F:\Apollo\apollo 1\apollo_ui"
if exist "%~dp0..\apollo_release.py" set "APOLLO_DIR=%~dp0.."
if not "%~1"=="" set "APOLLO_DIR=%~1"
set "PYTHON_EXE=%APOLLO_DIR%\.venv\Scripts\python.exe"
set "SETUP_TOOL=%~dp0..\tools\prepare_release_identity.py"
echo.
echo ============================================================
echo  APOLLO RELEASE SIGNING - ONE TIME LOCAL KEY SETUP
echo ============================================================
echo.
echo Apollo installation: %APOLLO_DIR%
echo No upload, release publishing or silent key trust is performed.
echo.
if not exist "%PYTHON_EXE%" (
    echo [ERROR] Apollo virtual environment missing: %PYTHON_EXE%
    echo Run Setup\01_INSTALL_APOLLO.bat first.
    pause
    exit /b 1
)
if not exist "%SETUP_TOOL%" (
    echo [ERROR] Missing trusted setup helper: %SETUP_TOOL%
    echo Extract BOTH Setup and tools folders from the setup ZIP.
    pause
    exit /b 1
)
"%PYTHON_EXE%" "%SETUP_TOOL%" --root "%APOLLO_DIR%"
set "RESULT=%ERRORLEVEL%"
echo.
if "%RESULT%"=="0" (
    echo [OK] Signing identity prepared. Follow the steps above.
) else (
    echo [ERROR] Signing identity setup stopped. Existing keys are not overwritten.
)
pause
exit /b %RESULT%
