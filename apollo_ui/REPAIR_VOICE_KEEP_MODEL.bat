@echo off
setlocal EnableExtensions
title Apollo Voice Repair - Keep Existing XTTS Model
cd /d "%~dp0"

set "MODEL_DIR=C:\Users\oscar\AppData\Local\Apollo\models\voice\xtts_v2"
set "PYTHON_EXE="

echo ============================================================
echo  APOLLO VOICE REPAIR - EXISTING MODEL
echo ============================================================
echo.
echo XTTS model:
echo   %MODEL_DIR%
echo.

if not exist "%MODEL_DIR%\config.json" (
    echo [ERROR] Missing %MODEL_DIR%\config.json
    echo This repair will NOT download the model automatically.
    pause
    exit /b 1
)
if not exist "%MODEL_DIR%\model.pth" (
    echo [ERROR] Missing %MODEL_DIR%\model.pth
    pause
    exit /b 1
)
if not exist "%MODEL_DIR%\vocab.json" (
    echo [ERROR] Missing %MODEL_DIR%\vocab.json
    pause
    exit /b 1
)

set "PYTHONHOME="
set "PYTHONPATH="
call :TRY_PY "%LOCALAPPDATA%\Python\pythoncore-3.14-64\python.exe"
call :TRY_PY "%~dp0.venv\Scripts\python.exe"
call :TRY_PY "%~dp0venv\Scripts\python.exe"
for %%V in (314 313 312 311 310) do if not defined PYTHON_EXE call :TRY_PY "%LOCALAPPDATA%\Programs\Python\Python%%V\python.exe"
if not defined PYTHON_EXE (
    for /f "delims=" %%P in ('where python.exe 2^>nul') do if not defined PYTHON_EXE call :TRY_PY "%%P"
)
if not defined PYTHON_EXE (
    echo [ERROR] No healthy Python installation found.
    pause
    exit /b 1
)

echo [OK] Python: %PYTHON_EXE%
echo.
echo Checking XTTS Python packages...
"%PYTHON_EXE%" -c "import importlib.metadata as m; print('coqui-tts:',m.version('coqui-tts')); print('legacy TTS:',m.version('TTS') if 'TTS' in [d.metadata.get('Name','') for d in m.distributions()] else 'not installed')" 2>nul

echo.
echo Removing conflicting legacy/runtime packages and reinstalling the pinned stack.
echo The XTTS MODEL DIRECTORY ABOVE IS NOT TOUCHED.
"%PYTHON_EXE%" -m pip uninstall -y TTS coqui-tts transformers tokenizers
if errorlevel 1 echo [INFO] Some packages were already absent.

"%PYTHON_EXE%" -m pip install --no-cache-dir "coqui-tts==0.27.5"
if errorlevel 1 goto :FAIL
"%PYTHON_EXE%" -m pip install --no-cache-dir --force-reinstall "transformers==4.57.6"
if errorlevel 1 goto :FAIL

echo.
echo Verifying clean Coqui XTTS import...
"%PYTHON_EXE%" -c "import importlib.metadata as m; assert m.version('coqui-tts')=='0.27.5'; from TTS.tts.configs.xtts_config import XttsConfig; c=XttsConfig(); c.load_json(r'%MODEL_DIR%\config.json'); print('XTTS import + existing model config: OK')"
if errorlevel 1 goto :FAIL

echo.
echo ============================================================
echo  VOICE REPAIR COMPLETE
echo ============================================================
echo Existing XTTS model preserved:
echo   %MODEL_DIR%
echo.
echo Restart Apollo and run Voice Center ^> Check Voice + Engine Readiness.
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
echo [ERROR] Voice runtime repair failed.
echo Your XTTS model files were NOT deleted.
pause
exit /b 1
