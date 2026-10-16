@echo off
setlocal EnableExtensions DisableDelayedExpansion
title Apollo Foundry - Docker Desktop Install and Diagnostics
echo ==============================================================
echo  APOLLO FOUNDRY - DOCKER DESKTOP INSTALLER AND DIAGNOSTICS
echo ==============================================================
echo This window stays open even if installation fails or is cancelled.
echo Existing Docker data, Apollo files and WSL distributions are not deleted.
echo.
set "HELPER=%~dp0Docker_Foundry_Setup.ps1"
set "RESULT=1"
if not exist "%HELPER%" (
  echo [ERROR] Missing helper: "%HELPER%"
  goto :finish
)
where powershell.exe >nul 2>&1
if errorlevel 1 (
  echo [ERROR] Windows PowerShell was not found.
  goto :finish
)
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%HELPER%" -Action InstallDocker
set "RESULT=%ERRORLEVEL%"
:finish
echo.
echo ==============================================================
echo Docker setup exit code: %RESULT%
echo Press any key to close this window. The diagnostic log is shown above.
echo ==============================================================
pause >nul
endlocal & exit /b %RESULT%
