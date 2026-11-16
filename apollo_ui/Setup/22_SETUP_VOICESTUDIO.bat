@echo off
setlocal EnableExtensions DisableDelayedExpansion
title Apollo - VoiceStudio Setup
cd /d "%~dp0.."
set "EXE=%CD%\.venv\Scripts\python.exe"
if exist "%EXE%" goto :RUN
where py.exe >nul 2>&1
if not errorlevel 1 (
  set "EXE=py -3"
  goto :RUN
)
where python.exe >nul 2>&1
if not errorlevel 1 (
  set "EXE=python"
  goto :RUN
)
echo [ERROR] Python is missing. Run Setup\01_INSTALL_APOLLO.bat first.
set "EXIT_CODE=1"
goto :END
:RUN
echo =========================================================
echo APOLLO VOICESTUDIO BACKEND SETUP
echo =========================================================
echo [INFO] This installer does not overwrite Apollo or XTTS.
echo [INFO] Default is read-only. Supply --install to request installation.
echo [INFO] Use --path "F:\Apollo\VoiceStudio" for a custom source folder.
echo [INFO] With --install --with-prerequisites, approved missing tools use WinGet.
if "%EXE%"=="py -3" (
  py -3 "%CD%\apollo_voicestudio_install_cli.py" %*
) else if "%EXE%"=="python" (
  python "%CD%\apollo_voicestudio_install_cli.py" %*
) else (
  "%EXE%" "%CD%\apollo_voicestudio_install_cli.py" %*
)
set "EXIT_CODE=%ERRORLEVEL%"
:END
echo.
echo [RESULT] VoiceStudio setup result code %EXIT_CODE%.
if not defined CI (
  echo Press any key to close.
  pause >nul
)
endlocal & exit /b %EXIT_CODE%
