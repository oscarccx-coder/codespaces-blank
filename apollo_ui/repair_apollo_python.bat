@echo off
setlocal EnableExtensions EnableDelayedExpansion
title Apollo Python Repair
cd /d "%~dp0"

echo ============================================================
echo  APOLLO - PYTHON REPAIR
echo ============================================================
echo.

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
    echo [ERROR] No healthy Python was found.
    echo The "encodings" module is part of Python itself, not a pip package.
    echo Repair/reinstall Python, then run this BAT again.
    pause
    exit /b 1
)

echo [OK] Python:
echo   %PYTHON_EXE%
"%PYTHON_EXE%" -c "import sys,encodings; print(sys.version); print(sys.executable); print(encodings.__file__)"
if errorlevel 1 goto :FAIL

"%PYTHON_EXE%" -m pip --version >nul 2>&1
if errorlevel 1 (
    "%PYTHON_EXE%" -m ensurepip --upgrade
    if errorlevel 1 goto :FAIL
)

"%PYTHON_EXE%" -m pip install -r "%~dp0requirements.txt"
if errorlevel 1 goto :FAIL

"%PYTHON_EXE%" -c "import encodings,sqlite3,json,numpy,psutil; import PySide6; print('Apollo Python repaired')"
if errorlevel 1 goto :FAIL

echo.
echo ============================================================
echo  REPAIR COMPLETE
echo ============================================================
echo Use start_apollo_ui.bat.
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
echo [ERROR] Repair did not complete.
pause
exit /b 1
