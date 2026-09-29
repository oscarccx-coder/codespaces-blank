@echo off
setlocal EnableExtensions EnableDelayedExpansion
title Apollo XTTS - Finish Manual Install v2

set "APOLLO=F:\Apollo\apollo 1\apollo_ui"
set "MODEL=%LOCALAPPDATA%\Apollo\models\voice\xtts_v2"
set "PYTHON_EXE=%LOCALAPPDATA%\Python\pythoncore-3.14-64\python.exe"
set "SETTINGS=%APOLLO%\storage\media\voice_imprint\settings.json"
set "FFMPEG_BIN="

echo ============================================================
echo  APOLLO XTTS - FINISH MANUAL MODEL INSTALL v2
echo ============================================================
echo.
echo Model:
echo   %MODEL%
echo.

if not exist "%APOLLO%" (
    echo [ERROR] Apollo folder not found:
    echo   %APOLLO%
    pause
    exit /b 1
)

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
    echo Put the missing XTTS files into:
    echo   %MODEL%
    start "" explorer.exe "%MODEL%"
    pause
    exit /b 1
)

if not exist "%PYTHON_EXE%" (
    echo.
    echo [ERROR] Python not found:
    echo   %PYTHON_EXE%
    pause
    exit /b 1
)

echo.
echo ------------------------------------------------------------
echo  1/4 - Verify XTTS model config
echo ------------------------------------------------------------
"%PYTHON_EXE%" -c "from TTS.tts.configs.xtts_config import XttsConfig; c=XttsConfig(); c.load_json(r'%MODEL%\config.json'); print('XTTS config: OK')"
if errorlevel 1 (
    echo [ERROR] XTTS config verification failed.
    pause
    exit /b 1
)

echo.
echo ------------------------------------------------------------
echo  2/4 - Locate FFmpeg Shared runtime
echo ------------------------------------------------------------

if exist "%APOLLO%\find_ffmpeg_shared.ps1" (
    set "FFMPEG_FIND=%TEMP%\apollo_ffmpeg_finish_%RANDOM%_%RANDOM%.txt"
    powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%APOLLO%\find_ffmpeg_shared.ps1" > "!FFMPEG_FIND!" 2>nul
    if not errorlevel 1 set /p FFMPEG_BIN=<"!FFMPEG_FIND!"
    if exist "!FFMPEG_FIND!" del /Q "!FFMPEG_FIND!" >nul 2>&1
)

if defined FFMPEG_BIN (
    echo [OK] FFmpeg Shared:
    echo   !FFMPEG_BIN!
) else (
    echo [INFO] FFmpeg Shared path was not rediscovered.
    echo Apollo can still use its existing stored path if one is already configured.
)

echo.
echo ------------------------------------------------------------
echo  3/4 - Update Apollo Voice Imprint settings
echo ------------------------------------------------------------

if not exist "%APOLLO%\storage\media\voice_imprint" (
    mkdir "%APOLLO%\storage\media\voice_imprint"
)

set "APOLLO_SETTINGS=%SETTINGS%"
set "APOLLO_MODEL=%MODEL%"
set "APOLLO_FFMPEG=!FFMPEG_BIN!"

powershell.exe -NoProfile -ExecutionPolicy Bypass -Command ^
  "$ErrorActionPreference='Stop';" ^
  "$path=$env:APOLLO_SETTINGS;" ^
  "$obj=$null;" ^
  "if(Test-Path -LiteralPath $path){" ^
  "  try{$obj=Get-Content -LiteralPath $path -Raw -Encoding UTF8 | ConvertFrom-Json}catch{$obj=$null}" ^
  "};" ^
  "if($null -eq $obj){$obj=New-Object PSObject};" ^
  "$obj | Add-Member -NotePropertyName backend -NotePropertyValue 'xtts_local' -Force;" ^
  "$obj | Add-Member -NotePropertyName model_dir -NotePropertyValue $env:APOLLO_MODEL -Force;" ^
  "$obj | Add-Member -NotePropertyName device -NotePropertyValue 'auto' -Force;" ^
  "if($null -eq $obj.language -or [string]::IsNullOrWhiteSpace([string]$obj.language)){" ^
  "  $obj | Add-Member -NotePropertyName language -NotePropertyValue 'en' -Force" ^
  "};" ^
  "if(-not [string]::IsNullOrWhiteSpace($env:APOLLO_FFMPEG)){" ^
  "  $obj | Add-Member -NotePropertyName ffmpeg_shared_bin -NotePropertyValue $env:APOLLO_FFMPEG -Force" ^
  "};" ^
  "$json=$obj | ConvertTo-Json -Depth 20;" ^
  "[System.IO.File]::WriteAllText($path,$json+[Environment]::NewLine,(New-Object System.Text.UTF8Encoding($false)));" ^
  "Write-Host ('Apollo XTTS model_dir -> '+$obj.model_dir)"

if errorlevel 1 (
    echo.
    echo [ERROR] Could not update Apollo settings.
    pause
    exit /b 1
)

echo.
echo ------------------------------------------------------------
echo  4/4 - Verify saved settings
echo ------------------------------------------------------------

"%PYTHON_EXE%" -c "import json,pathlib; p=pathlib.Path(r'%SETTINGS%'); d=json.loads(p.read_text(encoding='utf-8')); assert d.get('backend')=='xtts_local'; assert pathlib.Path(d['model_dir']).resolve()==pathlib.Path(r'%MODEL%').resolve(); print('Voice Imprint settings: OK'); print('backend:',d['backend']); print('model_dir:',d['model_dir']); print('device:',d.get('device')); print('language:',d.get('language'))"
if errorlevel 1 (
    echo [ERROR] Settings file was written but verification failed.
    pause
    exit /b 1
)

echo.
echo ============================================================
echo  MANUAL XTTS INSTALL COMPLETE
echo ============================================================
echo.
echo Restart Apollo, then open:
echo   Voice Imprint Lab
echo   ^> Check Voice + Engine Readiness
echo.
pause
exit /b 0
