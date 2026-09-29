@echo off
setlocal EnableExtensions EnableDelayedExpansion
title Apollo XTTS v2 - Clean Runtime Install
cd /d "%~dp0"

set "APOLLO_DIR=%~dp0"
if "%APOLLO_DIR:~-1%"=="\" set "APOLLO_DIR=%APOLLO_DIR:~0,-1%"

set "XTTS_ROOT=%LOCALAPPDATA%\Apollo\models\voice"
set "XTTS_TARGET=%XTTS_ROOT%\xtts_v2"
set "DOWNLOAD_HOME=%LOCALAPPDATA%\Apollo\downloads\coqui_tts"
set "LEGACY_XTTS=%APOLLO_DIR%\storage\models\voice\xtts_v2"

rem Known-good Apollo XTTS runtime pins for Python 3.14 / Windows.
set "TORCH_VERSION=2.11.0"
set "TORCHVISION_VERSION=0.26.0"
set "TORCHAUDIO_VERSION=2.11.0"
set "TORCHCODEC_VERSION=0.16.0"
set "COQUI_VERSION=0.27.5"
set "TRANSFORMERS_VERSION=4.57.6"
set "PYTORCH_INDEX=https://download.pytorch.org/whl/cu128"

echo.
echo ============================================================
echo  APOLLO XTTS v2 - CLEAN RUNTIME INSTALL
echo ============================================================
echo.
echo Apollo:
echo   %APOLLO_DIR%
echo.
echo XTTS engine:
echo   %XTTS_TARGET%
echo.
echo This deliberately REMOVES the conflicting XTTS/PyTorch Python stack
echo and reinstalls it in a fixed dependency order.
echo.
echo Runtime target:
echo   torch          %TORCH_VERSION%  CUDA 12.8
echo   torchvision    %TORCHVISION_VERSION%
echo   torchaudio     %TORCHAUDIO_VERSION%
echo   torchcodec     %TORCHCODEC_VERSION%
echo   coqui-tts      %COQUI_VERSION%
echo   transformers   %TRANSFORMERS_VERSION%
echo.
echo Existing voice profiles and downloaded XTTS model files are NOT deleted.
echo.

set "PYTHONHOME="
set "PYTHONPATH="
set "PYTHON_EXE="

call :TRY_PY "%LOCALAPPDATA%\Python\pythoncore-3.14-64\python.exe"
call :TRY_PY "%APOLLO_DIR%\.venv\Scripts\python.exe"
call :TRY_PY "%APOLLO_DIR%\venv\Scripts\python.exe"

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
    echo Run repair_apollo_python.bat first.
    pause
    exit /b 1
)

echo [OK] Python:
echo   %PYTHON_EXE%
"%PYTHON_EXE%" --version
if errorlevel 1 goto :FAIL

if not exist "%XTTS_ROOT%" mkdir "%XTTS_ROOT%"
if not exist "%LOCALAPPDATA%\Apollo\downloads" mkdir "%LOCALAPPDATA%\Apollo\downloads"

rem Preserve/migrate a completed old model before touching packages.
if not exist "%XTTS_TARGET%\config.json" (
    if exist "%LEGACY_XTTS%\config.json" if exist "%LEGACY_XTTS%\model.pth" if exist "%LEGACY_XTTS%\vocab.json" (
        echo.
        echo [INFO] Complete XTTS model found in Apollo storage.
        echo Moving it to C: so it will not need to be downloaded again...
        if exist "%XTTS_TARGET%" rmdir /S /Q "%XTTS_TARGET%"
        mkdir "%XTTS_TARGET%"
        robocopy "%LEGACY_XTTS%" "%XTTS_TARGET%" /E /MOVE /R:2 /W:2 /NFL /NDL /NJH /NJS /NP
        set "ROBO=%ERRORLEVEL%"
        if !ROBO! GEQ 8 goto :FAIL
    )
)

echo.
echo ------------------------------------------------------------
echo  1/10 - Update packaging tools
echo ------------------------------------------------------------
"%PYTHON_EXE%" -m pip install --upgrade pip setuptools wheel
if errorlevel 1 goto :FAIL

echo.
echo ------------------------------------------------------------
echo  2/10 - REMOVE old/conflicting XTTS runtime
echo ------------------------------------------------------------
echo Removing torch / torchvision / torchaudio / torchcodec / Coqui /
echo Transformers so Apollo starts from one known dependency stack...
echo.

"%PYTHON_EXE%" -m pip uninstall -y torch torchvision torchaudio torchcodec coqui-tts TTS transformers tokenizers
rem pip uninstall returns successfully even when individual packages are absent.
if errorlevel 1 (
    echo [WARNING] pip reported an uninstall issue. Continuing with forced clean install.
)

echo.
echo Verifying the critical runtime packages are gone...
"%PYTHON_EXE%" -c "import importlib.util as u; names=['torch','torchvision','torchaudio','torchcodec','TTS','transformers']; left=[n for n in names if u.find_spec(n) is not None]; print('Remaining importable packages:',left); raise SystemExit(1 if left else 0)"
if errorlevel 1 (
    echo.
    echo [WARNING] Some old package files remain importable.
    echo Running pip uninstall once more before continuing...
    "%PYTHON_EXE%" -m pip uninstall -y torch torchvision torchaudio torchcodec coqui-tts TTS transformers tokenizers
)

echo.
echo ------------------------------------------------------------
echo  3/10 - Shared FFmpeg runtime
echo ------------------------------------------------------------
set "FFMPEG_BIN="

echo Looking for an existing FFmpeg Shared installation...
call :FIND_SHARED_FFMPEG

if defined FFMPEG_BIN (
    echo [OK] Existing FFmpeg Shared located:
    echo   %FFMPEG_BIN%
) else (
    echo FFmpeg Shared DLLs were not found by direct file inspection.
    echo Installing/reinstalling the USER-SCOPE WinGet package...
    echo.

    where winget.exe >nul 2>&1
    if errorlevel 1 (
        echo [ERROR] WinGet is unavailable and Apollo could not locate FFmpeg Shared.
        echo Install Gyan.FFmpeg.Shared manually, then rerun this installer.
        goto :FAIL
    )

    winget install --id Gyan.FFmpeg.Shared --exact --source winget --scope user --force --accept-source-agreements --accept-package-agreements --disable-interactivity
    if errorlevel 1 (
        echo [WARNING] WinGet returned an error. Apollo will still search all
        echo known user and machine package roots before failing.
    )

    call :FIND_SHARED_FFMPEG
)

if not defined FFMPEG_BIN (
    echo.
    echo [ERROR] WinGet reports FFmpeg Shared, but Apollo cannot locate the
    echo shared DLL directory.
    echo.
    echo Apollo specifically needs one folder containing:
    echo   avcodec-*.dll
    echo   avformat-*.dll
    echo   avutil-*.dll
    echo.
    echo Searched locations include:
    echo   %LOCALAPPDATA%\Microsoft\WinGet\Packages
    echo   %ProgramFiles%\WinGet\Packages
    echo   C:\Program Files ^(x86^)\WinGet\Packages
    echo   C:\ffmpeg
    echo   PATH entries
    echo.
    goto :FAIL
)

echo [OK] Shared FFmpeg:
echo   %FFMPEG_BIN%

set "PATH=%FFMPEG_BIN%;%PATH%"
set "TORCHCODEC_FFMPEG_DIR=%FFMPEG_BIN%"

echo.
echo ------------------------------------------------------------
echo  4/10 - Fresh PyTorch GPU stack
echo ------------------------------------------------------------
echo Installing pinned PyTorch CUDA 12.8 runtime with NO pip cache...
echo.

"%PYTHON_EXE%" -m pip install --no-cache-dir --force-reinstall "torch==%TORCH_VERSION%" "torchvision==%TORCHVISION_VERSION%" "torchaudio==%TORCHAUDIO_VERSION%" --index-url "%PYTORCH_INDEX%"
if errorlevel 1 goto :FAIL

echo.
echo Verifying PyTorch family versions...
"%PYTHON_EXE%" -c "import torch,torchvision,torchaudio; print('torch:',torch.__version__); print('torchvision:',torchvision.__version__); print('torchaudio:',torchaudio.__version__); assert torch.__version__.split('+')[0]=='%TORCH_VERSION%'; assert torchvision.__version__.split('+')[0]=='%TORCHVISION_VERSION%'; assert torchaudio.__version__.split('+')[0]=='%TORCHAUDIO_VERSION%'; print('CUDA available:',torch.cuda.is_available()); print('GPU:',torch.cuda.get_device_name(0) if torch.cuda.is_available() else 'CPU fallback')"
if errorlevel 1 goto :FAIL

echo.
echo ------------------------------------------------------------
echo  5/10 - Fresh TorchCodec
echo ------------------------------------------------------------
echo Installing TorchCodec %TORCHCODEC_VERSION%...
"%PYTHON_EXE%" -m pip install --no-cache-dir --force-reinstall "torchcodec==%TORCHCODEC_VERSION%"
if errorlevel 1 goto :FAIL

echo.
echo Verifying TorchCodec with shared FFmpeg...
"%PYTHON_EXE%" -c "import os; os.add_dll_directory(r'%FFMPEG_BIN%') if hasattr(os,'add_dll_directory') else None; import torch,torchcodec,importlib.metadata as m; print('torch:',torch.__version__); print('torchcodec:',m.version('torchcodec')); assert m.version('torchcodec')=='%TORCHCODEC_VERSION%'; print('TorchCodec import: OK')"
if errorlevel 1 goto :FAIL

echo.
echo ------------------------------------------------------------
echo  6/10 - Fresh Coqui-TTS
echo ------------------------------------------------------------
"%PYTHON_EXE%" -m pip install --no-cache-dir --upgrade "coqui-tts==%COQUI_VERSION%"
if errorlevel 1 goto :FAIL

echo.
echo ------------------------------------------------------------
echo  7/10 - Pin Transformers LAST
echo ------------------------------------------------------------
rem Coqui may resolve a newer Transformers release. Pin the known XTTS-compatible
rem 4.x build after Coqui so nothing silently upgrades it back to 5.x.
"%PYTHON_EXE%" -m pip install --no-cache-dir --force-reinstall "transformers==%TRANSFORMERS_VERSION%"
if errorlevel 1 goto :FAIL

echo.
echo Verifying Transformers compatibility...
"%PYTHON_EXE%" -c "import transformers; from transformers.pytorch_utils import isin_mps_friendly; print('Transformers:',transformers.__version__); assert transformers.__version__=='%TRANSFORMERS_VERSION%'; print('isin_mps_friendly: OK')"
if errorlevel 1 goto :FAIL

echo.
echo ------------------------------------------------------------
echo  8/10 - Full XTTS runtime verification
echo ------------------------------------------------------------
"%PYTHON_EXE%" -c "import os; os.add_dll_directory(r'%FFMPEG_BIN%') if hasattr(os,'add_dll_directory') else None; import torch,torchcodec,transformers; from TTS.api import TTS; from TTS.tts.configs.xtts_config import XttsConfig; print('Coqui XTTS import: OK'); print('torch:',torch.__version__); print('transformers:',transformers.__version__)"
if errorlevel 1 goto :FAIL

echo.
echo Running pip dependency check...
"%PYTHON_EXE%" -m pip check
if errorlevel 1 (
    echo [ERROR] Python package dependency check failed.
    goto :FAIL
)

rem If model files already exist, do not redownload them.
if exist "%XTTS_TARGET%\config.json" if exist "%XTTS_TARGET%\model.pth" if exist "%XTTS_TARGET%\vocab.json" (
    echo.
    echo [OK] Existing XTTS model files are complete. Skipping model download.
    goto :CONFIGURE_APOLLO
)

echo.
echo ------------------------------------------------------------
echo  9/10 - XTTS model licence + download / resume
echo ------------------------------------------------------------
echo XTTS v2 is a pretrained model with its own model terms.
echo This is separate from using your own personal voice recording.
choice /C YN /M "Do you accept the XTTS model terms and want to continue"
if errorlevel 2 (
    echo Installation cancelled before model download.
    pause
    exit /b 2
)

set "COQUI_TOS_AGREED=1"
set "TTS_HOME=%DOWNLOAD_HOME%"
if not exist "%DOWNLOAD_HOME%" mkdir "%DOWNLOAD_HOME%"

"%PYTHON_EXE%" "%APOLLO_DIR%\download_xtts_model.py" "%DOWNLOAD_HOME%"
if errorlevel 1 (
    echo.
    echo [ERROR] XTTS model download failed.
    echo Partial download preserved at:
    echo   %DOWNLOAD_HOME%
    pause
    exit /b 1
)

set "FOUND_XTTS="
for /f "usebackq delims=" %%D in (`powershell -NoProfile -ExecutionPolicy Bypass -Command "$root='%DOWNLOAD_HOME%'; $m=Get-ChildItem -LiteralPath $root -Filter model.pth -File -Recurse -ErrorAction SilentlyContinue ^| Where-Object { Test-Path (Join-Path $_.DirectoryName 'config.json') -and Test-Path (Join-Path $_.DirectoryName 'vocab.json') } ^| Select-Object -First 1; if($m){$m.DirectoryName}"`) do (
    set "FOUND_XTTS=%%D"
)

if not defined FOUND_XTTS (
    echo [ERROR] XTTS model download completed but required model files were not found.
    goto :FAIL
)

if exist "%XTTS_TARGET%" rmdir /S /Q "%XTTS_TARGET%"
mkdir "%XTTS_TARGET%"
robocopy "!FOUND_XTTS!" "%XTTS_TARGET%" /E /MOVE /R:2 /W:2 /NFL /NDL /NJH /NJS /NP
set "ROBO=%ERRORLEVEL%"
if %ROBO% GEQ 8 goto :FAIL

:CONFIGURE_APOLLO
echo.
echo ------------------------------------------------------------
echo  10/10 - Verify model + configure Apollo
echo ------------------------------------------------------------

set "FAILED=0"
if exist "%XTTS_TARGET%\config.json" (echo [OK] config.json) else (echo [MISSING] config.json&set "FAILED=1")
if exist "%XTTS_TARGET%\model.pth" (echo [OK] model.pth) else (echo [MISSING] model.pth&set "FAILED=1")
if exist "%XTTS_TARGET%\vocab.json" (echo [OK] vocab.json) else (echo [MISSING] vocab.json&set "FAILED=1")
if exist "%XTTS_TARGET%\speakers_xtts.pth" echo [OK] speakers_xtts.pth
if "%FAILED%"=="1" goto :FAIL

"%PYTHON_EXE%" -c "import os; os.add_dll_directory(r'%FFMPEG_BIN%') if hasattr(os,'add_dll_directory') else None; from TTS.tts.configs.xtts_config import XttsConfig; c=XttsConfig(); c.load_json(r'%XTTS_TARGET%\config.json'); print('XTTS config loaded: OK')"
if errorlevel 1 goto :FAIL

set "VOICE_SETTINGS=%APOLLO_DIR%\storage\media\voice_imprint\settings.json"
if not exist "%APOLLO_DIR%\storage\media\voice_imprint" mkdir "%APOLLO_DIR%\storage\media\voice_imprint"

"%PYTHON_EXE%" -c "import json,pathlib; p=pathlib.Path(r'%VOICE_SETTINGS%'); d={}; exec(\"try:\\n d=json.loads(p.read_text(encoding='utf-8'))\\nexcept Exception:\\n d={}\"); d['backend']='xtts_local'; d['model_dir']=r'%XTTS_TARGET%'; d['device']='auto'; d.setdefault('language','en'); d['ffmpeg_shared_bin']=r'%FFMPEG_BIN%'; d['runtime_pins']={'torch':'%TORCH_VERSION%','torchvision':'%TORCHVISION_VERSION%','torchaudio':'%TORCHAUDIO_VERSION%','torchcodec':'%TORCHCODEC_VERSION%','coqui_tts':'%COQUI_VERSION%','transformers':'%TRANSFORMERS_VERSION%'}; p.write_text(json.dumps(d,indent=2)+'\n',encoding='utf-8'); print('Apollo XTTS settings updated:',p)"
if errorlevel 1 goto :FAIL

if exist "%DOWNLOAD_HOME%" rmdir /S /Q "%DOWNLOAD_HOME%" 2>nul

echo.
echo ============================================================
echo  XTTS CLEAN INSTALL COMPLETE
echo ============================================================
echo.
echo Runtime stack:
echo   torch          %TORCH_VERSION%
echo   torchvision    %TORCHVISION_VERSION%
echo   torchaudio     %TORCHAUDIO_VERSION%
echo   torchcodec     %TORCHCODEC_VERSION%
echo   coqui-tts      %COQUI_VERSION%
echo   transformers   %TRANSFORMERS_VERSION%
echo.
echo XTTS engine:
echo   %XTTS_TARGET%
echo.
echo Restart Apollo, then:
echo   Voice Imprint Lab ^> Check Voice + Engine Readiness
echo.
pause
exit /b 0

:TRY_PY
if defined PYTHON_EXE exit /b 0
if not exist "%~1" exit /b 0
"%~1" -c "import sys,encodings" >nul 2>&1
if not errorlevel 1 set "PYTHON_EXE=%~1"
exit /b 0

:FIND_SHARED_FFMPEG
set "FFMPEG_FIND_FILE=%TEMP%\apollo_ffmpeg_shared_%RANDOM%_%RANDOM%.txt"
if exist "%FFMPEG_FIND_FILE%" del /Q "%FFMPEG_FIND_FILE%" >nul 2>&1

powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%APOLLO_DIR%\find_ffmpeg_shared.ps1" > "%FFMPEG_FIND_FILE%" 2>nul
if not errorlevel 1 (
    set /p FFMPEG_BIN=<"%FFMPEG_FIND_FILE%"
)

if exist "%FFMPEG_FIND_FILE%" del /Q "%FFMPEG_FIND_FILE%" >nul 2>&1

if defined FFMPEG_BIN (
    dir /B "%FFMPEG_BIN%\avcodec-*.dll" >nul 2>&1
    if errorlevel 1 set "FFMPEG_BIN="
)
exit /b 0

:FAIL
echo.
echo ============================================================
echo  XTTS CLEAN INSTALL FAILED
echo ============================================================
echo Apollo did NOT mark the XTTS engine ready.
echo Read the first error above. The model/voice data was not deleted.
echo.
pause
exit /b 1
