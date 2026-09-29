@echo off
setlocal EnableExtensions EnableDelayedExpansion
title Apollo UI Installer
cd /d "%~dp0"

echo ============================================================
echo  APOLLO UI - INSTALL
echo ============================================================
echo.

rem A stale PYTHONHOME/PYTHONPATH can make Python lose its own standard library.
set "PYTHONHOME="
set "PYTHONPATH="
set "PYTHON_EXE="

call :TRY_PY "%~dp0.venv\Scripts\python.exe"
call :TRY_PY "%~dp0venv\Scripts\python.exe"
call :TRY_PY "%LOCALAPPDATA%\Python\pythoncore-3.14-64\python.exe"

for %%V in (314 313 312 311 310) do (
    if not defined PYTHON_EXE call :TRY_PY "%LOCALAPPDATA%\Programs\Python\Python%%V\python.exe"
)

if not defined PYTHON_EXE (
    for /f "delims=" %%P in ('where python.exe 2^>nul') do (
        if not defined PYTHON_EXE call :TRY_PY "%%P"
    )
)

if not defined PYTHON_EXE (
    echo [ERROR] No healthy Python installation was found.
    echo.
    echo Apollo requires a Python that can import its built-in encodings module.
    echo If Python is installed, repair/reinstall it and run this installer again.
    echo.
    pause
    exit /b 1
)

echo [OK] Healthy Python:
echo   %PYTHON_EXE%
"%PYTHON_EXE%" -c "import sys,encodings; print('Python:',sys.version); print('encodings:',encodings.__file__)"
if errorlevel 1 goto :FAIL

echo.
echo ------------------------------------------------------------
echo  Updating pip
echo ------------------------------------------------------------
"%PYTHON_EXE%" -m pip install --upgrade pip
if errorlevel 1 goto :FAIL

echo.
echo ------------------------------------------------------------
echo  Installing Apollo requirements
echo ------------------------------------------------------------
"%PYTHON_EXE%" -m pip install -r "%~dp0requirements.txt"
if errorlevel 1 goto :FAIL

echo.
echo ------------------------------------------------------------
echo  Apollo dependency smoke test
echo ------------------------------------------------------------
"%PYTHON_EXE%" -c "import encodings,sqlite3,json,numpy,psutil; import PySide6; print('Apollo imports OK')"
if errorlevel 1 goto :FAIL

echo.
echo ============================================================
echo  INSTALL COMPLETE
echo ============================================================
echo Run start_apollo_ui.bat
echo.
pause
exit /b 0

:TRY_PY
if defined PYTHON_EXE exit /b 0
if not exist "%~1" exit /b 0
"%~1" -c "import sys,encodings" >nul 2>&1
if not errorlevel 1 set "PYTHON_EXE=%~1"
exit /b 0

:FAIL
echo.
echo ============================================================
echo  INSTALL FAILED
echo ============================================================
echo Apollo was NOT marked installed because a required command failed.
echo Fix the error above and run install.bat again.
echo.
pause
exit /b 1
