@echo off
setlocal EnableExtensions
title Apollo XTTS 7.5.12.11 Force Hotfix

set "APOLLO=F:\Apollo\apollo 1\apollo_ui"

echo ============================================================
echo  APOLLO XTTS 7.5.12.11 - FORCE HOTFIX
echo ============================================================
echo.

if not exist "%APOLLO%" (
    echo [ERROR] Apollo folder not found:
    echo   %APOLLO%
    pause
    exit /b 1
)

echo Replacing the stale XTTS installer files in:
echo   %APOLLO%
echo.

copy /Y "%~dp0install_xtts_v2.bat" "%APOLLO%\install_xtts_v2.bat" >nul
if errorlevel 1 goto :FAIL

copy /Y "%~dp0clean_reinstall_xtts_runtime.bat" "%APOLLO%\clean_reinstall_xtts_runtime.bat" >nul
if errorlevel 1 goto :FAIL

copy /Y "%~dp0repair_xtts_runtime.bat" "%APOLLO%\repair_xtts_runtime.bat" >nul
if errorlevel 1 goto :FAIL

copy /Y "%~dp0find_ffmpeg_shared.ps1" "%APOLLO%\find_ffmpeg_shared.ps1" >nul
if errorlevel 1 goto :FAIL

echo [OK] Hotfix files replaced.
echo.

findstr /C:"Looking for an existing FFmpeg Shared installation" "%APOLLO%\install_xtts_v2.bat" >nul
if errorlevel 1 (
    echo [ERROR] The stale installer is still present after copying.
    echo Do not continue.
    pause
    exit /b 1
)

echo [OK] Verified the NEW FFmpeg locator installer is now active.
echo.
echo Starting the clean XTTS installer...
echo.
cd /d "%APOLLO%"
call "%APOLLO%\clean_reinstall_xtts_runtime.bat"
exit /b %ERRORLEVEL%

:FAIL
echo.
echo [ERROR] Could not replace one or more Apollo files.
echo Try right-clicking this BAT and choosing Run as administrator.
echo.
pause
exit /b 1
