@echo off
setlocal EnableExtensions DisableDelayedExpansion
title Apollo Foundry - Docker Sandbox Image Setup
echo ==============================================================
echo  APOLLO FOUNDRY - DOCKER SANDBOX IMAGE SETUP
echo ==============================================================
echo This window stays open and saves diagnostics if Docker is unavailable.
echo Generated application tests will run without network access.
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
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%HELPER%" -Action BuildImage
set "RESULT=%ERRORLEVEL%"
:finish
echo.
echo ==============================================================
echo Sandbox setup exit code: %RESULT%
echo Press any key to close this window. The diagnostic log is shown above.
echo ==============================================================
pause >nul
endlocal & exit /b %RESULT%
