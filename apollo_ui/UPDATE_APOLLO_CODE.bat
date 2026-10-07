@echo off
setlocal EnableExtensions
title Apollo - Update Code Only
cd /d "%~dp0"

echo ============================================================
echo  APOLLO CODE UPDATE
echo ============================================================
echo.
echo This updates tracked Apollo source files with Git.
echo It does NOT redownload the XTTS model in:
echo   %LOCALAPPDATA%\Apollo\models\voice\xtts_v2
echo.

where git.exe >nul 2>&1
if errorlevel 1 (
  echo [ERROR] Git is not installed or not on PATH.
  pause
  exit /b 1
)

git rev-parse --is-inside-work-tree >nul 2>&1
if errorlevel 1 (
  echo [ERROR] This Apollo folder is not a Git checkout.
  echo Clone the repository once, then future updates can use this tiny updater.
  pause
  exit /b 1
)

echo Checking for local code changes...
git status --porcelain
if not errorlevel 1 (
  for /f %%A in ('git status --porcelain ^| find /c /v ""') do set "CHANGES=%%A"
)
if defined CHANGES if not "%CHANGES%"=="0" (
  echo.
  echo [STOPPED] Local tracked/untracked changes exist.
  echo Commit or stash them first so an update cannot silently overwrite your work.
  pause
  exit /b 2
)

echo.
echo Fetching only repository changes...
git fetch --prune origin
if errorlevel 1 goto :FAIL

for /f "delims=" %%B in ('git branch --show-current') do set "BRANCH=%%B"
if not defined BRANCH set "BRANCH=main"
echo Updating branch: %BRANCH%
git pull --ff-only origin "%BRANCH%"
if errorlevel 1 goto :FAIL

echo.
echo [OK] Apollo code updated.
echo Large local model data was left alone.
pause
exit /b 0

:FAIL
echo.
echo [ERROR] Update failed. Existing Apollo files were not force-overwritten.
pause
exit /b 1
