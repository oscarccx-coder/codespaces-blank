@echo off
setlocal EnableExtensions
cd /d "%~dp0"
set "PYTHON_EXE=%LOCALAPPDATA%\Python\pythoncore-3.14-64\python.exe"
echo ============================================================
echo  APOLLO 7.5.12.14 - VOICE PERFORMANCE HOTFIX
echo ============================================================
echo Fixes XTTS 400-token errors, spaCy sentence-split errors and GUI freezing.
echo.
if exist "%PYTHON_EXE%" "%PYTHON_EXE%" -c "import json,pathlib; p=pathlib.Path(r'%CD%\config.json'); d=json.loads(p.read_text(encoding='utf-8')); d['version']='7.5.12.14'; p.write_text(json.dumps(d,indent=2)+'\n',encoding='utf-8'); print('Apollo config version -^> 7.5.12.14')"
echo.
echo [OK] Restart Apollo completely.
pause
