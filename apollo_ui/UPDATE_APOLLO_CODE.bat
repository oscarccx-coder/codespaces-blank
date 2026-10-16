@echo off
setlocal EnableExtensions DisableDelayedExpansion
title Apollo - Safe Code Update
rem Keep the legacy launcher, but use exactly the same checked Git main
rem updater as Apollo's in-app Update Centre. No unsigned code execution.
if not exist "%~dp0Setup\13_UPDATE_GIT_MAIN.bat" (
  echo [ERROR] Safe Git main updater is missing from Apollo Setup.
  if not defined CI pause
  endlocal & exit /b 1
)
call "%~dp0Setup\13_UPDATE_GIT_MAIN.bat" %*
set "EXIT_CODE=%errorlevel%"
endlocal & exit /b %EXIT_CODE%
