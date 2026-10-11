@echo off
setlocal EnableExtensions
title Apollo 8 - Manual Code-Only Update
cd /d "%~dp0"
echo.
echo Download only from the official GitHub Actions build.
echo Close Apollo before proceeding.
echo UNSIGNED manual code patch, not the signed in-app updater.
echo.
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0Apply_Apollo8_Patch.ps1" %*
set "RESULT=%ERRORLEVEL%"
echo.
if "%RESULT%"=="0" (
  echo Update completed. You may restart Apollo.
) else (
  echo Update not completed. Read the message above.
)
pause
exit /b %RESULT%
