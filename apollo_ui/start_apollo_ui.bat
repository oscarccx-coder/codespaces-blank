@echo off
setlocal EnableExtensions EnableDelayedExpansion
cd /d "%~dp0"

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
    echo Run repair_apollo_python.bat.
    pause
    exit /b 1
)

set "PYTHONW_EXE=%PYTHON_EXE:python.exe=pythonw.exe%"
if not exist "%PYTHONW_EXE%" set "PYTHONW_EXE=%PYTHON_EXE%"

start "" /b "%PYTHONW_EXE%" "%~dp0launch_apollo.pyw"
exit /b 0

:TRY_PY
if defined PYTHON_EXE exit /b 0
if not exist "%~1" exit /b 0
"%~1" -c "import sys,encodings" >nul 2>&1
if not errorlevel 1 set "PYTHON_EXE=%~1"
exit /b 0
