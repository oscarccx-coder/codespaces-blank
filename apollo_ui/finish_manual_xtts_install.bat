@echo off
setlocal EnableExtensions
title Apollo XTTS - Finish Manual Model Install

set "APOLLO=F:\Apollo\apollo 1\apollo_ui"
set "MODEL=%LOCALAPPDATA%\Apollo\models\voice\xtts_v2"
set "PYTHON_EXE=%LOCALAPPDATA%\Python\pythoncore-3.14-64\python.exe"

echo ============================================================
echo  APOLLO XTTS - FINISH MANUAL MODEL INSTALL
echo ============================================================
echo.
echo Expected model folder:
echo   %MODEL%
echo.

if not exist "%MODEL%" mkdir "%MODEL%"

set "MISSING=0"
for %%F in (
  model.pth
  config.json
  vocab.json
  speakers_xtts.pth
  hash.md5
) do (
  if exist "%MODEL%\%%F" (
    echo [OK] %%F
  ) else (
    echo [MISSING] %%F
    set "MISSING=1"
  )
)

if "%MISSING%"=="1" (
  echo.
  echo Put all five downloaded XTTS files into:
  echo   %MODEL%
  echo.
  start "" explorer.exe "%MODEL%"
  pause
  exit /b 1
)

if not exist "%PYTHON_EXE%" (
  echo [ERROR] Apollo Python was not found:
  echo   %PYTHON_EXE%
  pause
  exit /b 1
)

echo.
echo Verifying XTTS config...
"%PYTHON_EXE%" -c "from TTS.tts.configs.xtts_config import XttsConfig; c=XttsConfig(); c.load_json(r'%MODEL%\config.json'); print('XTTS config: OK')"
if errorlevel 1 (
  echo [ERROR] XTTS config verification failed.
  pause
  exit /b 1
)

echo.
echo Updating Apollo Voice Imprint settings...
if not exist "%APOLLO%\storage\media\voice_imprint" mkdir "%APOLLO%\storage\media\voice_imprint"
set "SETTINGS=%APOLLO%\storage\media\voice_imprint\settings.json"

"%PYTHON_EXE%" -c "import json,pathlib; p=pathlib.Path(r'%SETTINGS%'); d={}; exec(\"try:\\n d=json.loads(p.read_text(encoding='utf-8'))\\nexcept Exception:\\n d={}\"); d['backend']='xtts_local'; d['model_dir']=r'%MODEL%'; d['device']='auto'; d.setdefault('language','en'); p.write_text(json.dumps(d,indent=2)+'\n',encoding='utf-8'); print('Apollo XTTS model_dir ->',d['model_dir'])"
if errorlevel 1 (
  echo [ERROR] Could not update Apollo settings.
  pause
  exit /b 1
)

echo.
echo ============================================================
echo  MANUAL XTTS MODEL INSTALL COMPLETE
echo ============================================================
echo.
echo Restart Apollo and use:
echo   Voice Imprint Lab ^> Check Voice + Engine Readiness
echo.
pause
