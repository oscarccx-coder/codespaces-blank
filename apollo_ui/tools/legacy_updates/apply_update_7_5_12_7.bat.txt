@echo off
setlocal EnableExtensions
cd /d "%~dp0"

echo ============================================================
echo  APOLLO 7.5.12.7 - FINALISE UPDATE
echo ============================================================
echo.

set "PYTHONHOME="
set "PYTHONPATH="
set "PYTHON_EXE="

if exist "%LOCALAPPDATA%\Python\pythoncore-3.14-64\python.exe" set "PYTHON_EXE=%LOCALAPPDATA%\Python\pythoncore-3.14-64\python.exe"
if not defined PYTHON_EXE for /f "delims=" %%P in ('where python.exe 2^>nul') do if not defined PYTHON_EXE set "PYTHON_EXE=%%P"

if not defined PYTHON_EXE (
    echo [WARNING] Python not found. Apollo files are updated, but config version was not changed.
    pause
    exit /b 0
)

"%PYTHON_EXE%" -c "import json,pathlib; p=pathlib.Path(r'%CD%\config.json'); d=json.loads(p.read_text(encoding='utf-8')); d['version']='7.5.12.7'; p.write_text(json.dumps(d,indent=2)+'\n',encoding='utf-8'); print('Apollo config version -> 7.5.12.7')"
if errorlevel 1 (
    echo [WARNING] Could not update config.json version field.
) else (
    echo [OK] config.json preserved; only version field changed.
)

echo.
echo Update finalised.
echo Run start_apollo_ui.bat
echo.
pause
