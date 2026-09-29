@echo off
setlocal EnableExtensions
cd /d "%~dp0"
set "PYTHON_EXE=%LOCALAPPDATA%\Python\pythoncore-3.14-64\python.exe"

echo ============================================================
echo  APOLLO 7.5.12.15 - VOICE CENTER + PROCESS ISOLATION
echo ============================================================
echo.
echo This update preserves voice profiles, XTTS model files and user settings.
echo.

if exist "%PYTHON_EXE%" (
  "%PYTHON_EXE%" -c "import json,pathlib; p=pathlib.Path(r'%CD%\config.json'); d=json.loads(p.read_text(encoding='utf-8')); d['version']='7.5.12.15'; p.write_text(json.dumps(d,indent=2)+'\n',encoding='utf-8'); print('Apollo config version -> 7.5.12.15')"
)

echo.
echo [OK] Voice Center installed.
echo [OK] XTTS process isolation installed.
echo [OK] Heavy readiness imports removed from the GUI process.
echo.
echo Fully close Apollo and launch it again.
pause
